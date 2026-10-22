from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class SelectelMenu(StrEnum):
    """Enums representing the titles of the top entries of the Selectel header menu listing offers.

    Attributes:
        PRODUCTS (str): The products entry (`Продукты`).
        SERVICES (str): The services entry (`Услуги`).
    """

    PRODUCTS = "Продукты"
    SERVICES = "Услуги"


@unique
class SelectelMenuGroup(StrEnum):
    """Enums representing the titles of the Selectel header menu groups which are not catalogue categories.

    Attributes:
        POPULAR (str): The popular products (`Популярные`), a selection of the other groups.
        BUSINESS_TASKS (str): The business tasks (`Бизнес-задачи`), use-case pages.
        INDUSTRIES (str): The industries (`Отрасли`).
    """

    POPULAR = "Популярные"
    BUSINESS_TASKS = "Бизнес-задачи"
    INDUSTRIES = "Отрасли"
