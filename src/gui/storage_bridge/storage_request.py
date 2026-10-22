from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Awaitable, Callable, Optional, cast

# First Party Imports.
from storage.exception import StorageError
from storage.storage import Storage


class StorageRequest[R]:
    """A read or write of the storage asked by the GUI: run in the storage thread, answered in the GUI thread.

    Attributes:
        job (Callable[[Storage], Awaitable[R]]): The coroutine function run on the open storage.
        on_done (Callable[[R], None]): Called with the result, in the GUI thread.
        on_error (Optional[Callable[[StorageError], None]]): Called with the error, in the GUI thread, logged only
            when `None`.
        result (Optional[R]): The result, once the job ran without error.
        error (Optional[StorageError]): The error of the job, if it failed.
        logger (Logger): The request logger.
    """

    def __init__(
        self,
        job: Callable[[Storage], Awaitable[R]],
        on_done: Callable[[R], None],
        on_error: Optional[Callable[[StorageError], None]] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the request.

        Args:
            job (Callable[[Storage], Awaitable[R]]): The coroutine function run on the open storage.
            on_done (Callable[[R], None]): Called with the result, in the GUI thread.
            on_error (Optional[Callable[[StorageError], None]]): Called with the error, in the GUI thread.
            logger (Optional[Logger]): The request logger.
        """
        self.job = job
        self.on_done = on_done
        self.on_error = on_error
        self.result: Optional[R] = None
        self.error: Optional[StorageError] = None
        self.done = False
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Storage request prepared.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def run(self, storage: Storage) -> None:
        """Run the job on the open storage, keeping its result or its error (storage thread).

        Args:
            storage (Storage): The open storage.
        """
        try:
            self.result = await self.job(storage)
            self.done = True
        except StorageError as e:
            self.logger.warning("A storage request of the GUI failed: %s", e)
            self.error = e

    def fail(self, error: StorageError) -> None:
        """Record that the job could not run (storage thread).

        Args:
            error (StorageError): Why it could not run.
        """
        self.logger.warning("A storage request of the GUI could not run: %s", error)
        self.error = error

    def deliver(self) -> None:
        """Hand the result, or the error, to the callbacks (GUI thread)."""
        self.logger.debug("Storage request answered (%s).", "error" if self.error is not None else "result")
        if self.error is not None:
            if self.on_error is not None:
                self.on_error(self.error)
            return
        if self.done:
            self.on_done(cast(R, self.result))
