from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CombellCssClass(StrEnum):
    """Enums representing the CSS classes of the Combell elements giving the category of the links they hold.

    Attributes:
        MENU_ITEM (str): A main menu item.
        CARD_BODY (str): An IT solutions card of the managed services page.
    """

    MENU_ITEM = "menu__item"
    CARD_BODY = "card-body"


@unique
class CombellCategorySlug(StrEnum):
    """Enums representing the identifiers of the Combell marketplace categories.

    Attributes:
        CMS (str): The content management systems, the slug of the CMS hosting page.
    """

    CMS = "cms"


@unique
class CombellBadge(StrEnum):
    """Enums representing the texts of the badges of the Combell marketplace cards, matched case-insensitively.

    Attributes:
        ONE_CLICK (str): The "One-click install" badge.
    """

    ONE_CLICK = "one-click"
