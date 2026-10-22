from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GithubField(StrEnum):
    """Enums representing the fields of a GitHub repository document read by the crawler.

    Attributes:
        STARS (str): The stars of the repository.
    """

    STARS = "stargazers_count"
