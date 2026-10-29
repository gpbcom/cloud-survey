from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.results.fits.estimate import Estimate


class HeapsFit(BaseModel):
    """Heaps' law of a provider (6.8): its distinct categories against its catalogue size, in logarithms.

    Attributes:
        provider (CloudProvider): The provider.
        slope (Optional[Estimate]): The log-log slope (below 1: each new category opens less), `None` with fewer than
            three years.
        intercept (Optional[float]): The log-log intercept.
        r2 (Optional[float]): The share of the variance explained.
        points (List[Tuple[float, float]]): The catalogue size and the distinct categories of each year.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider.")
    slope: Optional[Estimate] = Field(default=None, description="The log-log slope.")
    intercept: Optional[float] = Field(default=None, description="The log-log intercept.")
    r2: Optional[float] = Field(default=None, description="The share of the variance explained.")
    points: List[Tuple[float, float]] = Field(default_factory=list, description="The size and categories by year.")
