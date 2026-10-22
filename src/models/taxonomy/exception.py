from __future__ import annotations

# Standard Library Imports.
from typing import List


class TaxonomyModelError(ValueError):
    """Base class for every taxonomy validation error.

    Attributes:
        message (str): Human-readable description of the error.

    Notes:
        It is a `ValueError`, so pydantic reports it as a `ValidationError` when raised by a validator.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class InvalidSlugError(TaxonomyModelError):
    """Raised when a taxonomy slug is not a kebab-case identifier.

    Attributes:
        slug (str): The rejected slug.
    """

    def __init__(self, slug: str) -> None:
        """Initialize the error.

        Args:
            slug (str): The rejected slug.
        """
        self.slug = slug
        super().__init__(f"The taxonomy slug {slug!r} is not a kebab-case identifier (e.g. `object-storage`).")


class InvalidTaxonomyTreeError(TaxonomyModelError):
    """Raised when the taxonomy nodes do not form domains holding categories.

    Attributes:
        problems (List[str]): What is wrong with the tree.
    """

    def __init__(self, problems: List[str]) -> None:
        """Initialize the error.

        Args:
            problems (List[str]): What is wrong with the tree.
        """
        self.problems = problems
        super().__init__(f"The taxonomy is invalid: {'. '.join(problems)}.")
