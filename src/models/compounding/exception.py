from __future__ import annotations


class CompoundingModelError(ValueError):
    """Base class for every validation error of the service-compounding configuration and results.

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


class InvalidCompoundingValueError(CompoundingModelError):
    """Raised when a value of the compounding configuration is malformed.

    Attributes:
        kind (str): What the value is, e.g. `start year`.
        value (str): The rejected value.
        expected (str): The expected format.
    """

    def __init__(self, kind: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the value is.
            value (str): The rejected value.
            expected (str): The expected format.
        """
        self.kind, self.value, self.expected = kind, value[:120], expected
        super().__init__(f"The {kind} {self.value!r} is malformed: {expected} is expected.")


class DuplicateCompoundingEntryError(CompoundingModelError):
    """Raised when the compounding configuration names an entry twice.

    Attributes:
        kind (str): What is duplicated, e.g. `provider`.
        key (str): The duplicated key.
    """

    def __init__(self, kind: str, key: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What is duplicated.
            key (str): The duplicated key.
        """
        self.kind, self.key = kind, key
        super().__init__(f"The {kind} {key!r} is listed twice.")
