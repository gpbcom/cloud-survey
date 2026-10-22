from __future__ import annotations

# Standard Library Imports.
from typing import List


class CorrespondenceModelError(ValueError):
    """Base class for every correspondence validation error.

    Attributes:
        message (str): Human-readable description of the error.

    Notes:
        It is a `ValueError`, so pydantic reports it as a `ValidationError` when raised by a validator.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class InvalidColumnsError(CorrespondenceModelError):
    """Raised when the provider columns of a correspondence query are not 2 to 6 distinct providers.

    Attributes:
        columns (List[str]): The rejected columns.
    """

    def __init__(self, columns: List[str], minimum: int, maximum: int) -> None:
        """Initialize the error.

        Args:
            columns (List[str]): The rejected columns.
            minimum (int): The smallest number of columns.
            maximum (int): The largest number of columns.
        """
        self.columns = columns
        super().__init__(f"{minimum} to {maximum} distinct provider columns are needed, got {columns}.")


class EmptyConceptNameError(CorrespondenceModelError):
    """Raised when a service concept has no name."""

    def __init__(self) -> None:
        """Initialize the error."""
        super().__init__("A service concept needs a name.")
