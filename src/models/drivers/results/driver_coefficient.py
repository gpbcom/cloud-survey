from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.drivers.enums import ProviderMetric


class DriverCoefficient(BaseModel):
    """What a criterion weighs in the regression of the target.

    Attributes:
        criterion (ProviderMetric): The criterion.
        beta (float): Its standardized coefficient (standard deviations of the target per standard deviation).
        low (Optional[float]): The lower bound of its 95% interval.
        high (Optional[float]): The upper bound of its 95% interval.
        p_value (Optional[float]): Its p-value, `None` without enough degrees of freedom.
        importance (float): Its share of the explained variance (Shapley decomposition of R², the shares summing
            to R²).
        importance_low (Optional[float]): The lower bound of its importance (bootstrap).
        importance_high (Optional[float]): The upper bound of its importance (bootstrap).
        granger_p (Optional[float]): The p-value of the test that it leads the target (panel only).
    """

    model_config = ConfigDict(frozen=True)

    criterion: ProviderMetric = Field(description="The criterion.")
    beta: float = Field(description="Its standardized coefficient.")
    low: Optional[float] = Field(default=None, description="The lower bound of its interval.")
    high: Optional[float] = Field(default=None, description="The upper bound of its interval.")
    p_value: Optional[float] = Field(default=None, ge=0, le=1, description="Its p-value.")
    importance: float = Field(ge=0, description="Its share of the explained variance.")
    importance_low: Optional[float] = Field(default=None, description="The lower bound of its importance.")
    importance_high: Optional[float] = Field(default=None, description="The upper bound of its importance.")
    granger_p: Optional[float] = Field(default=None, ge=0, le=1, description="The p-value that it leads the target.")
