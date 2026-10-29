from __future__ import annotations


class CompaniesModelError(ValueError):
    """Base class for every validation error of the companies' financial statements, patents and papers.

    Attributes:
        message (str): Human-readable description of the error.

    Notes:
        It is a `ValueError`, so pydantic reports it as a `ValidationError` when raised by a validator. The checks
        shared with the markets models (`MarketFieldCheck`) raise the markets errors, also `ValueError`s.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class InvalidCompanyValueError(CompaniesModelError):
    """Raised when a key, an identifier, a pattern, a period or a code of the companies data is malformed.

    Attributes:
        kind (str): What the value is, e.g. `SEC filer`.
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


class DuplicateCompanyKeyError(CompaniesModelError):
    """Raised when two entries of the companies catalogue share a key.

    Attributes:
        kind (str): What is duplicated, e.g. `company`.
        key (str): The duplicated key.
    """

    def __init__(self, kind: str, key: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What is duplicated.
            key (str): The duplicated key.
        """
        self.kind, self.key = kind, key
        super().__init__(f"The {kind} {key!r} is defined twice.")
