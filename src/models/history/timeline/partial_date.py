from __future__ import annotations

# Standard Library Imports.
import calendar
import re
from typing import ClassVar, Pattern, Tuple

# First Party Imports.
from models.history.enums import DatePrecision
from models.history.exception import InvalidHistoryDateError


class PartialDate:
    """Read the dates of the chronology, known to the year, the month or the day.

    Attributes:
        PATTERN (ClassVar[Pattern[str]]): The format of a date: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.

    Notes:
        A date stands for the start of its period, as the policy shocks of mega-trends stand for 1 January: `1998` is
        1998.0, `1998-07` is 1998.5. The fractional year places it on a time axis.
    """

    PATTERN: ClassVar[Pattern[str]] = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")

    ############################
    # Publicly Exposed Methods #
    ############################

    def parts(self, text: str) -> Tuple[int, int, int, DatePrecision]:
        """Split a date into its year, month and day.

        Args:
            text (str): The date.

        Returns:
            Tuple[int, int, int, DatePrecision]: The year, the month (1 when unknown), the day (1 when unknown) and
                the precision.

        Raises:
            InvalidHistoryDateError: If it is not a valid `YYYY`, `YYYY-MM` or `YYYY-MM-DD` date.
        """
        found = self.PATTERN.match(text.strip())
        if found is None:
            raise InvalidHistoryDateError(text)
        year = int(found.group(1))
        month = int(found.group(2)) if found.group(2) else 1
        day = int(found.group(3)) if found.group(3) else 1
        if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(year, month)[1]:
            raise InvalidHistoryDateError(text)
        precision = (
            DatePrecision.DAY if found.group(3) else DatePrecision.MONTH if found.group(2) else DatePrecision.YEAR
        )
        return year, month, day, precision

    def fraction(self, text: str) -> float:
        """Place a date on a time axis.

        Args:
            text (str): The date.

        Returns:
            float: Its fractional year (the start of its period).

        Raises:
            InvalidHistoryDateError: If it is not a valid date.
        """
        year, month, day, _ = self.parts(text)
        return year + (month - 1) / 12 + (day - 1) / calendar.monthrange(year, month)[1] / 12
