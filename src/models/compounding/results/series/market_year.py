from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.compounding.enums import ValueOrigin


class MarketYear(BaseModel):
    """The worldwide cloud infrastructure services market in a year.

    Attributes:
        year (int): The year.
        size_bn (Optional[float]): Its size (billion USD), `None` when unknown.
        origin (ValueOrigin): Where the size comes from.
        growth (Optional[float]): The growth of its logarithm since the year before.
        perimeter_break (bool): Whether the source measured another perimeter that year.
    """

    model_config = ConfigDict(frozen=True)

    year: int = Field(ge=1950, le=2100, description="The year.")
    size_bn: Optional[float] = Field(default=None, ge=0, description="Its size.")
    origin: ValueOrigin = Field(default=ValueOrigin.NONE, description="Where the size comes from.")
    growth: Optional[float] = Field(default=None, description="The growth of its logarithm.")
    perimeter_break: bool = Field(default=False, description="Whether another perimeter was measured.")
