from __future__ import annotations

# Standard Library Imports.
from pathlib import Path


class CatalogueStoreError(Exception):
    """Base class for every error raised by the catalogue store.

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


class CatalogueFileError(CatalogueStoreError):
    """Raised when a catalogue file cannot be loaded.

    Attributes:
        path (Path): The catalogue file path.
        reason (str): Human-readable explanation of why loading failed.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The catalogue file path.
            reason (str): Human-readable explanation of why loading failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot load the catalogue '{path}': {reason}.")


class CatalogueWriteError(CatalogueStoreError):
    """Raised when a catalogue file cannot be written.

    Attributes:
        path (Path): The catalogue file path.
        reason (str): Human-readable explanation of why writing failed.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The catalogue file path.
            reason (str): Human-readable explanation of why writing failed.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot write the catalogue '{path}': {reason}.")
