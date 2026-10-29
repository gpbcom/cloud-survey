from __future__ import annotations


class CompoundingError(Exception):
    """Base class for every error of the service-compounding analysis.

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


class CompoundingFileError(CompoundingError):
    """Raised when the compounding configuration or its help file cannot be read or is invalid.

    Attributes:
        path (str): The file.
        reason (str): What is wrong with it.
    """

    def __init__(self, path: str, reason: str) -> None:
        """Initialize the error.

        Args:
            path (str): The file.
            reason (str): What is wrong with it.
        """
        self.path, self.reason = path, reason
        super().__init__(f"The compounding file {path} is unusable: {reason}")


class UnknownCompoundingSlugError(CompoundingError):
    """Raised when the compounding configuration names a domain or a category missing from the taxonomy.

    Attributes:
        kind (str): What the slug is, e.g. `domain`.
        slug (str): The unknown slug.
    """

    def __init__(self, kind: str, slug: str) -> None:
        """Initialize the error.

        Args:
            kind (str): What the slug is.
            slug (str): The unknown slug.
        """
        self.kind, self.slug = kind, slug
        super().__init__(f"The {kind} {slug!r} of the compounding configuration is not in the taxonomy.")
