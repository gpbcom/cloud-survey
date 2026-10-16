from __future__ import annotations


class CloudModelError(ValueError):
    """Base class for every cloud model validation error.

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


class InvalidPricingPolicyError(CloudModelError):
    """Raised when the pricing policy is not a known `PricingPolicy`.

    Attributes:
        value (str): The rejected pricing policy.
    """

    def __init__(self, value: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected pricing policy.
        """
        self.value = value
        super().__init__(f"The pricing policy is invalid: {value!r}.")


class NegativeAmountError(CloudModelError):
    """Raised when the amount or the free limit is negative.

    Attributes:
        value (float): The rejected amount.
    """

    def __init__(self, value: float) -> None:
        """Initialize the error.

        Args:
            value (float): The rejected amount.
        """
        self.value = value
        super().__init__(f"The amount and free_limit must be greater than or equal to 0 (got {value}).")


class EmptyCurrencyError(CloudModelError):
    """Raised when the currency symbol is empty."""

    def __init__(self) -> None:
        """Initialize the error."""
        super().__init__("The currency symbol cannot be empty.")


class EmptyMandatoryFieldError(CloudModelError):
    """Raised when the product name or description is blank."""

    def __init__(self) -> None:
        """Initialize the error."""
        super().__init__("The name or description field(s) cannot be empty.")


class MissingPricingPolicyError(CloudModelError):
    """Raised when the product pricing policies are missing."""

    def __init__(self) -> None:
        """Initialize the error."""
        super().__init__("The pricing policy cannot be empty.")


class InvalidProductUrlError(CloudModelError):
    """Raised when the product URL is not an absolute http(s) link.

    Attributes:
        value (str): The rejected URL.
    """

    def __init__(self, value: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected URL.
        """
        self.value = value
        super().__init__(f"The product URL must be an absolute http(s) link (got {value!r}).")


class InvalidDateError(CloudModelError):
    """Raised when a date is neither an ISO 8601 date nor a Unix timestamp.

    Attributes:
        value (str): The rejected date.
    """

    def __init__(self, value: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected date.
        """
        self.value = value
        super().__init__(f"The date must be an ISO 8601 date or a Unix timestamp (got {value!r}).")
