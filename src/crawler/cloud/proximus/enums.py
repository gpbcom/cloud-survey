from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ProximusPageKind(StrEnum):
    """Enums representing the kinds of the Proximus website pages, read from their page identifier (`id_<kind>_`).

    Attributes:
        CATEGORY (str): A category page (`id_catl_`), listing products and sub-categories.
    """

    CATEGORY = "catl"
