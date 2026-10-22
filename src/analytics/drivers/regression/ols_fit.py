from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from typing import Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray


@dataclass(frozen=True)
class OlsFit:
    """A least-squares fit of the standardized target on the standardized criteria.

    Attributes:
        beta (NDArray[numpy.float64]): The standardized coefficient of each criterion.
        low (NDArray[numpy.float64]): The lower bound of the 95% interval of each (`NaN` without degrees of freedom).
        high (NDArray[numpy.float64]): The upper bound of the 95% interval of each (`NaN` without degrees of freedom).
        p_values (NDArray[numpy.float64]): The p-value of each (`NaN` without degrees of freedom).
        r2 (float): The share of the variance of the target explained.
        loo_r2 (Optional[float]): The same, each observation predicted by a fit without it.
        vif (NDArray[numpy.float64]): The variance inflation factor of each criterion (collinearity above 10).
        observations (int): The observations fitted.
        freedom (int): The residual degrees of freedom.
    """

    beta: NDArray[numpy.float64]
    low: NDArray[numpy.float64]
    high: NDArray[numpy.float64]
    p_values: NDArray[numpy.float64]
    r2: float
    loo_r2: Optional[float]
    vif: NDArray[numpy.float64]
    observations: int
    freedom: int
