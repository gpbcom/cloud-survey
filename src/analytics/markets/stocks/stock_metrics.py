from __future__ import annotations

# Standard Library Imports.
import math
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.markets.stocks.fx_converter import FxConverter
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.history.catalog.company import Company
from models.markets.facts.price_point import PricePoint
from models.markets.markets_catalog import MarketsCatalog


class StockMetrics:
    """Measure the stock value and return of the cloud providers per quarter, for the Rise drivers analysis.

    Attributes:
        converter (FxConverter): The exchange rates.
        logger (Logger): The measurer logger.

    Notes:
        - A provider takes the primary listing of its company in the chronology: AWS trades as Amazon, Azure as
          Microsoft, Google Cloud as Alphabet. The value is the group's, which the analysis must keep in mind.
        - The value is the last close of the quarter in US dollars, the return the log change of that close from
          the previous quarter. Decades of quarters give the panel the long series the catalogue snapshots lack.
    """

    def __init__(self, converter: FxConverter, logger: Optional[Logger] = None) -> None:
        """Initialize the measurer.

        Args:
            converter (FxConverter): The exchange rates.
            logger (Optional[Logger]): The measurer logger.
        """
        self.converter = converter
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _quarter(self, day: date) -> str:
        """Get the quarter of a day.

        Args:
            day (date): The day.

        Returns:
            str: The quarter, `YYYYQn`.
        """
        return f"{day.year}Q{(day.month - 1) // 3 + 1}"

    def _previous(self, quarter: str) -> str:
        """Get the quarter before another.

        Args:
            quarter (str): The quarter, `YYYYQn`.

        Returns:
            str: The previous quarter.
        """
        year, number = int(quarter[:4]), int(quarter[-1])
        return f"{year - 1}Q4" if number == 1 else f"{year}Q{number - 1}"

    def _quarter_ends(self, points: Sequence[PricePoint]) -> Dict[str, Tuple[float, str]]:
        """Get the last close of each quarter in US dollars.

        Args:
            points (Sequence[PricePoint]): The prices of one listing.

        Returns:
            Dict[str, Tuple[float, str]]: The close and its source by quarter.
        """
        ends: Dict[str, Tuple[date, float, str]] = {}
        for point in points:
            value = self.converter.convert(point.close, point.currency, FxConverter.PIVOT, point.day)
            quarter = self._quarter(point.day)
            if value is not None and (quarter not in ends or point.day >= ends[quarter][0]):
                ends[quarter] = (point.day, value, point.source_url)
        return {quarter: (value, url) for quarter, (_, value, url) in ends.items()}

    ############################
    # Publicly Exposed Methods #
    ############################

    def measure(
        self, catalog: MarketsCatalog, companies: Sequence[Company], points: Sequence[PricePoint]
    ) -> List[ProviderMetricValue]:
        """Measure the stock value and return of every provider with a listed company.

        Args:
            catalog (MarketsCatalog): The listings.
            companies (Sequence[Company]): The companies of the chronology (with the provider they run).
            points (Sequence[PricePoint]): The stored prices.

        Returns:
            List[ProviderMetricValue]: Two measures per provider and quarter (the first quarter has no return).
        """
        by_listing: Dict[str, List[PricePoint]] = defaultdict(list)
        for point in points:
            by_listing[point.listing].append(point)
        values: List[ProviderMetricValue] = []
        for company in companies:
            listings = catalog.listings_of(company.key)
            if company.provider is None or not listings or not listings[0].primary:
                continue
            provider: CloudProvider = company.provider
            ends = self._quarter_ends(sorted(by_listing.get(listings[0].symbol, []), key=lambda point: point.day))
            for quarter, (close, url) in ends.items():
                values.append(
                    ProviderMetricValue(
                        provider=provider,
                        period=quarter,
                        metric=ProviderMetric.STOCK_VALUE,
                        value=close,
                        source=MetricSource.GOOGLE_FINANCE,
                        source_url=url,
                    )
                )
                previous = ends.get(self._previous(quarter))
                if previous and previous[0] > 0 and close > 0:
                    values.append(
                        ProviderMetricValue(
                            provider=provider,
                            period=quarter,
                            metric=ProviderMetric.STOCK_RETURN,
                            value=math.log(close / previous[0]),
                            source=MetricSource.GOOGLE_FINANCE,
                            source_url=url,
                        )
                    )
        self.logger.info("%d stock measures of the providers computed.", len(values))
        return values
