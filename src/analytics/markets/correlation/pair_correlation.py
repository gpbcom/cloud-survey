from __future__ import annotations

# Standard Library Imports.
import math
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from statistics import fmean
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.drivers.correlation.benjamini_hochberg import BenjaminiHochberg
from analytics.drivers.correlation.spearman_correlation import SpearmanCorrelation
from analytics.markets.correlation.series_granger import SeriesGranger
from models.markets.enums import Granularity
from models.markets.series.lag_correlation import LagCorrelation


class PairCorrelation:
    """Correlate the changes of two series period by period and lag by lag, and test which one leads.

    Attributes:
        STEP (ClassVar[Dict[Granularity, int]]): The months of a period.
        MAX_LAG (ClassVar[Dict[Granularity, int]]): The most periods a series is shifted, both ways (a year).
        MIN_PAIRS (ClassVar[Dict[Granularity, int]]): The fewest period pairs a lag needs to get a correlation.
        BLOCK (ClassVar[Dict[Granularity, int]]): The periods of a block of the bootstrap (half a year).
        RESAMPLES (ClassVar[int]): The resamples of the bootstrap.
        GRANGER_LAGS (ClassVar[Dict[Granularity, int]]): The periods of past the Granger tests use.
        SEED (ClassVar[int]): The seed of the bootstrap, so that a result can be reproduced.
        spearman (SpearmanCorrelation): The rank correlation.
        multiple (BenjaminiHochberg): The q-values over the lags.
        granger (SeriesGranger): The lead test.
        logger (Logger): The analysis logger.

    Notes:
        - The series are levels by period (the first day of a month or a quarter). Each is turned into changes from
          the previous period: a difference (points of share, of concentration) or a log change (prices, exchange
          rates). Changes, not levels: two trending series always correlate in levels.
        - Two series of different periods are first brought to the coarser one: the months of a quarter are
          averaged (a share, a rate), or the quarter takes its last month (a close). Nothing is interpolated.
        - At lag `k` the first series' change of period `t` is paired with the second's of period `t + k`: a
          positive `k` asks whether the second follows the first, a negative one whether it leads it.
        - The periods are autocorrelated, so the intervals come from a moving-block bootstrap (half a year per
          block) rather than from independent draws, and the q-values correct for the lags tested.
    """

    STEP: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 1, Granularity.QUARTER: 3}
    MAX_LAG: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 12, Granularity.QUARTER: 4}
    MIN_PAIRS: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 24, Granularity.QUARTER: 12}
    BLOCK: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 6, Granularity.QUARTER: 2}
    RESAMPLES: ClassVar[int] = 400
    GRANGER_LAGS: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 3, Granularity.QUARTER: 2}
    SEED: ClassVar[int] = 20261023

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the analysis.

        Args:
            logger (Optional[Logger]): The analysis logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.spearman = SpearmanCorrelation()
        self.multiple = BenjaminiHochberg()
        self.granger = SeriesGranger()

    ############################
    # Internal Helpers Methods #
    ############################

    def _shift(self, period: date, months: int) -> date:
        """Move a period's first day by some months.

        Args:
            period (date): The first day of a month or a quarter.
            months (int): The months to move, negative to go back.

        Returns:
            date: The first day of the period reached.
        """
        index = period.year * 12 + period.month - 1 + months
        return date(index // 12, index % 12 + 1, 1)

    def _bootstrap(
        self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], block: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """Get the 95% moving-block bootstrap interval of a rank correlation.

        Args:
            x (NDArray[numpy.float64]): The first series.
            y (NDArray[numpy.float64]): The second series, paired.
            block (int): The periods of a block.

        Returns:
            Tuple[Optional[float], Optional[float]]: The 2.5% and 97.5% quantiles, `None` without enough draws.
        """
        count = len(x)
        block = min(block, count)
        starts = count - block + 1
        generator = numpy.random.default_rng(self.SEED)
        draws: List[float] = []
        for _ in range(self.RESAMPLES):
            chosen = generator.integers(0, starts, size=math.ceil(count / block))
            index = numpy.concatenate([numpy.arange(start, start + block) for start in chosen])[:count]
            rho = self.spearman.rho(x[index], y[index])
            if rho is not None:
                draws.append(rho)
        if len(draws) < self.RESAMPLES // 2:
            self.logger.warning(
                "Only %d of %d block bootstrap draws give a correlation: no interval.", len(draws), self.RESAMPLES
            )
            return None, None
        self.logger.debug("Block bootstrap of %d draws, blocks of %d periods.", len(draws), block)
        return float(numpy.quantile(draws, 0.025)), float(numpy.quantile(draws, 0.975))

    def _lag(
        self, first: Dict[date, float], second: Dict[date, float], lag: int, granularity: Granularity
    ) -> LagCorrelation:
        """Correlate the first series' changes with the second's `lag` periods later.

        Args:
            first (Dict[date, float]): The changes of the first series by period.
            second (Dict[date, float]): The changes of the second series by period.
            lag (int): The periods the second follows.
            granularity (Granularity): The period.

        Returns:
            LagCorrelation: The correlation, empty below the fewest pairs.
        """
        months = lag * self.STEP[granularity]
        pairs = [
            (change, second[self._shift(period, months)])
            for period, change in sorted(first.items())
            if self._shift(period, months) in second
        ]
        if len(pairs) < self.MIN_PAIRS[granularity]:
            self.logger.debug(
                "Lag %d: %d pairs, fewer than the %d needed.", lag, len(pairs), self.MIN_PAIRS[granularity]
            )
            return LagCorrelation(lag=lag, months=len(pairs))
        x = numpy.asarray([pair[0] for pair in pairs], dtype=numpy.float64)
        y = numpy.asarray([pair[1] for pair in pairs], dtype=numpy.float64)
        rho = self.spearman.rho(x, y)
        if rho is None:
            self.logger.warning("Lag %d: no correlation over %d pairs (a constant series).", lag, len(pairs))
            return LagCorrelation(lag=lag, months=len(pairs))
        self.logger.debug("Lag %d: rho %.3f over %d pairs.", lag, rho, len(pairs))
        low, high = self._bootstrap(x, y, self.BLOCK[granularity])
        return LagCorrelation(
            lag=lag, rho=rho, low=low, high=high, p_value=self.spearman.p_value(rho, len(pairs)), months=len(pairs)
        )

    def _longest_run(self, first: Dict[date, float], second: Dict[date, float], step: int) -> List[date]:
        """Find the longest run of consecutive periods with a change of both series.

        Args:
            first (Dict[date, float]): The changes of the first series by period.
            second (Dict[date, float]): The changes of the second series by period.
            step (int): The months of a period.

        Returns:
            List[date]: The periods of the run, oldest first.
        """
        best: List[date] = []
        run: List[date] = []
        for period in sorted(set(first) & set(second)):
            run = [*run, period] if run and self._shift(run[-1], step) == period else [period]
            if len(run) > len(best):
                best = run
        self.logger.debug("Longest run of consecutive common periods: %d.", len(best))
        return best

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_quarters(self, levels: Dict[date, float], period_end: bool) -> Dict[date, float]:
        """Bring monthly levels to quarters.

        Args:
            levels (Dict[date, float]): The levels by month.
            period_end (bool): Whether a quarter takes its last month (a close) rather than the mean of its months.

        Returns:
            Dict[date, float]: The levels by quarter (its first day). With `period_end`, only the quarters whose
                last month has a level.
        """
        if period_end:
            self.logger.debug("Quarters of %d monthly levels, from the quarter-end months.", len(levels))
            return {self._shift(month, -2): value for month, value in levels.items() if month.month % 3 == 0}
        self.logger.debug("Quarters of %d monthly levels, as means of their months.", len(levels))
        months: Dict[date, List[float]] = defaultdict(list)
        for month, value in levels.items():
            months[date(month.year, month.month - (month.month - 1) % 3, 1)].append(value)
        return {quarter: fmean(values) for quarter, values in sorted(months.items())}

    def changes(self, levels: Dict[date, float], granularity: Granularity, log: bool) -> Dict[date, float]:
        """Turn levels into changes from the previous period (consecutive periods only).

        Args:
            levels (Dict[date, float]): The levels by period.
            granularity (Granularity): The period.
            log (bool): Whether the change is a log change rather than a difference.

        Returns:
            Dict[date, float]: The change of each period whose previous period has a level.
        """
        step = self.STEP[granularity]
        changes: Dict[date, float] = {}
        for period, level in levels.items():
            previous = levels.get(self._shift(period, -step))
            if previous is None:
                continue
            if log:
                if previous > 0 and level > 0:
                    changes[period] = math.log(level / previous)
            else:
                changes[period] = level - previous
        if not changes and levels:
            self.logger.warning("No change out of %d levels at a %s step.", len(levels), granularity)
        else:
            self.logger.debug("%d changes out of %d levels (log %s).", len(changes), len(levels), log)
        return changes

    def correlate(
        self, first: Dict[date, float], second: Dict[date, float], granularity: Granularity
    ) -> Tuple[List[LagCorrelation], Optional[float], Optional[float]]:
        """Correlate two series of changes at every lag, and test both directions of lead.

        Args:
            first (Dict[date, float]): The changes of the first series by period.
            second (Dict[date, float]): The changes of the second series by period.
            granularity (Granularity): The period of both.

        Returns:
            Tuple[List[LagCorrelation], Optional[float], Optional[float]]: The correlation by lag with its q-value,
                the Granger p-value of "the first leads the second", and of "the second leads the first".
        """
        reach = self.MAX_LAG[granularity]
        lags = [self._lag(first, second, lag, granularity) for lag in range(-reach, reach + 1)]
        tested = [index for index, lag in enumerate(lags) if lag.p_value is not None]
        q_values = self.multiple.q_values([lags[index].p_value or 1.0 for index in tested])
        for index, q_value in zip(tested, q_values, strict=True):
            lags[index] = lags[index].model_copy(update={"q_value": q_value})
        run = self._longest_run(first, second, self.STEP[granularity])
        x = numpy.asarray([first[period] for period in run], dtype=numpy.float64)
        y = numpy.asarray([second[period] for period in run], dtype=numpy.float64)
        past = self.GRANGER_LAGS[granularity]
        first_leads, second_leads = self.granger.p_value(y, x, past), self.granger.p_value(x, y, past)
        self.logger.debug(
            "%d lags correlated over %d consecutive %ss, "  # noqa: E501
            "Granger first->second p=%s, second->first p=%s.",  
            len(tested),
            len(run),
            granularity.value,
            first_leads,
            second_leads,
        )
        return lags, first_leads, second_leads
