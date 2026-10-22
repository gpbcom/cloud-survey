from __future__ import annotations

# Standard Library Imports.
import asyncio
import threading
from concurrent.futures import Future
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Optional

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal

# First Party Imports.
from gui.storage_bridge.storage_job import StorageJob
from gui.storage_bridge.storage_request import StorageRequest
from storage.exception import StorageError
from storage.storage import Storage


class StorageLoop(QObject):
    """Run the storage requests of the GUI in a dedicated thread with its own asyncio event loop.

    Attributes:
        STOP_TIMEOUT (ClassVar[float]): How long, in seconds, closing the storage may take.
        DRAIN_TIMEOUT (ClassVar[float]): How long, in seconds, the running jobs may take to finish before the
            storage closes (they are cancelled afterwards).
        finished (pyqtSignal): Emitted (from the storage thread) with each job once it ran: Qt queues it to the GUI
            thread, where the job delivers its outcome.
        storage (Storage): The storage of the GUI, opened in the storage thread at the first request.
        loop (Optional[asyncio.AbstractEventLoop]): The event loop of the storage thread, `None` until started.
        worker_thread (Optional[threading.Thread]): The storage thread.
        logger (Logger): The loop logger.

    Notes:
        The asyncpg connections belong to the event loop which opened them: the GUI storage lives in this thread
        only, the crawls opening their own storage in their own event loop. The Qt event loop is never blocked by a
        database request, and the results (pydantic models) are built in the storage thread.
    """

    STOP_TIMEOUT: ClassVar[float] = 5.0
    DRAIN_TIMEOUT: ClassVar[float] = 2.0

    finished = pyqtSignal(object)

    def __init__(self, storage: Storage, logger: Optional[Logger] = None) -> None:
        """Initialize the loop, without starting it.

        Args:
            storage (Storage): The storage of the GUI, not open yet.
            logger (Optional[Logger]): The loop logger.
        """
        super().__init__()
        self.storage = storage
        self.logger = logger if logger else getLogger(__name__)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.finished.connect(self._deliver)
        self.logger.debug("Storage thread of the GUI prepared for %s.", storage.url)

    ############################
    # Internal Helpers Methods #
    ############################

    def _run_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Run the event loop of the storage thread until it is stopped.

        Args:
            loop (asyncio.AbstractEventLoop): The event loop.
        """
        self.logger.debug("Storage event loop running.")
        asyncio.set_event_loop(loop)
        loop.run_forever()
        loop.close()

    async def _execute(self, job: StorageJob) -> None:
        """Run a job on the storage, opening it first when needed, then hand the job to the GUI thread.

        Args:
            job (StorageJob): The job.
        """
        try:
            if not self.storage.database.is_open:
                await self.storage.database.open()
        except StorageError as e:
            self.logger.warning("The storage of the GUI cannot be opened: %s", e)
            job.fail(e)
        else:
            await job.run(self.storage)
        self.finished.emit(job)

    def _deliver(self, job: StorageJob) -> None:
        """Hand the outcome of a job to its callbacks (GUI thread).

        Args:
            job (StorageJob): The job.
        """
        self.logger.debug("Delivering a storage answer to the GUI.")
        job.deliver()

    async def _shutdown(self) -> None:
        """Let the running jobs finish, cancel those still running, then close the storage (storage thread).

        Notes:
            Closing the engine only closes the idle connections: a job left running would keep its connection (and
            its transaction, which blocks the schema changes and truncations of the tables) open. A job cancelled
            while its query runs may leave its connection in a transaction too, so the jobs get `DRAIN_TIMEOUT`
            seconds to finish before the remaining ones are cancelled.
        """
        jobs = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        pending = set(jobs)
        if jobs:
            self.logger.debug("Waiting for %d running storage jobs of the GUI.", len(jobs))
            _, pending = await asyncio.wait(jobs, timeout=self.DRAIN_TIMEOUT)
        for task in pending:
            task.cancel()
        if pending:
            self.logger.info("Cancelling %d running storage jobs of the GUI.", len(pending))
            await asyncio.gather(*pending, return_exceptions=True)
        await self.storage.database.close()

    ############################
    # Publicly Exposed Methods #
    ############################

    @property
    def is_running(self) -> bool:
        """Tell whether the storage thread runs.

        Returns:
            bool: Whether the loop was started and not stopped.
        """
        return self.loop is not None

    def start(self) -> asyncio.AbstractEventLoop:
        """Start the storage thread, unless it runs (done by the first request).

        Returns:
            asyncio.AbstractEventLoop: The event loop of the storage thread.
        """
        if self.loop is not None:
            return self.loop
        loop = asyncio.new_event_loop()
        self.loop = loop
        self.worker_thread = threading.Thread(target=self._run_loop, args=(loop,), name="storage", daemon=True)
        self.worker_thread.start()
        self.logger.debug("Storage thread of the GUI started on %s.", self.storage.url)
        return loop

    def submit[R](
        self,
        job: Callable[[Storage], Awaitable[R]],
        on_done: Callable[[R], None],
        on_error: Optional[Callable[[StorageError], None]] = None,
    ) -> Future[None]:
        """Run a coroutine function on the storage, its result handed to a callback in the GUI thread.

        Args:
            job (Callable[[Storage], Awaitable[R]]): The coroutine function, given the open storage.
            on_done (Callable[[R], None]): Called with the result, in the GUI thread.
            on_error (Optional[Callable[[StorageError], None]]): Called with a storage error, in the GUI thread.

        Returns:
            Future[None]: The run of the job in the storage thread (its outcome goes to the callbacks).
        """
        loop = self.start()
        request = StorageRequest[R](job, on_done, on_error, self.logger)
        self.logger.debug("Storage request submitted to the storage thread.")
        return asyncio.run_coroutine_threadsafe(self._execute(request), loop)

    def stop(self) -> None:
        """Cancel the running jobs, close the storage and stop the storage thread."""
        loop, thread = self.loop, self.worker_thread
        if loop is None:
            return
        self.loop, self.worker_thread = None, None
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), loop).result(self.STOP_TIMEOUT)
        except (StorageError, TimeoutError) as e:
            self.logger.warning("The storage of the GUI was not closed cleanly: %s", e)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(self.STOP_TIMEOUT)
        self.logger.debug("Storage thread of the GUI stopped.")
