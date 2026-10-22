from __future__ import annotations

# Standard Library Imports.
from typing import Protocol, runtime_checkable

# First Party Imports.
from storage.exception import StorageError
from storage.storage import Storage


@runtime_checkable
class StorageJob(Protocol):
    """A job run on the storage in the storage thread, its outcome delivered in the GUI thread."""

    ############################
    # Publicly Exposed Methods #
    ############################

    async def run(self, storage: Storage) -> None:
        """Run the job on the open storage, keeping its result or its error (storage thread).

        Args:
            storage (Storage): The open storage.
        """

    def fail(self, error: StorageError) -> None:
        """Record that the job could not run (storage thread).

        Args:
            error (StorageError): Why it could not run.
        """

    def deliver(self) -> None:
        """Hand the result, or the error, to the callbacks of the job (GUI thread)."""
