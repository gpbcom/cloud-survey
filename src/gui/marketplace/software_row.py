from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass, field
from datetime import datetime

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.marketplace_software import MarketplaceSoftware


@dataclass(frozen=True)
class SoftwareRow:
    """A marketplace software of the table, with its marketplace context.

    Attributes:
        provider (CloudProvider): The cloud provider of the marketplace.
        software (MarketplaceSoftware): The software.
        crawled_at (datetime): When the marketplace was crawled.
        haystack (str): The case-folded name, description and publisher, searched by the filter.
    """

    provider: CloudProvider
    software: MarketplaceSoftware
    crawled_at: datetime
    haystack: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute the searched text once, the table holding up to a hundred thousand rows."""
        texts = (self.software.name, self.software.description, self.software.publisher or "")
        object.__setattr__(self, "haystack", "\n".join(texts).casefold())
