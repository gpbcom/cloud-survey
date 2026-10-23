from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy import stats


class SeriesGranger:
    """Test whether a series leads another: do its past values predict the other beyond the other's own past.

    Attributes:
        logger (Logger): The test logger.

    Notes:
        - The restricted regression explains `y_t` by a constant and its own `L` past values, the full one adds the
          `L` past values of `x`. The F test of the gain gives the p-value: small, `x` moves first.
        - It is the single-series form of the panel test of the Rise drivers (`analytics.drivers.panel`), without
          provider effects. Run it both ways and compare: a feedback loop shows small p-values in both directions.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the test.

        Args:
            logger (Optional[Logger]): The test logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def p_value(self, y: NDArray[numpy.float64], x: NDArray[numpy.float64], lags: int) -> Optional[float]:
        """Test whether `x` leads `y`.

        Args:
            y (NDArray[numpy.float64]): The led series, consecutive periods.
            x (NDArray[numpy.float64]): The leading series, the same periods.
            lags (int): The past periods used (at least 1).

        Returns:
            Optional[float]: The p-value, `None` without enough periods.
        """
        lags = max(1, lags)
        count = min(len(y), len(x))
        freedom = count - lags - (2 * lags + 1)
        if freedom < 2:
            return None
        target = y[lags:count]
        own = numpy.column_stack([y[lags - step : count - step] for step in range(1, lags + 1)])
        other = numpy.column_stack([x[lags - step : count - step] for step in range(1, lags + 1)])
        constant = numpy.ones((len(target), 1))
        restricted = numpy.hstack([constant, own])
        full = numpy.hstack([constant, own, other])
        restricted_ssr = float(
            ((target - restricted @ numpy.linalg.lstsq(restricted, target, rcond=None)[0]) ** 2).sum()
        )
        full_ssr = float(((target - full @ numpy.linalg.lstsq(full, target, rcond=None)[0]) ** 2).sum())
        if full_ssr <= 1e-12:
            return 0.0 if restricted_ssr > 1e-12 else None
        statistic = max(0.0, (restricted_ssr - full_ssr) / lags) / (full_ssr / freedom)
        p_value = float(stats.f.sf(statistic, lags, freedom))
        self.logger.debug("Granger: F %.3f, p %.3g over %d periods.", statistic, p_value, len(target))
        return min(1.0, max(0.0, p_value))
