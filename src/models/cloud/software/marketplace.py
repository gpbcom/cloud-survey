from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, Field, computed_field

# First Party Imports.
from models.cloud.enums import CloudProvider, Country
from models.cloud.software.marketplace_software import MarketplaceSoftware


class CloudMarketplace(BaseModel):
    """Software listed in the marketplace of a cloud provider, as crawled at a given time.

    Attributes:
        provider (CloudProvider): The cloud provider.
        crawled_at (AwareDatetime): When the marketplace was crawled, timezone-aware.
        software (List[MarketplaceSoftware]): The marketplace software.
        in_progress (bool): Whether the crawl is still running: the file then holds the items crawled so far.
        country (Country): The country of the cloud provider, derived from it: written to the marketplace files and
            ignored when they are read.
    """

    provider: CloudProvider = Field(description="The cloud provider.")
    crawled_at: AwareDatetime = Field(description="When the marketplace was crawled, timezone-aware.")
    software: List[MarketplaceSoftware] = Field(default_factory=list, description="The marketplace software.")
    in_progress: bool = Field(
        default=False, description="Whether the crawl is still running: the file then holds the items crawled so far."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def country(self) -> Country:
        """Get the country of the cloud provider.

        Returns:
            Country: The country where the cloud provider is headquartered.
        """
        return self.provider.country

    @property
    def size(self) -> int:
        """Get the number of software still listed by the website.

        Returns:
            int: The number of software without a deletion date, not serialized.
        """
        return sum(1 for item in self.software if not item.is_deleted)
