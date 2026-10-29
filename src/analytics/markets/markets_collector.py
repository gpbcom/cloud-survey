from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Type

# Third Party Imports.
from pydantic import BaseModel, JsonValue, ValidationError

# First Party Imports.
from analytics.markets.criteria.context_criteria import ContextCriteria
from analytics.markets.criteria.home_criteria import HomeCriteria
from analytics.markets.criteria.usage_criteria import UsageCriteria
from analytics.markets.shares.share_mapper import ShareMapper
from analytics.markets.shares.union_estimator import UnionEstimator
from analytics.markets.stocks.fx_converter import FxConverter
from analytics.markets.stocks.stock_metrics import StockMetrics
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.history.chronology import Chronology
from models.markets.enums import AreaKind, Device, MarketFeed, ShareSource
from models.markets.facts.fx_observation import FxObservation
from models.markets.facts.price_point import PricePoint
from models.markets.facts.release_share import ReleaseShare
from models.markets.facts.share_observation import ShareObservation
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.market_share_value import MarketShareValue
from storage.storage import Storage


class MarketsCollector:
    """Measure the facts of a markets crawl and write them, then derive what depends on several sources.

    Attributes:
        catalog (MarketsCatalog): What is read.
        chronology (Chronology): The companies (their provider and country).
        storage (Storage): The open storage.
        mapper (ShareMapper): The label and segment mapping.
        estimator (UnionEstimator): The EU-27 estimate.
        weights (List[WeightObservation]): The World Bank weights crawled in this run.
        usage (UsageCriteria): The usage and shipment criteria of the providers.
        context (ContextCriteria): The supply context criteria.
        home (HomeCriteria): The home market criteria.
        logger (Logger): The collector logger.

    Notes:
        - `write` is the sink of a crawl (`CatalogueRunner.stream_markets`): each batch is validated, measured and
          written at once, never held whole (a full StatCounter crawl is millions of shares).
        - Once the crawls are over, `finish` estimates the unions from their members' stored shares, turns the
          stored Synergy reports into cloud shares, and writes the stock measures of the providers to
          `provider_metrics` for the Rise drivers. `write_stored_shares` (the dossier's manual shares and the Synergy
          cloud shares) also runs on its own, after a statistics crawl.
        - It also turns every new source into criteria of the Rise drivers, from what is stored (so that any run
          refreshes them): the StatCounter usage and IDC shipment shares of each provider's company, the TrendForce
          concentrations as a common context, the change of the home currency (FRED). The home internet users need
          the World Bank weights of the run (they are not stored).
    """

    def __init__(
        self, catalog: MarketsCatalog, chronology: Chronology, storage: Storage, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the collector.

        Args:
            catalog (MarketsCatalog): What is read.
            chronology (Chronology): The companies.
            storage (Storage): The open storage.
            logger (Optional[Logger]): The collector logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.catalog = catalog
        self.chronology = chronology
        self.storage = storage
        self.mapper = ShareMapper(catalog, self.logger)
        self.estimator = UnionEstimator(self.logger)
        self.weights: List[WeightObservation] = []
        self.usage = UsageCriteria(self.logger)
        self.context = ContextCriteria(self.logger)
        self.home = HomeCriteria(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _facts[Fact: BaseModel](self, model: Type[Fact], items: List[Dict[str, JsonValue]]) -> List[Fact]:
        """Validate the crawled items of a source.

        Args:
            model (Type[Fact]): The fact model of the source.
            items (List[Dict[str, JsonValue]]): The crawled items.

        Returns:
            List[Fact]: The valid facts (an invalid item is logged and left out).
        """
        facts: List[Fact] = []
        for item in items:
            try:
                facts.append(model.model_validate(item))
            except ValidationError as e:
                self.logger.warning("Invalid %s item left out: %s", model.__name__, e.errors()[0]["msg"])
        return facts

    async def _estimate_unions(self) -> int:
        """Estimate the shares of every union from the stored shares of its members.

        Returns:
            int: The estimated shares written.

        Raises:
            StorageReadError: If the members' shares cannot be read.
            StorageWriteError: If the estimates cannot be written.
        """
        if not self.weights:
            self.logger.warning("No World Bank weight crawled: the unions are not estimated again.")
            return 0
        written = 0
        for union in (area for area in self.catalog.areas if area.kind is AreaKind.UNION):
            for segment in self.catalog.statcounter_segments():
                for device in segment.devices:
                    members: List[MarketShareValue] = []
                    for member in union.members:
                        members.extend(await self.storage.shares.list(segment.key, member, device))
                    written += await self.storage.shares.upsert(self.estimator.estimate(union, members, self.weights))
        return written

    async def _usage_criteria(self) -> int:
        """Replace the usage (StatCounter) and shipment (IDC) criteria of the providers from the stored shares.

        Returns:
            int: The measures written.

        Raises:
            StorageReadError: If the shares cannot be read.
            StorageWriteError: If the measures cannot be written.
        """
        companies = self.chronology.companies
        measures: Dict[MetricSource, List[ProviderMetricValue]] = {
            source: [] for source in UsageCriteria.SOURCES.values()
        }
        for key in UsageCriteria.METRICS:
            segment = self.catalog.segment(key)
            if segment is None or segment.source not in UsageCriteria.SOURCES:
                self.logger.warning("The segment %s has no StatCounter or IDC shares: no criterion.", key)
                continue
            values_by_area = {
                area: await self.storage.shares.list(key, area, Device.ALL, source=segment.source)
                for area in self.usage.areas(companies)
            }
            measured = self.usage.measure(key, segment.source, values_by_area, companies)
            measures[UsageCriteria.SOURCES[segment.source]] += measured
        written = 0
        for source, values in measures.items():
            written += await self.storage.metrics.replace_source(source, values)
        return written

    async def _context_criteria(self) -> int:
        """Replace the supply context criteria (TrendForce concentrations) of every provider.

        Returns:
            int: The measures written.

        Raises:
            StorageReadError: If the shares or the providers cannot be read.
            StorageWriteError: If the measures cannot be written.
        """
        stored = set(await self.storage.metrics.providers())
        linked = {company.provider for company in self.chronology.companies if company.provider is not None}
        providers: List[CloudProvider] = [provider for provider in CloudProvider if provider in stored | linked]
        values: List[ProviderMetricValue] = []
        for key in ContextCriteria.METRICS:
            shares = await self.storage.shares.list(key, UsageCriteria.WORLD, Device.ALL, source=ShareSource.TRENDFORCE)
            values += self.context.measure(key, shares, providers)
        if not values:
            self.logger.warning("No context criterion of %d providers: the stored ones are replaced.", len(providers))
        written = await self.storage.metrics.replace_source(MetricSource.TRENDFORCE, values)
        self.logger.info("%d context criteria of %d providers stored.", written, len(providers))
        return written

    async def _home_criteria(self, feeds: Sequence[MarketFeed]) -> int:
        """Replace the home currency criteria (FRED), and the home internet users when the World Bank was crawled.

        Args:
            feeds (Sequence[MarketFeed]): The sources crawled in this run.

        Returns:
            int: The measures written.

        Raises:
            StorageReadError: If the rates cannot be read.
            StorageWriteError: If the measures cannot be written.
        """
        companies = self.chronology.companies
        changes = self.home.currency_changes(self.catalog, companies, await self.storage.fx.list())
        written = await self.storage.metrics.replace_source(MetricSource.FRED, changes)
        if MarketFeed.WORLD_BANK in feeds and self.weights:
            users = self.home.internet_users(companies, self.weights)
            written += await self.storage.metrics.replace_source(MetricSource.WORLD_BANK, users)
        elif MarketFeed.WORLD_BANK in feeds:
            self.logger.warning("No World Bank weight crawled: the home internet users are kept as stored.")
        return written

    ############################
    # Publicly Exposed Methods #
    ############################

    async def write_stored_shares(self) -> int:
        """Write the dossier's manual shares and the cloud shares of the stored Synergy reports.

        Returns:
            int: The shares written.

        Raises:
            StorageReadError: If the Synergy reports cannot be read.
            StorageWriteError: If the shares cannot be written.

        Notes:
            Neither needs a markets crawl: a statistics crawl calls it to fill the `cloud` segment at once.
        """
        written = await self.storage.shares.upsert(self.mapper.manual())
        statistics = await self.storage.statistics.read("synergy")
        if statistics is None:
            self.logger.warning("No Synergy statistics stored: no cloud share written.")
        else:
            written += await self.storage.shares.upsert(self.mapper.synergy(statistics.reports))
        self.logger.info("%d manual and Synergy shares written.", written)
        return written

    async def write(self, feed: MarketFeed, items: List[Dict[str, JsonValue]]) -> int:
        """Measure and write a batch of crawled facts (the sink of a markets crawl).

        Args:
            feed (MarketFeed): The source of the batch.
            items (List[Dict[str, JsonValue]]): The facts, as the source states them.

        Returns:
            int: The rows written (the weights are kept for `finish`, not written).

        Raises:
            StorageWriteError: If the rows cannot be written.
        """
        match feed:
            case MarketFeed.STATCOUNTER:
                return await self.storage.shares.upsert(self.mapper.statcounter(self._facts(ShareObservation, items)))
            case MarketFeed.GOOGLE_FINANCE:
                return await self.storage.stocks.upsert(self._facts(PricePoint, items))
            case MarketFeed.FRED:
                rates = FxConverter(logger=self.logger).to_rates(self._facts(FxObservation, items), self.catalog)
                return await self.storage.fx.upsert(rates)
            case MarketFeed.TRENDFORCE | MarketFeed.IDC:
                return await self.storage.shares.replace_periods(self.mapper.releases(self._facts(ReleaseShare, items)))
            case MarketFeed.WORLD_BANK:
                weights = self._facts(WeightObservation, items)
                self.weights.extend(weights)
                self.logger.debug("%d World Bank weights kept for the union estimates.", len(weights))
                return 0

    async def finish(self, feeds: Sequence[MarketFeed]) -> int:
        """Derive what depends on several sources, once the crawls of a run are over.

        Args:
            feeds (Sequence[MarketFeed]): The sources crawled in this run.

        Returns:
            int: The rows written.

        Raises:
            StorageReadError: If the stored data cannot be read.
            StorageWriteError: If the derived rows cannot be written.
        """
        written = 0
        if MarketFeed.STATCOUNTER in feeds or MarketFeed.WORLD_BANK in feeds:
            written += await self._estimate_unions()
        written += await self.write_stored_shares()
        if MarketFeed.GOOGLE_FINANCE in feeds or MarketFeed.FRED in feeds:
            converter = FxConverter(await self.storage.fx.list(), self.logger)
            measures = StockMetrics(converter, self.logger).measure(
                self.catalog, self.chronology.companies, await self.storage.stocks.list()
            )
            written += await self.storage.metrics.replace_source(MetricSource.GOOGLE_FINANCE, measures)
        written += await self._usage_criteria()
        written += await self._context_criteria()
        written += await self._home_criteria(feeds)
        self.logger.info("%d markets rows derived after the crawls.", written)
        return written
