from __future__ import annotations

# Standard Library Imports.
import itertools
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Sequence

# First Party Imports.
from models.markets.enums import Granularity
from models.markets.series.coverage_entry import CoverageEntry


class CoverageChecker:
    """Count the points of a series and tell whether there are enough of them to correlate it.

    Attributes:
        MIN_POINTS (ClassVar[Dict[Granularity, int]]): The fewest points a correlated series may hold: three years
            of months, four years of quarters.
        MAX_GAP (ClassVar[int]): The most consecutive periods a correlated series may miss.
        STEP (ClassVar[Dict[Granularity, int]]): The months of a period.
        logger (Logger): The checker logger.

    Notes:
        Below 36 monthly or 16 quarterly points, a rank correlation over lags of up to a year keeps too few pairs,
        and the bootstrap intervals cover the whole range: the analysis refuses rather than show noise.
    """

    MIN_POINTS: ClassVar[Dict[Granularity, int]] = {
        Granularity.MONTH: 36,
        Granularity.QUARTER: 16,
        Granularity.YEAR: 10,
    }
    MAX_GAP: ClassVar[int] = 3
    STEP: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 1, Granularity.QUARTER: 3, Granularity.YEAR: 12}

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the checker.

        Args:
            logger (Optional[Logger]): The checker logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _months_between(self, first: date, second: date) -> int:
        """Count the months from a period to a later one.

        Args:
            first (date): The earlier period.
            second (date): The later period.

        Returns:
            int: The months between their first days.
        """
        return (second.year - first.year) * 12 + second.month - first.month

    ############################
    # Publicly Exposed Methods #
    ############################

    def entry(self, key: str, periods: Sequence[date], granularity: Granularity = Granularity.MONTH) -> CoverageEntry:
        """Describe the coverage of a series.

        Args:
            key (str): What the series is.
            periods (Sequence[date]): The periods with a value (first days, in any order).
            granularity (Granularity): The period of the series.

        Returns:
            CoverageEntry: Its span, its points, its longest gap and whether it can be correlated.
        """
        ordered = sorted(set(periods))
        step = self.STEP[granularity]
        gap = max((self._months_between(a, b) // step - 1 for a, b in itertools.pairwise(ordered)), default=0)
        enough = len(ordered) >= self.MIN_POINTS[granularity] and gap <= self.MAX_GAP
        if not enough:
            self.logger.debug("%s: %d points, longest gap %d: not enough to correlate.", key, len(ordered), gap)
        return CoverageEntry(
            key=key,
            granularity=granularity,
            first=ordered[0] if ordered else None,
            last=ordered[-1] if ordered else None,
            points=len(ordered),
            longest_gap=max(0, gap),
            enough=enough,
        )
