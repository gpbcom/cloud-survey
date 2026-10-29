from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass

# Third Party Imports.
import numpy
from numpy.typing import NDArray


@dataclass(frozen=True)
class LogitFit:
    """A logit fit of entries on covariates.

    Attributes:
        intercept (float): The intercept (log-odds of an entry with every covariate at 0).
        beta (NDArray[numpy.float64]): The coefficient of each covariate (change of the log-odds per unit).
        log_likelihood (float): The log-likelihood of the fit.
        converged (bool): Whether the Newton iterations converged without separation.
    """

    intercept: float
    beta: NDArray[numpy.float64]
    log_likelihood: float
    converged: bool
