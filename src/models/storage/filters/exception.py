from __future__ import annotations

# Standard Library Imports.
from datetime import datetime


class StorageFilterError(ValueError):
    """Base class for every error raised by the filters of the stored items.

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


class InvalidDateRangeError(StorageFilterError):
    """Raised when a date range ends before it starts.

    Attributes:
        after (datetime): The start of the range.
        before (datetime): The end of the range.
    """

    def __init__(self, after: datetime, before: datetime) -> None:
        """Initialize the error.

        Args:
            after (datetime): The start of the range.
            before (datetime): The end of the range.
        """
        self.after = after
        self.before = before
        super().__init__(f"The date range ends ({before.isoformat()}) before it starts ({after.isoformat()}).")
