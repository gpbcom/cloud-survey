from __future__ import annotations


class StatsModelError(ValueError):
    """Base class for every market statistics validation error.

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


class InvalidShareBandError(StatsModelError):
    """Raised when the low bound of a market share band is above its high bound.

    Attributes:
        low (float): The low bound.
        high (float): The high bound.
    """

    def __init__(self, low: float, high: float) -> None:
        """Initialize the error.

        Args:
            low (float): The low bound.
            high (float): The high bound.
        """
        self.low = low
        self.high = high
        super().__init__(f"The market share band is inverted: {low}% to {high}%.")


class SharesOverflowError(StatsModelError):
    """Raised when the top-level market shares of a report sum to more than 100%.

    Attributes:
        total (float): The sum of the top-level shares.
    """

    def __init__(self, total: float) -> None:
        """Initialize the error.

        Args:
            total (float): The sum of the top-level shares.
        """
        self.total = total
        super().__init__(f"The top-level market shares sum to {total}%, more than 100%.")
