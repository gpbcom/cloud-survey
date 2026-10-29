from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from statistics import fmean
from typing import ClassVar, Dict, List, Mapping, Optional, Sequence, Tuple

# First Party Imports.
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.history.catalog.company import Company
from models.markets.enums import Granularity, ShareSource
from models.markets.values.market_share_value import MarketShareValue


class UsageCriteria:
    """Turn the usage shares (StatCounter) and the shipment shares (IDC) into quarterly criteria of the providers.

    Attributes:
        METRICS (ClassVar[Dict[str, Tuple[ProviderMetric, ProviderMetric]]]): The worldwide and the home-country
            criterion of each segment read.
        SOURCES (ClassVar[Dict[ShareSource, MetricSource]]): The source of the criteria of each share source.
        WORLD (ClassVar[str]): The area of the worldwide criteria.
        calendar (QuarterCalendar): Names the quarters.
        logger (Logger): The measurer logger.

    Notes:
        - A provider takes the shares of the company running it in the chronology (`Company.provider`): Azure takes
          Microsoft's Bing, Edge and Windows, Google Cloud takes Google's search, Chrome and Android. The labels of a
          company are summed in each period.
        - A monthly share (StatCounter) becomes the mean of the quarter's months, a quarterly share (IDC) is kept as
          it is, a yearly total is left out (it is not a quarter).
        - The home criterion reads the area of the company's headquarters (`Company.country`): Yandex in Russia,
          Baidu in China. A company missing from a period has no value there, never a zero.
    """

    METRICS: ClassVar[Dict[str, Tuple[ProviderMetric, ProviderMetric]]] = {
        "search": (ProviderMetric.USAGE_SEARCH, ProviderMetric.USAGE_SEARCH_HOME),
        "browsers": (ProviderMetric.USAGE_BROWSERS, ProviderMetric.USAGE_BROWSERS_HOME),
        "operating-systems": (ProviderMetric.USAGE_OS, ProviderMetric.USAGE_OS_HOME),
        "device-vendors": (ProviderMetric.USAGE_DEVICE_VENDORS, ProviderMetric.USAGE_DEVICE_VENDORS_HOME),
        "ai-chatbots": (ProviderMetric.USAGE_AI_CHATBOTS, ProviderMetric.USAGE_AI_CHATBOTS_HOME),
        "pcs": (ProviderMetric.SHIPMENTS_PCS, ProviderMetric.SHIPMENTS_PCS_HOME),
        "smartphones": (ProviderMetric.SHIPMENTS_SMARTPHONES, ProviderMetric.SHIPMENTS_SMARTPHONES_HOME),
        "tablets": (ProviderMetric.SHIPMENTS_TABLETS, ProviderMetric.SHIPMENTS_TABLETS_HOME),
    }
    SOURCES: ClassVar[Dict[ShareSource, MetricSource]] = {
        ShareSource.STATCOUNTER: MetricSource.STATCOUNTER,
        ShareSource.IDC: MetricSource.IDC,
    }
    WORLD: ClassVar[str] = "ww"

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

    def _quarters(self, values: Sequence[MarketShareValue], company: str) -> Dict[str, Tuple[float, Optional[str]]]:
        """Get a company's share of each quarter, with the document of its last period.

        Args:
            values (Sequence[MarketShareValue]): The shares of one segment and area.
            company (str): The company.

        Returns:
            Dict[str, Tuple[float, Optional[str]]]: The share (mean of the quarter's periods) and the document, by
                quarter.
        """
        periods: Dict[date, float] = defaultdict(float)
        documents: Dict[date, Optional[str]] = {}
        for value in values:
            if value.company == company and value.granularity in (Granularity.MONTH, Granularity.QUARTER):
                periods[value.period] += value.value
                documents[value.period] = value.source_url
        by_quarter: Dict[str, List[date]] = defaultdict(list)
        for period in sorted(periods):
            by_quarter[self.calendar.of_day(period)].append(period)
        if not by_quarter:
            self.logger.warning("No monthly or quarterly share of %s.", company)
        else:
            self.logger.debug("%d quarters of shares of %s.", len(by_quarter), company)
        return {
            quarter: (fmean(periods[period] for period in days), documents[days[-1]])
            for quarter, days in by_quarter.items()
        }

    def _criteria(
        self,
        metric: ProviderMetric,
        source: MetricSource,
        provider: CloudProvider,
        quarters: Dict[str, Tuple[float, Optional[str]]],
    ) -> List[ProviderMetricValue]:
        """Write the quarterly shares of a provider as measures.

        Args:
            metric (ProviderMetric): The criterion.
            source (MetricSource): Its source.
            provider (CloudProvider): The provider.
            quarters (Dict[str, Tuple[float, Optional[str]]]): The share and the document of each quarter.

        Returns:
            List[ProviderMetricValue]: One measure per quarter.
        """
        return [
            ProviderMetricValue(
                provider=provider, period=quarter, metric=metric, value=value, source=source, source_url=url
            )
            for quarter, (value, url) in sorted(quarters.items())
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def areas(self, companies: Sequence[Company]) -> List[str]:
        """List the areas to read: worldwide, then the countries of the providers' companies.

        Args:
            companies (Sequence[Company]): The companies of the chronology.

        Returns:
            List[str]: The areas, each once.
        """
        homes = sorted({company.country for company in companies if company.provider and company.country})
        self.logger.debug("Usage areas: worldwide and %d home countries.", len(homes))
        return [self.WORLD, *homes]

    def measure(
        self,
        segment: str,
        source: ShareSource,
        values_by_area: Mapping[str, Sequence[MarketShareValue]],
        companies: Sequence[Company],
    ) -> List[ProviderMetricValue]:
        """Measure the worldwide and home criteria of a segment for every provider with a company.

        Args:
            segment (str): The segment, a key of `METRICS`.
            source (ShareSource): The source of its shares (StatCounter or IDC).
            values_by_area (Mapping[str, Sequence[MarketShareValue]]): The shares of the segment, by area (all
                devices).
            companies (Sequence[Company]): The companies of the chronology.

        Returns:
            List[ProviderMetricValue]: The measures, none when the segment or the source has no criterion.
        """
        metrics = self.METRICS.get(segment)
        metric_source = self.SOURCES.get(source)
        if metrics is None or metric_source is None:
            self.logger.warning("No provider criterion for %s from %s: left out.", segment, source.value)
            return []
        world, home = metrics
        values: List[ProviderMetricValue] = []
        for company in companies:
            if company.provider is None:
                continue
            quarters = self._quarters(values_by_area.get(self.WORLD, []), company.key)
            values += self._criteria(world, metric_source, company.provider, quarters)
            if company.country:
                quarters = self._quarters(values_by_area.get(company.country, []), company.key)
                values += self._criteria(home, metric_source, company.provider, quarters)
        self.logger.info("%d %s criteria of the providers measured from %s.", len(values), segment, source.value)
        return values
