from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import ValueOrigin


class ProviderYear(BaseModel):
    """A provider's cloud catalogue in a year.

    Attributes:
        provider (CloudProvider): The provider.
        year (int): The year.
        size (int): The products offered at the end of the year (held ones included).
        launches (int): The products launched during the year.
        categories (int): The distinct cloud computing categories offered at the end of the year.
        share (Optional[float]): Its share of the cloud market (%), `None` when unknown.
        share_origin (ValueOrigin): Where the share comes from.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider.")
    year: int = Field(ge=1950, le=2100, description="The year.")
    size: int = Field(ge=0, description="The products offered at the end of the year.")
    launches: int = Field(ge=0, description="The products launched during the year.")
    categories: int = Field(ge=0, description="The distinct categories offered.")
    share: Optional[float] = Field(default=None, ge=0, le=100, description="Its share of the cloud market.")
    share_origin: ValueOrigin = Field(default=ValueOrigin.NONE, description="Where the share comes from.")
