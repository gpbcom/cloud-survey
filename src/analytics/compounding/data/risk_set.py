from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from typing import List

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from models.cloud.enums import CloudProvider


@dataclass(frozen=True)
class RiskSet:
    """The provider-category-years at risk of an entry, with their covariates.

    Attributes:
        names (List[str]): The name of each covariate column (provider effects named `fe:<provider>`).
        x (NDArray[numpy.float64]): The covariates, one row per provider-category-year, without intercept.
        y (NDArray[numpy.float64]): Whether the provider entered the category that year (1) or not (0).
        providers (List[CloudProvider]): The provider of each row.
        columns (NDArray[numpy.intp]): The category column of each row (the bootstrap clusters).
        years (NDArray[numpy.intp]): The year of each row.
    """

    names: List[str]
    x: NDArray[numpy.float64]
    y: NDArray[numpy.float64]
    providers: List[CloudProvider]
    columns: NDArray[numpy.intp]
    years: NDArray[numpy.intp]

    ############################
    # Publicly Exposed Methods #
    ############################

    def events(self) -> int:
        """Count the entries.

        Returns:
            int: The rows with an entry.
        """
        return int(numpy.sum(self.y))

    def rows(self) -> int:
        """Count the rows.

        Returns:
            int: The provider-category-years at risk.
        """
        return int(self.y.shape[0])
