from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from pathlib import Path


class LLMError(Exception):
    """Base class for every error of the language model layer.

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


class LLMConfigurationFileError(LLMError):
    """Raised when the language model settings file cannot be loaded.

    Attributes:
        path (Path): The settings file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The settings file.
            reason (str): Why it cannot be loaded.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The language model settings {path} cannot be loaded: {reason}.")


class UnsupportedLLMProviderError(LLMError):
    """Raised when a model names a provider no client is built for.

    Attributes:
        provider (str): The provider.
    """

    def __init__(self, provider: str) -> None:
        """Initialize the error.

        Args:
            provider (str): The provider.
        """
        self.provider = provider
        super().__init__(f"No language model client for the provider {provider!r}.")


class LLMBudgetExceededError(LLMError):
    """Raised when the language model calls already spent their budget.

    Attributes:
        spent (Decimal): What the recorded calls cost.
        ceiling (Decimal): The budget ceiling.
        currency (str): The currency of both.
    """

    def __init__(self, spent: Decimal, ceiling: Decimal, currency: str) -> None:
        """Initialize the error.

        Args:
            spent (Decimal): What the recorded calls cost.
            ceiling (Decimal): The budget ceiling.
            currency (str): The currency of both.
        """
        self.spent = spent
        self.ceiling = ceiling
        self.currency = currency
        super().__init__(f"The language model budget is spent: {spent:.4f} of {ceiling:.2f} {currency}.")


class LLMResponseError(LLMError):
    """Raised when a language model answer cannot be used (refused, truncated or not of the expected shape).

    Attributes:
        task (str): The task of the call.
        reason (str): Why the answer cannot be used.
    """

    def __init__(self, task: str, reason: str) -> None:
        """Initialize the error.

        Args:
            task (str): The task of the call.
            reason (str): Why the answer cannot be used.
        """
        self.task = task
        self.reason = reason
        super().__init__(f"The {task} answer cannot be used: {reason}.")
