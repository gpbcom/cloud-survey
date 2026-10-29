from __future__ import annotations


class CompaniesAnalyticsError(Exception):
    """Base class for every error of the companies analytics (the collector of the companies crawl).

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


class CompaniesCollectorError(CompaniesAnalyticsError):
    """Raised when the collector refuses to write: what it was given would delete stored data.

    Attributes:
        reason (str): Why.
    """

    def __init__(self, reason: str) -> None:
        """Initialize the error.

        Args:
            reason (str): Why.
        """
        self.reason = reason
        super().__init__(f"The companies collector refuses to write: {reason}")
