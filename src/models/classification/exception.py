from __future__ import annotations

# Standard Library Imports.
from typing import List


class ClassificationModelError(ValueError):
    """Base class for every classification rules validation error.

    It is a `ValueError`, so pydantic reports it as a `ValidationError` when raised by a validator.

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


class InvalidRulePatternError(ClassificationModelError):
    """Raised when a rule pattern is not a valid regular expression.

    Attributes:
        pattern (str): The rejected pattern.
        reason (str): Why the pattern is invalid.
    """

    def __init__(self, pattern: str, reason: str) -> None:
        """Initialize the error.

        Args:
            pattern (str): The rejected pattern.
            reason (str): Why the pattern is invalid.
        """
        self.pattern = pattern
        self.reason = reason
        super().__init__(f"The rule pattern {pattern!r} is not a valid regular expression ({reason}).")


class IncompleteRulesError(ClassificationModelError):
    """Raised when a mapping of the rules does not cover every value of its enum.

    Attributes:
        field (str): The incomplete mapping.
        missing (List[str]): The values without an entry.
    """

    def __init__(self, field: str, missing: List[str]) -> None:
        """Initialize the error.

        Args:
            field (str): The incomplete mapping.
            missing (List[str]): The values without an entry.
        """
        self.field = field
        self.missing = missing
        super().__init__(f"The `{field}` rules have no entry for: {', '.join(missing)}.")
