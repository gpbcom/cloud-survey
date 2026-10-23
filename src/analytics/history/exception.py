from __future__ import annotations

# Standard Library Imports.
from pathlib import Path


class HistoryError(Exception):
    """Base class for every error of the computing chronology.

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


class ChronologyFileError(HistoryError):
    """Raised when the chronology cannot be loaded.

    Attributes:
        path (Path): The chronology file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The chronology file.
            reason (str): Why it cannot be loaded.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The chronology {path} cannot be loaded: {reason}")
