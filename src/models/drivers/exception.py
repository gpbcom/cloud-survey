from __future__ import annotations


class DriverModelError(ValueError):
    """Base class for every driver analysis validation error.

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


class InvalidPeriodError(DriverModelError):
    """Raised when a period is not a quarter written `YYYYQn`.

    Attributes:
        period (str): The rejected period.
    """

    def __init__(self, period: str) -> None:
        """Initialize the error.

        Args:
            period (str): The rejected period.
        """
        self.period = period
        super().__init__(f"A period must be a quarter written YYYYQn, got {period!r}.")


class TargetAmongCriteriaError(DriverModelError):
    """Raised when the target of a driver analysis is also one of its criteria.

    Attributes:
        target (str): The target.
    """

    def __init__(self, target: str) -> None:
        """Initialize the error.

        Args:
            target (str): The target.
        """
        self.target = target
        super().__init__(f"The target {target!r} cannot also be a criterion.")


class InvalidSourceIdentifierError(DriverModelError):
    """Raised when the identifier of a provider at a metric source is malformed (a CIK, a Wikidata item, a repository).

    Attributes:
        kind (str): What the identifier is, e.g. `SEC CIK`.
        value (str): The rejected identifier.
        expected (str): The expected format.
    """

    def __init__(self, kind: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the identifier is.
            value (str): The rejected identifier.
            expected (str): The expected format.
        """
        self.kind, self.value, self.expected = kind, value, expected
        super().__init__(f"The {kind} {value!r} is malformed: {expected} is expected.")


class InvalidFactPeriodError(DriverModelError):
    """Raised when a fact of a source ends before it starts.

    Attributes:
        start (str): The first day of the period.
        end (str): The last day of the period.
    """

    def __init__(self, start: str, end: str) -> None:
        """Initialize the error.

        Args:
            start (str): The first day of the period.
            end (str): The last day of the period.
        """
        self.start, self.end = start, end
        super().__init__(f"A fact cannot end ({end}) before it starts ({start}).")


class UnknownHelpChoiceError(DriverModelError):
    """Raised when an explanation of the driver analysis names a choice no list offers (a scale or a scope).

    Attributes:
        choice (str): The rejected choice.
    """

    def __init__(self, choice: str) -> None:
        """Initialize the error.

        Args:
            choice (str): The rejected choice.
        """
        self.choice = choice
        super().__init__(f"An explained choice must be a metric scale or a driver scope, got {choice!r}.")


class InvalidHelpTextError(DriverModelError):
    """Raised when the text of an explanation of the driver analysis is missing or not a text.

    Attributes:
        field (str): The field of the explanation.
    """

    def __init__(self, field: str) -> None:
        """Initialize the error.

        Args:
            field (str): The field of the explanation.
        """
        self.field = field
        super().__init__(f"The {field} of an explanation must be a non-empty text.")
