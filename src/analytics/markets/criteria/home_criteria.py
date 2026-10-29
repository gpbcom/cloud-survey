from __future__ import annotations

# Standard Library Imports.
import math
from collections import defaultdict
from logging import Logger, getLogger
from statistics import fmean
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.history.catalog.company import Company
from models.markets.enums import WeightIndicator
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.fx_rate import FxRate


class HomeCriteria:
    """Measure the home market of each provider's company: its currency (FRED) and its internet users (World Bank).

    Attributes:
        PIVOT (ClassVar[str]): The currency the changes are measured against.
        MILLION (ClassVar[float]): The people of a million.
        calendar (QuarterCalendar): Names the quarters.
        logger (Logger): The measurer logger.

    Notes:
        - The home country is the company's headquarters (`Company.country`), its currency the catalogue's
          `country_currencies`. The change is the log change of the quarter's mean units per US dollar from the
          previous quarter: positive when the home currency weakens. A US company's change is 0 over the quarters
          the rates cover.
        - The internet users of a year are its share of the population using the internet times its population, in
          millions. Each quarter of the year takes that value (the World Bank publishes years).
    """

    PIVOT: ClassVar[str] = "USD"
    MILLION: ClassVar[float] = 1_000_000.0

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the measurer.

        Args:
            logger (Optional[Logger]): The measurer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.calendar = QuarterCalendar()

    ############################
    # Internal Helpers Methods #
    ############################

    def _quarter_means(self, rates: Sequence[FxRate]) -> Dict[str, Dict[str, float]]:
        """Average the units per US dollar of each currency over each quarter.

        Args:
            rates (Sequence[FxRate]): The exchange rates.

        Returns:
            Dict[str, Dict[str, float]]: The mean units per US dollar, by currency then quarter.
        """
        samples: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for rate in rates:
            samples[rate.currency][self.calendar.of_day(rate.day)].append(1.0 / rate.usd_per_unit)
        self.logger.debug("Quarterly means of %d rates in %d currencies.", len(rates), len(samples))
        return {
            currency: {quarter: fmean(values) for quarter, values in sorted(quarters.items())}
            for currency, quarters in samples.items()
        }

    def _changes(self, means: Dict[str, float]) -> Dict[str, float]:
        """Get the log change of each quarter from the previous one.

        Args:
            means (Dict[str, float]): The mean units per US dollar, by quarter.

        Returns:
            Dict[str, float]: The changes, for the quarters whose previous quarter has a mean.
        """
        changes: Dict[str, float] = {}
        for quarter, mean in means.items():
            previous = means.get(self.calendar.shift(quarter, -1))
            if previous is not None and previous > 0 and mean > 0:
                changes[quarter] = math.log(mean / previous)
        self.logger.debug("%d quarterly changes out of %d means.", len(changes), len(means))
        return changes

    def _users(self, weights: Sequence[WeightObservation]) -> Dict[Tuple[str, int], float]:
        """Get the internet users of each country and year, in millions.

        Args:
            weights (Sequence[WeightObservation]): The World Bank observations.

        Returns:
            Dict[Tuple[str, int], float]: The users, by country and year holding both indicators.
        """
        rates = {
            (weight.country, weight.year): weight.value
            for weight in weights
            if weight.indicator is WeightIndicator.INTERNET_USERS
        }
        people = {
            (weight.country, weight.year): weight.value
            for weight in weights
            if weight.indicator is WeightIndicator.POPULATION
        }
        users = {key: rates[key] / 100.0 * people[key] / self.MILLION for key in rates.keys() & people.keys()}
        if len(users) < len(rates):
            self.logger.warning(
                "%d of %d internet user rates have no population: left out.", len(rates) - len(users), len(rates)
            )
        self.logger.debug("Internet users of %d country years.", len(users))
        return users

    ############################
    # Publicly Exposed Methods #
    ############################

    def currency_changes(
        self, catalog: MarketsCatalog, companies: Sequence[Company], rates: Sequence[FxRate]
    ) -> List[ProviderMetricValue]:
        """Measure the change of each provider's home currency against the US dollar, quarter by quarter.

        Args:
            catalog (MarketsCatalog): The catalogue (the currency of each country).
            companies (Sequence[Company]): The companies of the chronology.
            rates (Sequence[FxRate]): The stored exchange rates.

        Returns:
            List[ProviderMetricValue]: One measure per provider and quarter.
        """
        changes = {currency: self._changes(means) for currency, means in self._quarter_means(rates).items()}
        covered = sorted({quarter for by_quarter in changes.values() for quarter in by_quarter})
        values: List[ProviderMetricValue] = []
        for company in companies:
            currency = catalog.currency_of(company.country)
            if company.provider is None or currency is None:
                continue
            series = dict.fromkeys(covered, 0.0) if currency == self.PIVOT else changes.get(currency, {})
            if not series:
                self.logger.warning("No %s rate stored: no home currency criterion for %s.", currency, company.key)
            values += [
                ProviderMetricValue(
                    provider=company.provider,
                    period=quarter,
                    metric=ProviderMetric.HOME_FX_CHANGE,
                    value=change,
                    source=MetricSource.FRED,
                )
                for quarter, change in series.items()
            ]
        self.logger.info("%d home currency changes of the providers measured.", len(values))
        return values

    def internet_users(
        self, companies: Sequence[Company], weights: Sequence[WeightObservation]
    ) -> List[ProviderMetricValue]:
        """Measure the internet users of each provider's home country, each quarter taking its year's value.

        Args:
            companies (Sequence[Company]): The companies of the chronology.
            weights (Sequence[WeightObservation]): The World Bank observations of the run.

        Returns:
            List[ProviderMetricValue]: Four measures per provider and year.
        """
        users = self._users(weights)
        values = [
            ProviderMetricValue(
                provider=company.provider,
                period=f"{year:04d}Q{quarter}",
                metric=ProviderMetric.HOME_INTERNET_USERS,
                value=count,
                source=MetricSource.WORLD_BANK,
            )
            for company in companies
            if company.provider is not None and company.country
            for (country, year), count in sorted(users.items())
            if country == company.country
            for quarter in range(1, 5)
        ]
        self.logger.info("%d home internet user measures of the providers computed.", len(values))
        return values
