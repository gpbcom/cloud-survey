from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider


class PlaceboResult(BaseModel):
    """The placebo test of the foundation coefficient: random foundation sets of the same sizes.

    Attributes:
        provider (Optional[CloudProvider]): The provider fitted, `None` for the pooled fit.
        real (float): The foundation coefficient with the real foundation sets.
        draws (List[float]): The coefficient with each random set (fits that converged only).
        p_value (Optional[float]): The share of the random sets doing at least as well, `None` without draws.
    """

    model_config = ConfigDict(frozen=True)

    provider: Optional[CloudProvider] = Field(default=None, description="The provider fitted.")
    real: float = Field(description="The coefficient with the real foundation sets.")
    draws: List[float] = Field(default_factory=list, description="The coefficient with each random set.")
    p_value: Optional[float] = Field(default=None, ge=0, le=1, description="The share doing at least as well.")
