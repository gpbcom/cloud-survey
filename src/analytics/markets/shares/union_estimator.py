from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Set, Tuple

# First Party Imports.
from models.markets.catalog.market_area import MarketArea
from models.markets.enums import WeightIndicator
from models.markets.facts.weight_observation import WeightObservation
from models.markets.values.market_share_value import MarketShareValue


class UnionEstimator:
    """Estimate the market shares of a union of countries (the EU-27) from the shares of its members.

    Attributes:
        logger (Logger): The estimator logger.

    Notes:
        - StatCounter publishes no figure for the EU: a label's share in the union is the average of its shares in
          the members, weighted by their internet users that year (World Bank: the share of the population using
          the internet times the population).
        - A member weighs in a month only if StatCounter has figures for it that month. A label it does not show
          that month counts as zero there (StatCounter leaves the zero shares out).
        - A year the World Bank has not published yet takes the member's latest known year (the earliest one for a
          year before its first). The estimates are flagged as such, and every chart says so.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the estimator.

        Args:
            logger (Optional[Logger]): The estimator logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _users(self, weights: Sequence[WeightObservation]) -> Dict[str, Dict[int, float]]:
        """Compute the internet users of each country and year.

        Args:
            weights (Sequence[WeightObservation]): The World Bank values.

        Returns:
            Dict[str, Dict[int, float]]: The users by country and year, for the years with both indicators.
        """
        by_key: Dict[Tuple[str, int, WeightIndicator], float] = {
            (weight.country, weight.year, weight.indicator): weight.value for weight in weights
        }
        users: Dict[str, Dict[int, float]] = defaultdict(dict)
        for (country, year, indicator), value in by_key.items():
            if indicator is not WeightIndicator.INTERNET_USERS:
                continue
            population = by_key.get((country, year, WeightIndicator.POPULATION))
            if population:
                users[country][year] = value / 100.0 * population
        return users

    def _weight(self, users: Dict[int, float], year: int) -> Optional[float]:
        """Get the weight of a country in a year, carried from the nearest known year when missing.

        Args:
            users (Dict[int, float]): The internet users of the country by year.
            year (int): The year.

        Returns:
            Optional[float]: The weight, `None` when the country has no known year.
        """
        if year in users:
            return users[year]
        earlier = [known for known in users if known < year]
        later = [known for known in users if known > year]
        if earlier:
            return users[max(earlier)]
        return users[min(later)] if later else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def estimate(
        self, union: MarketArea, values: Sequence[MarketShareValue], weights: Sequence[WeightObservation]
    ) -> List[MarketShareValue]:
        """Estimate the shares of a union from those of its members.

        Args:
            union (MarketArea): The union.
            values (Sequence[MarketShareValue]): The shares of its members (other areas are left out), of one
                segment and device or several.
            weights (Sequence[WeightObservation]): The World Bank values of its members.

        Returns:
            List[MarketShareValue]: The estimated shares of the union, flagged as estimates.
        """
        users = self._users(weights)
        members = set(union.members)
        missing = sorted(member for member in members if member not in users)
        if missing:
            self.logger.warning(
                "No World Bank weight for %s: left out of the %s estimate.", ", ".join(missing), union.key
            )
        totals: Dict[Tuple[str, str, date, str, str], float] = defaultdict(float)
        present: Dict[Tuple[str, str, date, str], Set[str]] = defaultdict(set)
        samples: Dict[Tuple[str, str, date, str, str], MarketShareValue] = {}
        for value in values:
            if value.area not in members or value.area not in users:
                continue
            weight = self._weight(users[value.area], value.period.year)
            if weight is None:
                continue
            period = (value.segment, value.device.value, value.period, value.metric.value)
            key = (*period, value.label)
            totals[key] += weight * value.value
            present[period].add(value.area)
            samples.setdefault(key, value)
        estimates: List[MarketShareValue] = []
        for key, weighted in totals.items():
            period = key[:4]
            total = sum(self._weight(users[member], period[2].year) or 0.0 for member in present[period])
            if total <= 0:
                continue
            sample = samples[key]
            estimates.append(
                sample.model_copy(
                    update={
                        "area": union.key,
                        "value": min(100.0, weighted / total),
                        "estimate": True,
                        "source_url": None,
                    }
                )
            )
        self.logger.info(
            "%d shares estimated for %s from %d members.", len(estimates), union.key, len(members) - len(missing)
        )
        return estimates
