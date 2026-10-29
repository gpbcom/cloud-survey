from __future__ import annotations


class LlmCallError(ValueError):
    """Base class for every error raised by the recorded language model calls.

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


class InvalidLlmCallValueError(LlmCallError):
    """Raised when a field of a recorded language model call is not valid.

    Attributes:
        field (str): The field.
        value (str): The invalid value, as text.
        expected (str): What the field must hold.
    """

    def __init__(self, field: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            field (str): The field.
            value (str): The invalid value, as text.
            expected (str): What the field must hold.
        """
        self.field = field
        self.value = value
        self.expected = expected
        super().__init__(f"The {field} of a language model call is {value!r}: expected {expected}.")
