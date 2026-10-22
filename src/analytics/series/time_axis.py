from __future__ import annotations

# Standard Library Imports.
import calendar
import math
from datetime import UTC, date, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple

# First Party Imports.
from models.stats.market_report import MarketReport
from models.trends.enums import ChartMetric


class TimeAxis:
    """Place moments on a time axis as month ordinals, and name them.

    Attributes:
        GRAIN_MONTHS (ClassVar[Dict[ChartMetric, int]]): The number of months of each calendar bucket.
        logger (Logger): The axis logger.

    Notes:
        A month ordinal is `year * 12 + month - 1`, plus the elapsed fraction of the month for a date. A bucket or a
        market report period sits on its last month: `2025Q2`, `2025H1` and the June 2025 month bucket are all at the
        same ordinal, so that the series of every source line up.
    """

    GRAIN_MONTHS: ClassVar[Dict[ChartMetric, int]] = {
        ChartMetric.YEAR: 12,
        ChartMetric.QUARTER: 3,
        ChartMetric.MONTH: 1,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the axis.

        Args:
            logger (Optional[Logger]): The axis logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _parts(self, ordinal: float) -> Tuple[int, int, float]:
        """Split a month ordinal.

        Args:
            ordinal (float): The month ordinal.

        Returns:
            Tuple[int, int, float]: The year, the month (1 to 12) and the elapsed fraction of the month.
        """
        index = math.floor(ordinal + 1e-9)
        year, month = divmod(index, 12)
        return year, month + 1, max(ordinal - index, 0.0)

    ############################
    # Publicly Exposed Methods #
    ############################

    def month(self, year: int, month: int) -> float:
        """Get the ordinal of a month.

        Args:
            year (int): The year.
            month (int): The month, 1 to 12.

        Returns:
            float: The month ordinal.
        """
        return float(year * 12 + month - 1)

    def ordinal(self, value: date) -> float:
        """Get the ordinal of a date (a timezone-aware time is read in UTC).

        Args:
            value (date): The date, or the time.

        Returns:
            float: The month ordinal, with the elapsed fraction of the month.
        """
        if isinstance(value, datetime):
            moment = value.astimezone(UTC) if value.tzinfo else value
            days = calendar.monthrange(moment.year, moment.month)[1]
            elapsed = moment.day - 1 + (moment.hour * 3600 + moment.minute * 60 + moment.second) / 86400
            return self.month(moment.year, moment.month) + elapsed / days
        days = calendar.monthrange(value.year, value.month)[1]
        return self.month(value.year, value.month) + (value.day - 1) / days

    def period(self, report: MarketReport) -> float:
        """Get the ordinal of the period of a market report: its last month.

        Args:
            report (MarketReport): The market report.

        Returns:
            float: The month ordinal, e.g. June 2025 for `2025Q2` and `2025H1`.
        """
        year, last_month = report.sort_key()
        return self.month(year, last_month)

    def bucket(self, ordinal: float, grain: ChartMetric) -> float:
        """Get the calendar bucket of a moment: the ordinal of its last month.

        Args:
            ordinal (float): The month ordinal of the moment.
            grain (ChartMetric): The bucket: `YEAR`, `QUARTER` or `MONTH`.

        Returns:
            float: The month ordinal of the last month of the bucket.
        """
        span = self.GRAIN_MONTHS[grain]
        year, month, _ = self._parts(ordinal)
        last = ((month - 1) // span) * span + span
        return self.month(year, last)

    def bucket_of_start(self, start: date, grain: ChartMetric) -> float:
        """Get the bucket starting on a date (as truncated by the database).

        Args:
            start (date): The first day of the bucket.
            grain (ChartMetric): The bucket: `YEAR`, `QUARTER` or `MONTH`.

        Returns:
            float: The month ordinal of the last month of the bucket.
        """
        return self.month(start.year, start.month) + self.GRAIN_MONTHS[grain] - 1

    def now(self) -> float:
        """Get the ordinal of the current time.

        Returns:
            float: The month ordinal of now, in UTC.
        """
        return self.ordinal(datetime.now(UTC))

    def label(self, metric: ChartMetric, ordinal: float) -> str:
        """Name a moment the way its axis counts time.

        Args:
            metric (ChartMetric): The time metric of the axis.
            ordinal (float): The month ordinal.

        Returns:
            str: e.g. `2026` (year), `2026Q2` (quarter or period), `2026-05` (month), `12 Mar 2026` (dates).
        """
        year, month, fraction = self._parts(ordinal)
        match metric:
            case ChartMetric.YEAR:
                return f"{year}"
            case ChartMetric.QUARTER | ChartMetric.PERIOD:
                return f"{year}Q{(month - 1) // 3 + 1}"
            case ChartMetric.MONTH:
                return f"{year}-{month:02d}"
            case _:
                days = calendar.monthrange(year, month)[1]
                day = min(int(fraction * days) + 1, days)
                return date(year, month, day).strftime("%d %b %Y")
