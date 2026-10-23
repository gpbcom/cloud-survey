from __future__ import annotations

# Standard Library Imports.
from typing import List


class MarketsModelError(ValueError):
    """Base class for every validation error of the market shares and stock values.

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


class InvalidMarketValueError(MarketsModelError):
    """Raised when a key, a code, a currency, a symbol or a date of the markets is malformed.

    Attributes:
        kind (str): What the value is, e.g. `stock symbol`.
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
        self.kind, self.value, self.expected = kind, value, expected
        super().__init__(f"The {kind} {value!r} is malformed: {expected} is expected.")


class UnknownMarketReferenceError(MarketsModelError):
    """Raised when the markets catalogue names an area, a segment, a company or a currency it does not define.

    Attributes:
        kind (str): What is referenced, e.g. `area`.
        key (str): The unknown key.
    """

    def __init__(self, kind: str, key: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What is referenced.
            key (str): The unknown key.
        """
        self.kind, self.key = kind, key
        super().__init__(f"Unknown {kind} {key!r}: define it in the markets catalogue first.")


class DuplicateMarketKeyError(MarketsModelError):
    """Raised when two entries of the markets catalogue share a key.

    Attributes:
        kind (str): What is duplicated, e.g. `listing`.
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


class InvalidMarketTextError(MarketsModelError):
    """Raised when a text of the markets is not a string, is empty or is too long.

    Attributes:
        kind (str): What the text is, e.g. `listing note`.
        value (str): The rejected value, shortened.
        expected (str): What is expected, e.g. `1 to 80 characters`.
    """

    def __init__(self, kind: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the text is.
            value (str): The rejected value.
            expected (str): What is expected.
        """
        self.kind, self.value, self.expected = kind, value[:120], expected
        super().__init__(f"The {kind} {self.value!r} is invalid: {expected} expected.")


class InvalidMarketNumberError(MarketsModelError):
    """Raised when a number of the markets is not a number or is out of its range.

    Attributes:
        kind (str): What the number is, e.g. `share`.
        value (str): The rejected value.
        expected (str): The expected range, e.g. `a number from 0 to 100`.
    """

    def __init__(self, kind: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the number is.
            value (str): The rejected value.
            expected (str): The expected range.
        """
        self.kind, self.value, self.expected = kind, value, expected
        super().__init__(f"The {kind} {value!r} is invalid: {expected} expected.")


class InvalidMarketChoiceError(MarketsModelError):
    """Raised when a value of the markets is not one of its allowed values (an enum).

    Attributes:
        kind (str): What the value is, e.g. `device`.
        value (str): The rejected value.
        choices (List[str]): The allowed values.
    """

    def __init__(self, kind: str, value: str, choices: List[str]) -> None:
        """Initialize the error.

        Args:
            kind (str): What the value is.
            value (str): The rejected value.
            choices (List[str]): The allowed values.
        """
        self.kind, self.value, self.choices = kind, value, choices
        super().__init__(f"The {kind} {value!r} is unknown: one of {', '.join(choices)} expected.")


class InvalidMarketDateError(MarketsModelError):
    """Raised when a date of the markets is not a date nor an ISO date text.

    Attributes:
        kind (str): What the date is, e.g. `trading day`.
        value (str): The rejected value.
    """

    def __init__(self, kind: str, value: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the date is.
            value (str): The rejected value.
        """
        self.kind, self.value = kind, value
        super().__init__(f"The {kind} {value!r} is not a date: YYYY-MM-DD expected.")


class InvalidMarketFlagError(MarketsModelError):
    """Raised when a yes-or-no value of the markets is not a boolean.

    Attributes:
        kind (str): What the flag is, e.g. `primary listing`.
        value (str): The rejected value.
    """

    def __init__(self, kind: str, value: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the flag is.
            value (str): The rejected value.
        """
        self.kind, self.value = kind, value
        super().__init__(f"The {kind} {value!r} is not a boolean.")


class InvalidMarketListError(MarketsModelError):
    """Raised when a list of the markets (points, entries, lags) is not a list or holds a malformed item.

    Attributes:
        kind (str): What the list is, e.g. `share points`.
        expected (str): What is expected, e.g. `a list of (date, value) pairs`.
    """

    def __init__(self, kind: str, expected: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the list is.
            expected (str): What is expected.
        """
        self.kind, self.expected = kind, expected
        super().__init__(f"The {kind} are invalid: {expected} expected.")
