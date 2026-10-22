from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import List


class TaxonomyError(Exception):
    """Base class for every error of the unified taxonomy.

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


class TaxonomySeedFileError(TaxonomyError):
    """Raised when a taxonomy seed file cannot be loaded.

    Attributes:
        path (Path): The seed file.
        reason (str): Why it cannot be loaded.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Initialize the error.

        Args:
            path (Path): The seed file.
            reason (str): Why it cannot be loaded.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"The taxonomy seed {path} cannot be loaded: {reason}")


class UnknownTaxonomySlugError(TaxonomyError):
    """Raised when rules or seeds name taxonomy nodes which do not exist.

    Attributes:
        problems (List[str]): Where each unknown slug is named.
    """

    def __init__(self, problems: List[str]) -> None:
        """Initialize the error.

        Args:
            problems (List[str]): Where each unknown slug is named.
        """
        self.problems = problems
        super().__init__(f"The taxonomy does not match its rules and seeds: {'. '.join(problems)}.")
