from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.drivers.enums import ProviderMetric


class CorrelationCell(BaseModel):
    """The rank correlation of a criterion with the target.

    Attributes:
        criterion (ProviderMetric): The criterion.
        rho (float): The Spearman correlation, from -1 to 1.
        low (Optional[float]): The lower bound of its 95% bootstrap interval.
        high (Optional[float]): The upper bound of its 95% bootstrap interval.
        p_value (float): Its p-value.
        q_value (float): Its Benjamini-Hochberg q-value (the criteria tested together).
        partial (Optional[float]): The correlation once the controls are held constant, `None` without controls.
        observations (int): The observations holding both measures.
        granger_p (Optional[float]): The p-value of the test that the criterion leads the target, panel only (`None`
            on the latest quarter, or without enough history).
    """

    model_config = ConfigDict(frozen=True)

    criterion: ProviderMetric = Field(description="The criterion.")
    rho: float = Field(ge=-1, le=1, description="The Spearman correlation.")
    low: Optional[float] = Field(default=None, description="The lower bound of its interval.")
    high: Optional[float] = Field(default=None, description="The upper bound of its interval.")
    p_value: float = Field(ge=0, le=1, description="Its p-value.")
    q_value: float = Field(ge=0, le=1, description="Its Benjamini-Hochberg q-value.")
    partial: Optional[float] = Field(default=None, description="The correlation with the controls held constant.")
    observations: int = Field(ge=0, description="The observations holding both measures.")
    granger_p: Optional[float] = Field(default=None, ge=0, le=1, description="The p-value that it leads the target.")
