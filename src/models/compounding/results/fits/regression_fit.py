from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import FitKind, FoundationSource, Specification
from models.compounding.results.fits.estimate import Estimate


class RegressionFit(BaseModel):
    """A logit fit of the yearly entry of providers into categories.

    Attributes:
        kind (FitKind): The density model (6.5) or the foundation hazard (6.13).
        provider (Optional[CloudProvider]): The provider fitted, `None` for the pooled fit.
        specification (Specification): The controls held constant.
        lag (int): The years the foundations are held before the entry (hazard only).
        source (FoundationSource): Where the foundations come from (hazard only).
        rows (int): The provider-category-years at risk fitted.
        events (int): The entries among them.
        converged (bool): Whether the fit converged.
        log_likelihood (Optional[float]): Its log-likelihood.
        estimates (List[Estimate]): The coefficients, the intercept excluded.
    """

    model_config = ConfigDict(frozen=True)

    kind: FitKind = Field(description="The model.")
    provider: Optional[CloudProvider] = Field(default=None, description="The provider fitted.")
    specification: Specification = Field(description="The controls held constant.")
    lag: int = Field(default=1, ge=0, le=5, description="The years the foundations are held.")
    source: FoundationSource = Field(default=FoundationSource.CURATED, description="Where the foundations come from.")
    rows: int = Field(ge=0, description="The rows fitted.")
    events: int = Field(ge=0, description="The entries among them.")
    converged: bool = Field(description="Whether the fit converged.")
    log_likelihood: Optional[float] = Field(default=None, description="Its log-likelihood.")
    estimates: List[Estimate] = Field(default_factory=list, description="The coefficients.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def estimate(self, name: str) -> Optional[Estimate]:
        """Get a coefficient.

        Args:
            name (str): The coefficient.

        Returns:
            Optional[Estimate]: The coefficient, `None` when not fitted.
        """
        return next((estimate for estimate in self.estimates if estimate.name == name), None)
