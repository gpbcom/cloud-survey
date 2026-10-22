from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.software.marketplace_software import MarketplaceSoftware


@dataclass(frozen=True)
class SoftwareRow:
    """A marketplace software of the table, with its marketplace context.

    Attributes:
        provider (CloudProvider): The cloud provider of the marketplace.
        software (MarketplaceSoftware): The software.
        crawled_at (Optional[datetime]): When the marketplace was last crawled, `None` when unknown.
        id (int): The storage identifier of the software.
    """

    provider: CloudProvider
    software: MarketplaceSoftware
    crawled_at: Optional[datetime]
    id: int = 0
