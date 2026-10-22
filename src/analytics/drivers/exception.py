from __future__ import annotations

# Standard Library Imports.
from pathlib import Path


class DriverAnalysisError(Exception):
    """Base class for every error of the "Rise drivers" analysis.

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


class MetricCatalogFileError(DriverAnalysisError):
    """Raised when the catalogue of the criteria cannot be loaded.

    Attributes:
        path (Path): The catalogue file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The catalogue file.
            reason (str): Why it cannot be loaded.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The metric catalogue {path} cannot be loaded: {reason}")


class InvalidQuarterError(DriverAnalysisError):
    """Raised when a quarter is not written `YYYYQn`.

    Attributes:
        period (str): The rejected quarter.
    """

    def __init__(self, period: str) -> None:
        """Initialize the error.

        Args:
            period (str): The rejected quarter.
        """
        self.period = period
        super().__init__(f"A quarter must be written YYYYQn, got {period!r}.")


class DriverHelpFileError(DriverAnalysisError):
    """Raised when the explanations of the driver analysis cannot be loaded.

    Attributes:
        path (Path): The explanations file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The explanations file.
            reason (str): Why it cannot be loaded.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The driver explanations {path} cannot be loaded: {reason}")
