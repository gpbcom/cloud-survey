from __future__ import annotations


class HistoryModelError(ValueError):
    """Base class for every validation error of the computing chronology.

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


class InvalidHistoryDateError(HistoryModelError):
    """Raised when a date of the chronology is not written `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.

    Attributes:
        value (str): The rejected date.
    """

    def __init__(self, value: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected date.
        """
        self.value = value
        super().__init__(f"A date must be written YYYY, YYYY-MM or YYYY-MM-DD, got {value!r}.")  # noqa: E501


class ReignOrderError(HistoryModelError):
    """Raised when a reign ends before it starts.

    Attributes:
        start (str): The start of the reign.
        end (str): The end of the reign.
    """

    def __init__(self, start: str, end: str) -> None:
        """Initialize the error.

        Args:
            start (str): The start of the reign.
            end (str): The end of the reign.
        """
        self.start, self.end = start, end
        super().__init__(f"A reign cannot end ({end}) before it starts ({start}).")  # noqa: E501


class UnknownReferenceError(HistoryModelError):
    """Raised when a reign or an event names a segment or a company the chronology does not define.

    Attributes:
        kind (str): What is referenced, `segment` or `company`.
        key (str): The unknown key.
    """

    def __init__(self, kind: str, key: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What is referenced.
            key (str): The unknown key.
        """
        self.kind, self.key = kind, key
        super().__init__(f"Unknown {kind} {key!r}: define it in the chronology first.")  # noqa: E501


class DuplicateKeyError(HistoryModelError):
    """Raised when two segments, companies or events share a key.

    Attributes:
        kind (str): What is duplicated.
        key (str): The duplicated key.
    """

    def __init__(self, kind: str, key: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What is duplicated.
            key (str): The duplicated key.
        """
        self.kind, self.key = kind, key
        super().__init__(f"The {kind} key {key!r} is defined twice.")


class OverlappingReignError(HistoryModelError):
    """Raised when two reigns of the same segment overlap in time.

    Attributes:
        segment (str): The segment.
        first (str): The company of the earlier reign.
        second (str): The company of the later reign.
    """

    def __init__(self, segment: str, first: str, second: str) -> None:
        """Initialize the error.

        Args:
            segment (str): The segment.
            first (str): The company of the earlier reign.
            second (str): The company of the later reign.
        """
        self.segment, self.first, self.second = segment, first, second
        super().__init__(f"In {segment!r}, the reign of {second!r} starts before the reign of {first!r} ends.")  # noqa: E501


class InvalidHistoryKeyError(HistoryModelError):
    """Raised when a key or a colour of the chronology is malformed.

    Attributes:
        kind (str): What the value is, e.g. `company key`.
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
        super().__init__(f"The {kind} {value!r} is malformed: {expected} is expected.")  # noqa: E501
