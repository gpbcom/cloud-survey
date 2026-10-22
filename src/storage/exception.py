from __future__ import annotations


class StorageError(Exception):
    """Base class for every error raised by the storage of the crawled data.

    Attributes:
        message (str): Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class StorageConnectionError(StorageError):
    """Raised when the database cannot be reached, or is used before being opened.

    Attributes:
        url (str): The database URL, without its password.
        reason (str): Human-readable explanation of why the connection failed.
    """

    def __init__(self, url: str, reason: str) -> None:
        """Initialize the error.

        Args:
            url (str): The database URL, without its password.
            reason (str): Human-readable explanation of why the connection failed.
        """
        self.url = url
        self.reason = reason
        super().__init__(f"Cannot use the database {url}: {reason}.")


class StorageSchemaError(StorageError):
    """Raised when the database schema is missing or not the one the code expects.

    Attributes:
        found (str): The schema revision of the database, `none` when it has no schema.
        expected (str): The schema revision the code expects.
    """

    def __init__(self, found: str, expected: str) -> None:
        """Initialize the error.

        Args:
            found (str): The schema revision of the database, `none` when it has no schema.
            expected (str): The schema revision the code expects.
        """
        self.found = found
        self.expected = expected
        super().__init__(
            f"The database schema is at revision {found} instead of {expected}: run `uv run migrate-db upgrade`."
        )


class StorageLockError(StorageError):
    """Raised when a dataset is already being written by another crawl.

    Attributes:
        kind (str): What the dataset holds (catalogue, marketplace or statistics).
        dataset (str): The cloud provider, or the statistics source.
    """

    def __init__(self, kind: str, dataset: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the dataset holds.
            dataset (str): The cloud provider, or the statistics source.
        """
        self.kind = kind
        self.dataset = dataset
        super().__init__(f"The {dataset} {kind} is already being written by another crawl.")


class StorageWriteError(StorageError):
    """Raised when crawled data cannot be written to the database.

    Attributes:
        what (str): What was written (e.g. `aws marketplace`).
        reason (str): Human-readable explanation of why writing failed.
    """

    def __init__(self, what: str, reason: str) -> None:
        """Initialize the error.

        Args:
            what (str): What was written.
            reason (str): Human-readable explanation of why writing failed.
        """
        self.what = what
        self.reason = reason
        super().__init__(f"Cannot write the {what}: {reason}.")


class StorageReadError(StorageError):
    """Raised when stored data cannot be read from the database.

    Attributes:
        what (str): What was read (e.g. `aws marketplace`).
        reason (str): Human-readable explanation of why reading failed.
    """

    def __init__(self, what: str, reason: str) -> None:
        """Initialize the error.

        Args:
            what (str): What was read.
            reason (str): Human-readable explanation of why reading failed.
        """
        self.what = what
        self.reason = reason
        super().__init__(f"Cannot read the {what}: {reason}.")


class StorageImportError(StorageError):
    """Raised when a JSON file of the former file storage cannot be imported.

    Attributes:
        path (str): The JSON file.
        reason (str): Human-readable explanation of why importing failed.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The JSON file.
            reason (str): Human-readable explanation of why importing failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot import {path}: {reason}.")


class StorageExportError(StorageError):
    """Raised when stored items cannot be exported to a file.

    Attributes:
        path (str): The export file.
        reason (str): Human-readable explanation of why exporting failed.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The export file.
            reason (str): Human-readable explanation of why exporting failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot export to {path}: {reason}.")
