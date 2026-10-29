from __future__ import annotations

# Standard Library Imports.
import itertools
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

type Duration = Tuple[date, date]


class FlowQuarters:
    """Get the fiscal quarters and years of a flow (revenue, cash flow) from the periods its filings state.

    Attributes:
        QUARTER_DAYS (ClassVar[Tuple[int, int]]): The lengths of a fiscal quarter, in days.
        YEAR_DAYS (ClassVar[Tuple[int, int]]): The lengths of a fiscal year, in days (52 or 53 weeks included).
        logger (Logger): The helper logger.

    Notes:
        - A 10-Q states the cash flows of the fiscal year to date, a 10-K the year: a quarter is taken as filed
          when a 3-month figure exists, else derived from two figures of the same fiscal year 3 months apart (the
          fourth quarter is the year less the nine months).
        - A quarter is dated by its last day.
    """

    QUARTER_DAYS: ClassVar[Tuple[int, int]] = (80, 100)
    YEAR_DAYS: ClassVar[Tuple[int, int]] = (350, 380)

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the helper.

        Args:
            logger (Optional[Logger]): The helper logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_quarter(self, start: date, end: date) -> bool:
        """Tell whether a period is a fiscal quarter long.

        Args:
            start (date): Its first day.
            end (date): Its last day.

        Returns:
            bool: Whether it lasts about 3 months.
        """
        low, high = self.QUARTER_DAYS
        return low <= (end - start).days <= high

    def is_year(self, start: date, end: date) -> bool:
        """Tell whether a period is a fiscal year long.

        Args:
            start (date): Its first day.
            end (date): Its last day.

        Returns:
            bool: Whether it lasts about 12 months.
        """
        low, high = self.YEAR_DAYS
        return low <= (end - start).days <= high

    def quarters(self, durations: Dict[Duration, float]) -> Tuple[Dict[date, float], Dict[date, float]]:
        """Get the value of each fiscal quarter, as filed or derived from the year-to-date figures.

        Args:
            durations (Dict[Duration, float]): The value of each period filed.

        Returns:
            Tuple[Dict[date, float], Dict[date, float]]: The quarters filed, then those derived, by their last day
                (a quarter filed is never derived).
        """
        filed = {end: value for (start, end), value in durations.items() if self.is_quarter(start, end)}
        derived: Dict[date, float] = {}
        by_start: Dict[date, List[Tuple[date, float]]] = {}
        for (start, end), value in durations.items():
            by_start.setdefault(start, []).append((end, value))
        for ends in by_start.values():
            ends.sort()
            for (first, before), (last, after) in itertools.pairwise(ends):
                if last not in filed and last not in derived and self.is_quarter(first, last):
                    derived[last] = after - before
        self.logger.debug("%d quarters filed, %d derived from the year-to-date figures.", len(filed), len(derived))
        return filed, derived

    def years(self, durations: Dict[Duration, float]) -> Dict[date, float]:
        """Get the value of each fiscal year filed.

        Args:
            durations (Dict[Duration, float]): The value of each period filed.

        Returns:
            Dict[date, float]: The value of each fiscal year, by its last day.
        """
        return {end: value for (start, end), value in durations.items() if self.is_year(start, end)}
