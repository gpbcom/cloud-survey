from __future__ import annotations

# Standard Library Imports.
import bisect
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from models.markets.values.fx_rate import FxRate


class CurrencyRates:
    """Convert amounts into US dollars at the rate of a day, from the stored FRED exchange rates.

    Attributes:
        DOLLAR (ClassVar[str]): The US dollar.
        TOLERANCE_DAYS (ClassVar[int]): How far from the day a rate may be taken (a weekend, a holiday).
        days (Dict[str, List[date]]): The days of the rates of each currency, sorted.
        rates (Dict[str, List[float]]): The US dollars per unit of each currency, in the order of the days.
        logger (Logger): The helper logger.

    Notes:
        The rate of a day is the last one on or before it, else the first one after it, within the tolerance. A
        currency without a stored rate (or a day outside its series) has no conversion: the US-dollar value is
        then left empty, never guessed.
    """

    DOLLAR: ClassVar[str] = "USD"
    TOLERANCE_DAYS: ClassVar[int] = 10

    def __init__(self, rates: Sequence[FxRate], logger: Optional[Logger] = None) -> None:
        """Initialize the helper.

        Args:
            rates (Sequence[FxRate]): The stored exchange rates.
            logger (Optional[Logger]): The helper logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        series: Dict[str, List[Tuple[date, float]]] = {}
        for rate in rates:
            series.setdefault(rate.currency, []).append((rate.day, rate.usd_per_unit))
        self.days: Dict[str, List[date]] = {}
        self.rates: Dict[str, List[float]] = {}
        for currency, points in series.items():
            points.sort()
            self.days[currency] = [day for day, _ in points]
            self.rates[currency] = [value for _, value in points]
        self.logger.debug("Exchange rates of %d currencies ready.", len(self.days))

    ############################
    # Publicly Exposed Methods #
    ############################

    def usd_per_unit(self, currency: Optional[str], day: date) -> Optional[float]:
        """Get the US dollars of one unit of a currency on a day.

        Args:
            currency (Optional[str]): The currency.
            day (date): The day.

        Returns:
            Optional[float]: The rate (1 for the dollar), `None` when no rate is stored near the day.
        """
        if currency == self.DOLLAR:
            return 1.0
        days = self.days.get(currency or "")
        if not days:
            return None
        index = bisect.bisect_right(days, day)
        if index and (day - days[index - 1]).days <= self.TOLERANCE_DAYS:
            return self.rates[currency or ""][index - 1]
        if index < len(days) and (days[index] - day).days <= self.TOLERANCE_DAYS:
            return self.rates[currency or ""][index]
        return None

    def to_usd(self, value: float, currency: Optional[str], day: date) -> Optional[float]:
        """Convert an amount into US dollars.

        Args:
            value (float): The amount.
            currency (Optional[str]): Its currency.
            day (date): The day of the rate.

        Returns:
            Optional[float]: The amount in US dollars, `None` without a rate.
        """
        rate = self.usd_per_unit(currency, day)
        return value * rate if rate is not None else None

    def convert(self, value: float, source: Optional[str], target: Optional[str], day: date) -> Optional[float]:
        """Convert an amount from one currency into another, through the US dollar.

        Args:
            value (float): The amount.
            source (Optional[str]): Its currency.
            target (Optional[str]): The currency wanted.
            day (date): The day of the rates.

        Returns:
            Optional[float]: The amount in the target currency, `None` without the rates.
        """
        if source == target:
            return value
        usd = self.to_usd(value, source, day)
        rate = self.usd_per_unit(target, day)
        return usd / rate if usd is not None and rate else None
