from __future__ import annotations


class CuratedError(Exception):
    """Base class for every error of the curated catalogues (the bundle and its assembly).

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


class CuratedBundleError(CuratedError):
    """Raised when a file of the curated bundle cannot be read or written, or is invalid.

    Attributes:
        path (str): The file.
        reason (str): Why.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The file.
            reason (str): Why.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The curated bundle file {path} is unusable: {reason}")


class CuratedCatalogError(CuratedError):
    """Raised when the curated rows do not assemble into a valid catalogue.

    Attributes:
        catalog (str): The catalogue (chronology, markets, companies, figures, launches).
        reason (str): Why.
    """

    def __init__(self, catalog: str, reason: str) -> None:
        """Initialize the error.

        Args:
            catalog (str): The catalogue.
            reason (str): Why.
        """
        self.catalog = catalog
        self.reason = reason
        super().__init__(f"The curated {catalog} catalogue cannot be assembled: {reason}")
