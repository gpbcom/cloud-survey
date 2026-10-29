from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.compounding.enums import CurveKind
from models.compounding.results.fits.estimate import Estimate


class CurveFit(BaseModel):
    """A growth curve fitted to a provider's yearly catalogue size.

    Attributes:
        kind (CurveKind): The curve.
        aic (Optional[float]): Its Akaike information criterion (lower is better), `None` when it did not fit.
        parameters (List[Estimate]): Its parameters.
        points (List[Tuple[int, float]]): The fitted catalogue size of each year.
    """

    model_config = ConfigDict(frozen=True)

    kind: CurveKind = Field(description="The curve.")
    aic: Optional[float] = Field(default=None, description="Its Akaike information criterion.")
    parameters: List[Estimate] = Field(default_factory=list, description="Its parameters.")
    points: List[Tuple[int, float]] = Field(default_factory=list, description="The fitted size of each year.")
