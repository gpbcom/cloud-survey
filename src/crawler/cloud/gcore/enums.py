from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GcoreMenuTab(StrEnum):
    """Enums representing the Gcore products menu tabs listing use cases, not products (case-folded labels).

    Attributes:
        BY_INDUSTRY (str): The use cases by industry tab.
        BY_NEED (str): The use cases by need tab.
    """

    BY_INDUSTRY = "by industry"
    BY_NEED = "by need"
