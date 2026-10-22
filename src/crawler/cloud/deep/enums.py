from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class DEEPMenuGroup(StrEnum):
    """Enums representing the DEEP services menu groups which are not categories.

    Attributes:
        OUR_SERVICES (str): The SME packs group.
    """

    OUR_SERVICES = "Our Services"
