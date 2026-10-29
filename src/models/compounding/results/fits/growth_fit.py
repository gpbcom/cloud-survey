from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import CurveKind
from models.compounding.results.fits.curve_fit import CurveFit
from models.compounding.results.fits.estimate import Estimate


class GrowthFit(BaseModel):
    """How a provider's catalogue grows: the linear launch rate (6.6) and the growth curves (6.7).

    Attributes:
        provider (CloudProvider): The provider.
        years (int): The years fitted.
        linear (List[Estimate]): The coefficients of the yearly launches on the catalogue size of the year before
            (`size`), the market share (`share`, specification S2) and the growth of the cloud market (`market`).
        r2 (Optional[float]): The share of the variance of the launches explained.
        curves (List[CurveFit]): The growth curves fitted to the catalogue size.
        best (Optional[CurveKind]): The curve with the lowest AIC.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider.")
    years: int = Field(ge=0, description="The years fitted.")
    linear: List[Estimate] = Field(default_factory=list, description="The linear-rate coefficients.")
    r2: Optional[float] = Field(default=None, description="The share of the variance explained.")
    curves: List[CurveFit] = Field(default_factory=list, description="The growth curves.")
    best: Optional[CurveKind] = Field(default=None, description="The curve with the lowest AIC.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def estimate(self, name: str) -> Optional[Estimate]:
        """Get a linear-rate coefficient.

        Args:
            name (str): The coefficient.

        Returns:
            Optional[Estimate]: The coefficient, `None` when not fitted.
        """
        return next((estimate for estimate in self.linear if estimate.name == name), None)
