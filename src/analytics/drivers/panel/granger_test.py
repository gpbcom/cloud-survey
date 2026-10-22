from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
import numpy
from scipy import stats

# First Party Imports.
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from analytics.drivers.panel.fixed_effects_demeaner import FixedEffectsDemeaner
from models.cloud.enums import CloudProvider
from models.drivers.enums import ProviderMetric


class GrangerTest:
    """Test whether a criterion leads the target: do its past changes predict the target beyond the target's own past.

    Attributes:
        calendar (QuarterCalendar): The quarter arithmetic.
        demeaner (FixedEffectsDemeaner): The provider effects.
        logger (Logger): The test logger.

    Notes:
        - The pooled test compares the regression of the target change on its own `L` past changes with the one adding
          the `L` past changes of the criterion, both with a provider effect, by an F test. A small p-value says the
          criterion moves first, which separates a driver from a consequence.
        - With few quarters the provider effect biases the own lags (Nickell bias): read the p-value as an indication.
        - The yearly changes of consecutive quarters overlap (they share 3 quarters), so a follower can show a weak lead
          too: compare the p-values of both directions rather than reading one against 5%.
    """

    def __init__(
        self,
        calendar: Optional[QuarterCalendar] = None,
        demeaner: Optional[FixedEffectsDemeaner] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the test.

        Args:
            calendar (Optional[QuarterCalendar]): The quarter arithmetic.
            demeaner (Optional[FixedEffectsDemeaner]): The provider effects.
            logger (Optional[Logger]): The test logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.calendar = calendar if calendar else QuarterCalendar(self.logger)
        self.demeaner = demeaner if demeaner else FixedEffectsDemeaner(self.logger)

    ############################
    # Publicly Exposed Methods #
    ############################

    def p_value(
        self,
        series: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]],
        target: ProviderMetric,
        criterion: ProviderMetric,
        lags: int,
    ) -> Optional[float]:
        """Test whether a criterion leads the target.

        Args:
            series (Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]): The changes by provider, metric
                and quarter.
            target (ProviderMetric): The target.
            criterion (ProviderMetric): The criterion.
            lags (int): The past quarters used (at least 1).

        Returns:
            Optional[float]: The p-value, `None` without enough observations.
        """
        lags = max(1, lags)
        rows: List[List[float]] = []
        providers: List[str] = []
        for provider, by_metric in series.items():
            own, other = by_metric.get(target, {}), by_metric.get(criterion, {})
            for period, value in own.items():
                past = [self.calendar.shift(period, -step) for step in range(1, lags + 1)]
                if all(quarter in own for quarter in past) and all(quarter in other for quarter in past):
                    rows.append([value, *(own[quarter] for quarter in past), *(other[quarter] for quarter in past)])
                    providers.append(provider.value)
        freedom = len(rows) - 2 * lags - len(set(providers))
        if freedom < 2:
            return None
        values = self.demeaner.demean(numpy.asarray(rows, dtype=numpy.float64), [self.demeaner.codes(providers)])
        y = values[:, 0]
        restricted = numpy.linalg.lstsq(values[:, 1 : lags + 1], y, rcond=None)[0]
        full = numpy.linalg.lstsq(values[:, 1:], y, rcond=None)[0]
        restricted_ssr = float(((y - values[:, 1 : lags + 1] @ restricted) ** 2).sum())
        full_ssr = float(((y - values[:, 1:] @ full) ** 2).sum())
        if full_ssr <= 1e-12:
            return 0.0 if restricted_ssr > 1e-12 else None
        statistic = max(0.0, (restricted_ssr - full_ssr) / lags) / (full_ssr / freedom)
        p_value = float(stats.f.sf(statistic, lags, freedom))
        self.logger.debug(
            "Granger %s -> %s: F %.3f, p %.3g (%d rows).", criterion, target, statistic, p_value, len(rows)
        )
        return min(1.0, max(0.0, p_value))
