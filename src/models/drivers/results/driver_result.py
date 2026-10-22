from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.drivers.query.driver_query import DriverQuery
from models.drivers.results.correlation_cell import CorrelationCell
from models.drivers.results.driver_coefficient import DriverCoefficient
from models.drivers.results.driver_warning import DriverWarning


class DriverResult(BaseModel):
    """What a driver analysis found: the correlations, the regression, the predominant criteria, its caveats.

    Attributes:
        query (DriverQuery): The analysis.
        observations (int): The observations used by the regression (providers, or providers × quarters).
        providers (int): The distinct providers among them.
        r2 (Optional[float]): The share of the variance of the target the criteria explain, `None` without a fit.
        loo_r2 (Optional[float]): The same, each observation predicted by a model fitted without it.
        correlations (List[CorrelationCell]): The correlation of each criterion with the target.
        coefficients (List[DriverCoefficient]): The regression, the most important criterion first.
        warnings (List[DriverWarning]): What limits the conclusions (few observations, collinear criteria…).
    """

    model_config = ConfigDict(frozen=True)

    query: DriverQuery = Field(description="The analysis.")
    observations: int = Field(default=0, ge=0, description="The observations of the regression.")
    providers: int = Field(default=0, ge=0, description="The distinct providers.")
    r2: Optional[float] = Field(default=None, description="The explained share of the variance.")
    loo_r2: Optional[float] = Field(default=None, description="The leave-one-out explained share.")
    correlations: List[CorrelationCell] = Field(default_factory=list, description="The correlations.")
    coefficients: List[DriverCoefficient] = Field(default_factory=list, description="The regression.")
    warnings: List[DriverWarning] = Field(default_factory=list, description="What limits the conclusions.")
