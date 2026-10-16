from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class FlagDesign(BaseModel):
    """Simplified design of a national flag, drawn in a 3:2 rectangle.

    The layers are drawn in this order: the bands, the canton, the saltire, the cross and the stars.

    Attributes:
        bands (List[str]): The colours of the bands, a single one for a plain field.
        weights (List[int]): The relative size of each band, equal bands when empty.
        vertical (bool): Whether the bands are vertical (France) rather than horizontal (Germany).
        canton (Optional[str]): The colour of the upper hoist rectangle (United States).
        canton_bands (int): How many bands the canton covers, from the top.
        saltire (Optional[str]): The colour of the diagonal cross (United Kingdom).
        saltire_inner (Optional[str]): The colour of the thinner diagonal cross drawn over the saltire.
        cross (Optional[str]): The colour of the centred cross (Switzerland, United Kingdom).
        cross_width (float): The width of the cross arms, as a fraction of the flag height.
        cross_length (Optional[float]): The length of the cross arms, as a fraction of the flag height. `None` for a
            cross reaching the flag edges.
        cross_inner (Optional[str]): The colour of the thinner centred cross drawn over the cross.
        cross_inner_width (float): The width of the inner cross arms, as a fraction of the flag height.
        stars (Optional[str]): The colour of the large star and the 4 small stars of the upper hoist (China).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bands: List[str] = Field(min_length=1, description="The colours of the bands, a single one for a plain field.")
    weights: List[int] = Field(default_factory=list, description="The relative size of each band.")
    vertical: bool = Field(default=False, description="Whether the bands are vertical.")
    canton: Optional[str] = Field(default=None, description="The colour of the upper hoist rectangle.")
    canton_bands: int = Field(default=0, ge=0, description="How many bands the canton covers, from the top.")
    saltire: Optional[str] = Field(default=None, description="The colour of the diagonal cross.")
    saltire_inner: Optional[str] = Field(default=None, description="The colour of the thinner diagonal cross.")
    cross: Optional[str] = Field(default=None, description="The colour of the centred cross.")
    cross_width: float = Field(default=0.2, gt=0, le=1, description="The width of the cross arms.")
    cross_length: Optional[float] = Field(default=None, gt=0, le=1, description="The length of the cross arms.")
    cross_inner: Optional[str] = Field(default=None, description="The colour of the thinner centred cross.")
    cross_inner_width: float = Field(default=0.1, gt=0, le=1, description="The width of the inner cross arms.")
    stars: Optional[str] = Field(default=None, description="The colour of the stars of the upper hoist.")
