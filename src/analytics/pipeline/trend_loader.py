from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Sequence

# First Party Imports.
from analytics.pipeline.chart_assembler import ChartAssembler
from analytics.pipeline.statistics_series import StatisticsSeries
from analytics.series.axis_rules import AxisRules
from analytics.series.series_transformer import SeriesTransformer
from analytics.series.time_axis import TimeAxis
from models.cloud.enums import CloudProvider
from models.stats.market_statistics import MarketStatistics
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartNote, ChartScope, MetricKind, SeriesGrouping
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult
from storage.storage import Storage


class TrendLoader:
    """Read the series of a chart of the stored datasets, and assemble them: the job of a chart storage request.

    Attributes:
        PAIR_GRAIN (ClassVar[ChartMetric]): The calendar bucket two metrics are compared in (numeric x axis, bubbles).
        COUNTED (ClassVar[FrozenSet[ChartMetric]]): The metrics counted from the dated items.
        UNDATED_SHARE (ClassVar[float]): The share of items dated by their first crawl above which the footnote warns.
        statistics_source (str): The market statistics source compared with the providers.
        rules (AxisRules): The chart rules.
        time (TimeAxis): The time axis.
        statistics (StatisticsSeries): The builder of the market statistics series.
        transformer (SeriesTransformer): The series transformer.
        assembler (ChartAssembler): The assembler of the drawn series.
        logger (Logger): The loader logger.

    Notes:
        - A metric is read from its own dataset (e.g. the market share from the statistics), or from the dataset of
          the chart scope. The filters of the scope apply to its own dataset only: the other datasets are only
          filtered on the providers.
        - The levels counted per bucket (e.g. the listed items) are carried forward to the current bucket.
    """

    PAIR_GRAIN: ClassVar[ChartMetric] = ChartMetric.QUARTER
    COUNTED: ClassVar[FrozenSet[ChartMetric]] = frozenset(
        {
            ChartMetric.ADDED,
            ChartMetric.DELETED,
            ChartMetric.LISTED,
            ChartMetric.CATALOGUE_SIZE,
            ChartMetric.MARKETPLACE_SIZE,
            ChartMetric.PUBLISHERS,
        }
    )
    UNDATED_SHARE: ClassVar[float] = 0.1

    def __init__(self, statistics_source: str, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            statistics_source (str): The market statistics source compared with the providers (e.g. `synergy`).
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.statistics_source = statistics_source
        self.rules = AxisRules(self.logger)
        self.time = TimeAxis(self.logger)
        self.statistics = StatisticsSeries(self.logger)
        self.transformer = SeriesTransformer(self.logger)
        self.assembler = ChartAssembler(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _dataset(self, metric: ChartMetric, axes: ChartAxes) -> DatasetKind:
        """Get the dataset a metric is read from.

        Args:
            metric (ChartMetric): The metric.
            axes (ChartAxes): The chart axes.

        Returns:
            DatasetKind: Its own dataset, or the dataset of the chart scope (the catalogues for the analysis).
        """
        return metric.source or axes.scope.dataset or DatasetKind.CATALOGUE

    def _query(self, dataset: DatasetKind, axes: ChartAxes, query: ItemQuery) -> ItemQuery:
        """Get the filters of the items of a dataset.

        Args:
            dataset (DatasetKind): The dataset read.
            axes (ChartAxes): The chart axes.
            query (ItemQuery): The filters of the chart scope.

        Returns:
            ItemQuery: The scope filters for its own dataset, its providers only for another dataset.
        """
        return query if dataset is axes.scope.dataset else ItemQuery(providers=query.providers)

    def _crawl_value(self, crawl: CrawlSummary, metric: ChartMetric) -> float:
        """Get what a crawl recorded of a metric.

        Args:
            crawl (CrawlSummary): The crawl.
            metric (ChartMetric): `ADDED`, `DELETED`, `UPDATED` or `LISTED`.

        Returns:
            float: The number of items added, deleted, updated, or listed after the crawl.
        """
        match metric:
            case ChartMetric.ADDED:
                return float(crawl.added)
            case ChartMetric.DELETED:
                return float(crawl.deleted)
            case ChartMetric.UPDATED:
                return float(crawl.updated)
            case _:
                return float(crawl.size)

    def _crawl_points(
        self, crawls: List[CrawlSummary], metric: ChartMetric, grain: Optional[ChartMetric]
    ) -> List[MetricPoint]:
        """Get the points of the crawls of a provider.

        Args:
            crawls (List[CrawlSummary]): The crawls of the provider, in start order.
            metric (ChartMetric): The recorded metric.
            grain (Optional[ChartMetric]): The calendar bucket, `None` for a point per crawl.

        Returns:
            List[MetricPoint]: The points: per crawl, or per bucket (the flows summed, the levels at the last crawl).
        """
        if grain is None:
            return [
                MetricPoint(x=self.time.ordinal(crawl.started_at), y=self._crawl_value(crawl, metric))
                for crawl in crawls
            ]
        buckets: Dict[float, float] = {}
        for crawl in crawls:
            at = self.time.bucket(self.time.ordinal(crawl.started_at), grain)
            value = self._crawl_value(crawl, metric)
            buckets[at] = value if metric.stock else buckets.get(at, 0.0) + value
        return [MetricPoint(x=at, y=value) for at, value in sorted(buckets.items())]

    async def _crawl_series(
        self,
        storage: Storage,
        dataset: DatasetKind,
        metric: ChartMetric,
        grain: Optional[ChartMetric],
        grouping: SeriesGrouping,
        providers: Sequence[CloudProvider],
    ) -> List[MetricSeries]:
        """Read the series of a metric recorded by the crawls.

        Args:
            storage (Storage): The open storage.
            dataset (DatasetKind): The crawled dataset.
            metric (ChartMetric): `ADDED`, `DELETED`, `UPDATED` or `LISTED`.
            grain (Optional[ChartMetric]): The calendar bucket, `None` for a point per crawl.
            grouping (SeriesGrouping): `PROVIDER` or `BLOC`.
            providers (Sequence[CloudProvider]): The providers read, every one when empty.

        Returns:
            List[MetricSeries]: One series per provider (or bloc, the providers summed).
        """
        crawls = await storage.crawls.history(dataset, providers)
        by_provider: Dict[str, List[CrawlSummary]] = {}
        for crawl in crawls:
            by_provider.setdefault(crawl.dataset, []).append(crawl)
        series = [
            MetricSeries(key=provider, points=self._crawl_points(found, metric, grain))
            for provider, found in by_provider.items()
        ]
        if grouping is SeriesGrouping.BLOC:
            blocs = {provider.value: provider.bloc.value for provider in CloudProvider}
            series = self.transformer.combine(series, blocs, metric)
        return series

    async def _series(
        self,
        storage: Storage,
        metric: ChartMetric,
        grain: ChartMetric,
        axes: ChartAxes,
        query: ItemQuery,
        statistics: Optional[MarketStatistics],
    ) -> List[MetricSeries]:
        """Read the series of a metric per calendar bucket.

        Args:
            storage (Storage): The open storage.
            metric (ChartMetric): The metric.
            grain (ChartMetric): The calendar bucket.
            axes (ChartAxes): The chart axes.
            query (ItemQuery): The filters of the chart scope.
            statistics (Optional[MarketStatistics]): The stored market statistics, `None` when not needed or never
                crawled.

        Returns:
            List[MetricSeries]: One series per key of the series grouping.
        """
        dataset = self._dataset(metric, axes)
        if dataset is DatasetKind.STATISTICS:
            return self.statistics.provider_series(statistics, metric, axes.series_by)
        if metric is ChartMetric.UPDATED:
            return await self._crawl_series(storage, dataset, metric, grain, axes.series_by, query.providers)
        counted = ChartMetric.LISTED if metric in (ChartMetric.CATALOGUE_SIZE, ChartMetric.MARKETPLACE_SIZE) else metric
        series = await storage.trends.series(
            dataset, counted, grain, self._query(dataset, axes, query), axes.series_by, axes.facet_by
        )
        if counted.stock:
            series = self.transformer.extend(series, self.time.bucket(self.time.now(), grain))
        return series

    async def _notes(
        self, storage: Storage, axes: ChartAxes, query: ItemQuery, metrics: List[ChartMetric]
    ) -> List[ChartNote]:
        """Find the caveats of the figures of a chart.

        Args:
            storage (Storage): The open storage.
            axes (ChartAxes): The chart axes.
            query (ItemQuery): The filters of the chart scope.
            metrics (List[ChartMetric]): The metrics of the chart axes.

        Returns:
            List[ChartNote]: The caveats.
        """
        notes: List[ChartNote] = []
        if ChartMetric.UPDATED in metrics or ChartMetric.CRAWL_DATE in metrics:
            notes.append(ChartNote.CRAWL_HISTORY)
        if axes.scope is not ChartScope.STATISTICS and any(metric.player_scoped for metric in metrics):
            notes.append(ChartNote.PLAYER_PROVIDERS)
        if ChartMetric.PUBLISHERS in metrics:
            notes.append(ChartNote.PUBLISHERS_FIRST_SEEN)
        if ChartMetric.CRAWL_DATE not in metrics:
            datasets = {self._dataset(metric, axes) for metric in metrics if metric in self.COUNTED}
            for dataset in sorted(datasets):
                if await storage.trends.undated_share(dataset, self._query(dataset, axes, query)) > self.UNDATED_SHARE:
                    notes.append(ChartNote.FIRST_CRAWL_DATES)
                    break
        return notes

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, storage: Storage, axes: ChartAxes, query: ItemQuery) -> TrendResult:
        """Read and assemble the series of a chart (not a matrix chart).

        Args:
            storage (Storage): The open storage.
            axes (ChartAxes): The chart axes (repaired when invalid).
            query (ItemQuery): The filters of the chart scope (for the catalogue and marketplace charts).

        Returns:
            TrendResult: The drawn series, empty for a matrix chart (logged).

        Raises:
            StorageReadError: If the stored data cannot be read.
        """
        axes = self.rules.repair(axes)
        if axes.chart.is_matrix:
            self.logger.warning("The %s chart is a matrix: it has no series.", axes.chart.value)
            return TrendResult()
        metrics = [axes.x, axes.y] + ([axes.size] if axes.size is not None else [])
        needs_statistics = any(self._dataset(metric, axes) is DatasetKind.STATISTICS for metric in metrics)
        statistics = await storage.statistics.read(self.statistics_source) if needs_statistics else None
        as_of: Optional[float] = None
        dataset = self._dataset(axes.y, axes)
        if axes.x is ChartMetric.CRAWL_DATE:
            series = await self._crawl_series(storage, dataset, axes.y, None, axes.series_by, query.providers)
        elif axes.x.kind is MetricKind.TIME:
            series = await self._series(storage, axes.y, axes.x, axes, query, statistics)
        else:
            xs = await self._series(storage, axes.x, self.PAIR_GRAIN, axes, query, statistics)
            ys = await self._series(storage, axes.y, self.PAIR_GRAIN, axes, query, statistics)
            if axes.chart is ChartKind.BUBBLE:
                sizes = (
                    await self._series(storage, axes.size, self.PAIR_GRAIN, axes, query, statistics)
                    if axes.size is not None
                    else []
                )
                series, as_of = self.transformer.snapshot(xs, ys, sizes, self.PAIR_GRAIN)
            else:
                series = self.transformer.pair(xs, ys, self.PAIR_GRAIN)
        notes = await self._notes(storage, axes, query, metrics)
        result = self.assembler.assemble(axes, TrendResult(series=series, notes=notes, as_of=as_of))
        self.logger.debug("%s chart of %s loaded: %d series.", axes.chart.value, axes.y.value, len(result.series))
        return result
