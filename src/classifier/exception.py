from __future__ import annotations

# Standard Library Imports.
from pathlib import Path


class ClassifierError(Exception):
    """Base class for every error raised while classifying the marketplace software.

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


class ClassificationRulesFileError(ClassifierError):
    """Raised when the classification rules file cannot be loaded.

    Attributes:
        path (Path): The rules file path.
        reason (str): Human-readable explanation of why loading failed.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The rules file path.
            reason (str): Human-readable explanation of why loading failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot load the classification rules {path}: {reason}")
