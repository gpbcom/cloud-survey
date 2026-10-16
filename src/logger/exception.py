from __future__ import annotations

# Standard Library Imports.
from pathlib import Path


class LoggerError(Exception):
    """Base class for every error raised while setting the logging up.

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


class LoggingConfigFileError(LoggerError):
    """Raised when the logging configuration file cannot be loaded.

    Attributes:
        path (Path): The logging configuration file path.
        reason (str): Human-readable explanation of why loading failed.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The logging configuration file path.
            reason (str): Human-readable explanation of why loading failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot load the logging configuration '{path}': {reason}")
