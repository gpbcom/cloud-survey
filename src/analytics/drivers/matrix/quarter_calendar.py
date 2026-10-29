from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Optional, Pattern

# First Party Imports.
from analytics.drivers.exception import InvalidQuarterError


class QuarterCalendar:
    """Do the arithmetic of the quarters written `YYYYQn`.

    Attributes:
        PERIOD (ClassVar[Pattern[str]]): The format of a quarter.
        logger (Logger): The calendar logger.

    Notes:
        A quarter is numbered `4 × year + (n - 1)`, so that consecutive quarters have consecutive numbers across the
        years (`2024Q4 + 1` is `2025Q1`).
    """

    PERIOD: ClassVar[Pattern[str]] = re.compile(r"^(\d{4})Q([1-4])$")

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the calendar.

        Args:
            logger (Optional[Logger]): The calendar logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def index(self, period: str) -> int:
        """Number a quarter.

        Args:
            period (str): The quarter, written `YYYYQn`.

        Returns:
            int: Its number, `4 × year + (n - 1)`.

        Raises:
            InvalidQuarterError: If it is not written `YYYYQn`.
        """
        found = self.PERIOD.match(period.strip().upper())
        if found is None:
            self.logger.error("The quarter %r is not written YYYYQn.", period)
            raise InvalidQuarterError(period)
        return 4 * int(found.group(1)) + int(found.group(2)) - 1

    def period(self, index: int) -> str:
        """Write the quarter of a number.

        Args:
            index (int): The number, `4 × year + (n - 1)`.

        Returns:
            str: The quarter, written `YYYYQn`.
        """
        return f"{index // 4:04d}Q{index % 4 + 1}"

    def shift(self, period: str, quarters: int) -> str:
        """Move a quarter forward or backward.

        Args:
            period (str): The quarter, written `YYYYQn`.
            quarters (int): How many quarters to move (negative to go back).

        Returns:
            str: The moved quarter (e.g. `2025Q1` shifted by -1 is `2024Q4`).

        Raises:
            InvalidQuarterError: If the quarter is not written `YYYYQn`.
        """
        return self.period(self.index(period) + quarters)

    def of_day(self, day: date) -> str:
        """Write the quarter holding a day.

        Args:
            day (date): The day.

        Returns:
            str: The quarter, written `YYYYQn` (e.g. `2026Q2` for any day from April to June 2026).
        """
        return f"{day.year:04d}Q{(day.month - 1) // 3 + 1}"
