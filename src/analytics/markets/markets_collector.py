from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Type

# Third Party Imports.
from pydantic import BaseModel, JsonValue, ValidationError

# First Party Imports.
from analytics.markets.shares.share_mapper import ShareMapper
from analytics.markets.shares.union_estimator import UnionEstimator
from analytics.markets.stocks.fx_converter import FxConverter
from analytics.markets.stocks.stock_metrics import StockMetrics
from models.drivers.enums import MetricSource
from models.history.chronology import Chronology
from models.markets.enums import AreaKind, MarketFeed
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
        logger (Logger): The collector logger.

    Notes:
        - `write` is the sink of a crawl (`CatalogueRunner.stream_markets`): each batch is validated, measured and
          written at once, never held whole (a full StatCounter crawl is millions of shares).
        - Once the crawls are over, `finish` estimates the unions from their members' stored shares, turns the
          stored Synergy reports into cloud shares, and writes the stock measures of the providers to
          `provider_metrics` for the Rise drivers.
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
        self.mapper = ShareMapper(catalog)
        self.estimator = UnionEstimator()
        self.weights: List[WeightObservation] = []

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
                        members.extend(await self.storage.shares.read(segment.key, member, device))
                    written += await self.storage.shares.upsert(self.estimator.estimate(union, members, self.weights))
        return written

    ############################
    # Publicly Exposed Methods #
    ############################

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
        written += await self.storage.shares.upsert(self.mapper.manual())
        statistics = await self.storage.statistics.load("synergy")
        if statistics is not None:
            written += await self.storage.shares.upsert(self.mapper.synergy(statistics.reports))
        if MarketFeed.GOOGLE_FINANCE in feeds or MarketFeed.FRED in feeds:
            converter = FxConverter(await self.storage.fx.read(), self.logger)
            measures = StockMetrics(converter, self.logger).measure(
                self.catalog, self.chronology.companies, await self.storage.stocks.read()
            )
            written += await self.storage.metrics.replace_source(MetricSource.GOOGLE_FINANCE, measures)
        self.logger.info("%d markets rows derived after the crawls.", written)
        return written
