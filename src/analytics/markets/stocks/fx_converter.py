from __future__ import annotations

# Standard Library Imports.
import bisect
from collections import defaultdict
from datetime import date, timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from models.markets.enums import FxQuote, MarketFeed
from models.markets.facts.fx_observation import FxObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.fx_rate import FxRate


class FxConverter:
    """Turn the FRED series into dollar rates, and convert amounts between currencies on a day.

    Attributes:
        PIVOT (ClassVar[str]): The currency every conversion goes through.
        STALE_AFTER (ClassVar[timedelta]): How old the latest rate may be before a day counts as without rate.
        logger (Logger): The converter logger.
        days (Dict[str, List[date]]): The days with a rate, by currency, sorted.
        rates (Dict[str, List[float]]): The US dollars per unit on those days, by currency.

    Notes:
        - A day takes the latest rate on or before it (a weekend takes Friday's), as long as it is less than
          `STALE_AFTER` old (the monthly rouble series included).
        - A day before a currency's first rate has no conversion: the euro starts in 1999, so a Helsinki price of
          1995 shows in its listing currency only.
    """

    PIVOT: ClassVar[str] = "USD"
    STALE_AFTER: ClassVar[timedelta] = timedelta(days=40)

    def __init__(self, rates: Optional[Sequence[FxRate]] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the converter.

        Args:
            rates (Optional[Sequence[FxRate]]): The stored rates, none by default (`load` reads them later).
            logger (Optional[Logger]): The converter logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.days: Dict[str, List[date]] = {}
        self.rates: Dict[str, List[float]] = {}
        self.load(rates or [])

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_rates(self, observations: Sequence[FxObservation], catalog: MarketsCatalog) -> List[FxRate]:
        """Turn FRED values into US dollars per unit.

        Args:
            observations (Sequence[FxObservation]): The values, quoted as their series is.
            catalog (MarketsCatalog): The currency of each series and its quotation.

        Returns:
            List[FxRate]: The rates, the values of a series no currency reads left out.
        """
        series = {entry.series: entry for entry in catalog.currencies}
        rates: List[FxRate] = []
        for observation in observations:
            entry = series.get(observation.series)
            if entry is None:
                self.logger.warning("The FRED series %s is no currency of the catalogue.", observation.series)
                continue
            value = observation.value if entry.quote is FxQuote.USD_PER_UNIT else 1.0 / observation.value
            rates.append(
                FxRate(currency=entry.currency, day=observation.day, usd_per_unit=value, source=MarketFeed.FRED)
            )
        self.logger.debug("%d FRED values turned into dollar rates.", len(rates))
        return rates

    def load(self, rates: Sequence[FxRate]) -> None:
        """Index the rates to convert with.

        Args:
            rates (Sequence[FxRate]): The rates.
        """
        by_currency: Dict[str, List[Tuple[date, float]]] = defaultdict(list)
        for rate in rates:
            by_currency[rate.currency].append((rate.day, rate.usd_per_unit))
        self.days = {currency: [day for day, _ in sorted(pairs)] for currency, pairs in by_currency.items()}
        self.rates = {currency: [value for _, value in sorted(pairs)] for currency, pairs in by_currency.items()}
        self.logger.debug("Exchange rates indexed for %d currencies.", len(self.days))

    def usd_per_unit(self, currency: str, day: date) -> Optional[float]:
        """Get the US dollars one unit of a currency was worth on a day.

        Args:
            currency (str): The currency.
            day (date): The day.

        Returns:
            Optional[float]: The rate, `None` when the currency has no rate on or recently before that day.
        """
        if currency == self.PIVOT:
            return 1.0
        days = self.days.get(currency)
        if not days:
            return None
        index = bisect.bisect_right(days, day) - 1
        if index < 0 or day - days[index] > self.STALE_AFTER:
            return None
        return self.rates[currency][index]

    def convert(self, amount: float, source: str, target: str, day: date) -> Optional[float]:
        """Convert an amount from a currency to another on a day, through the US dollar.

        Args:
            amount (float): The amount.
            source (str): Its currency.
            target (str): The currency wanted.
            day (date): The day.

        Returns:
            Optional[float]: The amount in the target currency, `None` when a rate is missing that day.
        """
        if source == target:
            return amount
        source_rate, target_rate = self.usd_per_unit(source, day), self.usd_per_unit(target, day)
        if source_rate is None or target_rate is None:
            return None
        return amount * source_rate / target_rate

    def first_day(self, currency: str) -> Optional[date]:
        """Get the first day a currency converts.

        Args:
            currency (str): The currency.

        Returns:
            Optional[date]: Its first rate's day, `None` for the US dollar or a currency without rate.
        """
        days = self.days.get(currency)
        return days[0] if days and currency != self.PIVOT else None
