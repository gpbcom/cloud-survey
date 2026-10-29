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


class InvalidLaunchFieldError(CloudModelError):
    """Raised when a field of the launch dates catalogue is not what is expected.

    Attributes:
        field (str): The field.
        value (str): The rejected value.
        expected (str): What the field expects.
    """

    def __init__(self, field: str, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            field (str): The field.
            value (str): The rejected value.
            expected (str): What the field expects.
        """
        self.field, self.value, self.expected = field, value, expected
        super().__init__(f"The launch {field} must be {expected} (got {value!r}).")


class MissingLaunchSourceError(CloudModelError):
    """Raised when a curated launch date does not cite its source.

    Attributes:
        name (str): The product.
    """

    def __init__(self, name: str) -> None:
        """Initialize the error.

        Args:
            name (str): The product.
        """
        self.name = name
        super().__init__(f"The launch date of {name!r} must cite its source (an announcement URL).")


class MissingLaunchReasonError(CloudModelError):
    """Raised when a product of the launch dates catalogue has neither a launch date nor the reason why.

    Attributes:
        name (str): The product.
    """

    def __init__(self, name: str) -> None:
        """Initialize the error.

        Args:
            name (str): The product.
        """
        self.name = name
        super().__init__(f"The product {name!r} has no launch date: the reason why must be given.")


class DuplicateLaunchEntryError(CloudModelError):
    """Raised when the launch dates catalogue lists a product twice for the same crawler.

    Attributes:
        crawler (str): The crawler.
        name (str): The product.
    """

    def __init__(self, crawler: str, name: str) -> None:
        """Initialize the error.

        Args:
            crawler (str): The crawler.
            name (str): The product.
        """
        self.crawler, self.name = crawler, name
        super().__init__(f"The {crawler} product {name!r} is listed twice in the launch dates catalogue.")

