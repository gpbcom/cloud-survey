from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import ValueOrigin


class YearValue(BaseModel):
    """A yearly input of the compounding models: a provider's market share, or the market size.

    Attributes:
        provider (Optional[CloudProvider]): The provider of a share, `None` for the market size.
        year (int): The year.
        value (float): The share (%) or the size (billion USD).
        origin (ValueOrigin): Where it comes from.
        perimeter_break (bool): Whether the source measured another perimeter that year (an older methodology).
    """

    model_config = ConfigDict(frozen=True)

    provider: Optional[CloudProvider] = Field(default=None, description="The provider of a share.")
    year: int = Field(ge=1950, le=2100, description="The year.")
    value: float = Field(ge=0, description="The share or the size.")
    origin: ValueOrigin = Field(description="Where it comes from.")
    perimeter_break: bool = Field(default=False, description="Whether another perimeter was measured.")
