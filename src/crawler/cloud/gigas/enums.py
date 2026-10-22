from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GigasMenuMarkup(StrEnum):
    """Enums representing the HTML markup of the Gigas main menu compared by the crawler.

    Attributes:
        SEGMENT (str): The CSS class of the heading (a link or a label) of a menu column.
        LINK (str): The tag of a menu column heading which is a link.
    """

    SEGMENT = "dropdown-menu-segment"
    LINK = "a"
