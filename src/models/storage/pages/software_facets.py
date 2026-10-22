from __future__ import annotations

# Standard Library Imports.
from typing import Dict

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.cloud.enums import CloudProvider, DeliveryMethod, SoftwareCategory


class SoftwareFacets(BaseModel):
    """The counts of the stored software matching a query, by facet, computed by the server.

    Attributes:
        total (int): The number of matching software.
        by_provider (Dict[CloudProvider, int]): The matching software of each cloud provider.
        by_category (Dict[SoftwareCategory, int]): The matching software meant for each audience (a software may be
            meant for several).
        by_domain (Dict[str, int]): The matching software of each taxonomy domain (a software may be in several).
        by_domain_and_category (Dict[str, Dict[SoftwareCategory, int]]): The matching software of each taxonomy
            domain meant for each audience.
        by_delivery (Dict[DeliveryMethod, int]): The matching software delivered each way.
        by_publisher (Dict[str, int]): The matching software of the most frequent publishers (counted on request).
    """

    total: int = Field(default=0, ge=0, description="The number of matching software.")
    by_provider: Dict[CloudProvider, int] = Field(default_factory=dict, description="The software by provider.")
    by_category: Dict[SoftwareCategory, int] = Field(default_factory=dict, description="The software by audience.")
    by_domain: Dict[str, int] = Field(default_factory=dict, description="The software by taxonomy domain.")
    by_domain_and_category: Dict[str, Dict[SoftwareCategory, int]] = Field(
        default_factory=dict, description="The software by taxonomy domain and audience."
    )
    by_delivery: Dict[DeliveryMethod, int] = Field(default_factory=dict, description="The software by delivery.")
    by_publisher: Dict[str, int] = Field(default_factory=dict, description="The software by publisher.")
