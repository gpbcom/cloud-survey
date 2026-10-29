from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider


class ProviderCoverage(BaseModel):
    """What the database holds for a provider analysed.

    Attributes:
        provider (CloudProvider): The provider.
        excluded (bool): Whether it is outside the public-cloud scope (fitted apart).
        products (int): Its dated products in the cloud computing domains.
        held (int): Those held at the start of the window (dated "on or before").
        first (Optional[int]): The first year of its window.
        last (Optional[int]): The last year of its window.
        categories (int): The distinct categories it offers at the end.
        events (int): The categories it entered inside the window.
        share_years (int): The years of its window with a market share.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider.")
    excluded: bool = Field(default=False, description="Whether it is fitted apart.")
    products: int = Field(ge=0, description="Its dated products kept.")
    held: int = Field(ge=0, description="Those held at the start.")
    first: Optional[int] = Field(default=None, description="The first year of its window.")
    last: Optional[int] = Field(default=None, description="The last year of its window.")
    categories: int = Field(ge=0, description="The distinct categories offered at the end.")
    events: int = Field(ge=0, description="The categories entered inside the window.")
    share_years: int = Field(ge=0, description="The years with a market share.")
