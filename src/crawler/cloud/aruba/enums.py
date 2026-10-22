from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ArubaPricingCardName(StrEnum):
    """Enums representing the Aruba Cloud pricing card names of the products the menu names otherwise.

    Attributes:
        SERVER_BARE_METAL (str): The bare metal servers card, the menu `Dedicated Servers`.
        VIRTUAL_PRIVATE_SERVERS (str): The virtual private servers card.
        BACKUP_AGENTLESS (str): The agentless backup card.
        DISASTER_RECOVERY (str): The disaster recovery as a service card, the menu `Disaster Recovery for VMware`.
        CLOUD_BARE_METAL_BACKUP (str): The bare metal backup card, the menu `Backup for VMware`.
        AI_TOOLS_TEXT_MANAGEMENT (str): The text management AI tools card, the menu `AI Tools`.
    """

    SERVER_BARE_METAL = "Server Bare Metal"
    VIRTUAL_PRIVATE_SERVERS = "VPS - Virtual Private Servers"
    BACKUP_AGENTLESS = "Backup Agentless"
    DISASTER_RECOVERY = "Disaster Recovery (DRaaS)"
    CLOUD_BARE_METAL_BACKUP = "Cloud Bare Metal Backup"
    AI_TOOLS_TEXT_MANAGEMENT = "AI Tools - Text Management"


@unique
class ArubaMenuMarkup(StrEnum):
    """Enums representing the HTML markup of the Aruba Cloud products menu compared by the crawler.

    Attributes:
        LIST_ITEM (str): The tag of the menu items.
        NAV_ITEM (str): The CSS class of the menu items, whose links label the menu groups.
    """

    LIST_ITEM = "li"
    NAV_ITEM = "nav-item"
