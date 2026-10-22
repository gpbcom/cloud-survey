from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from typing import Dict, List

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.enums import ProviderMetric


@dataclass(frozen=True)
class DriverMatrix:
    """The numeric observations of a driver analysis: one row per provider (or per provider and quarter).

    Attributes:
        target (ProviderMetric): The measure of the rise.
        criteria (List[ProviderMetric]): The candidate drivers, in the order of the columns of `x`.
        controls (List[ProviderMetric]): The controls, in the order of the columns of `z`.
        y (NDArray[numpy.float64]): The transformed target of each row (`NaN` when missing).
        x (NDArray[numpy.float64]): The transformed criteria, one column per criterion (`NaN` when missing).
        z (NDArray[numpy.float64]): The transformed controls, one column per control (`NaN` when missing).
        providers (List[CloudProvider]): The provider of each row.
        periods (List[str]): The quarter of the target of each row.
        dropped (int): The rows holding the target but missing a criterion (left out of the regression).
        target_providers (int): The distinct providers holding at least one value of the target.
        series (Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]): The transformed values by provider,
            metric and quarter: the levels for a cross-section, the changes over 4 quarters for a panel.

    Notes:
        The rows missing a criterion are kept (with `NaN`) so that
        the correlations stay pairwise-complete, while
        the regression only uses the complete rows (`complete_rows`).
    """

    target: ProviderMetric
    criteria: List[ProviderMetric]
    controls: List[ProviderMetric]
    y: NDArray[numpy.float64]
    x: NDArray[numpy.float64]
    z: NDArray[numpy.float64]
    providers: List[CloudProvider]
    periods: List[str]
    dropped: int
    target_providers: int
    series: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]

    ############################
    # Publicly Exposed Methods #
    ############################

    def complete_rows(self) -> NDArray[numpy.bool_]:
        """Tell which rows hold the target and every criterion.

        Returns:
            NDArray[numpy.bool_]: One flag per row.
        """
        if not len(self.y):
            return numpy.zeros(0, dtype=numpy.bool_)
        return numpy.isfinite(self.y) & numpy.isfinite(self.x).all(axis=1)
