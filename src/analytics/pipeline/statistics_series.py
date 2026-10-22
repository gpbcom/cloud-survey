from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.series.series_transformer import SeriesTransformer
from analytics.series.time_axis import TimeAxis
from models.cloud.enums import GeoBloc, MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartMetric, ChartNote, MetricKind, MetricUnit, SeriesGrouping
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult

GroupKey = Tuple[MarketRegion, MarketSegment]


class StatisticsSeries:
    """Build the chart series of the cloud market statistics: per player, per bloc or for the whole market.

    Attributes:
        PROVIDER_REGION (ClassVar[MarketRegion]): The region of the statistics compared with the crawled providers.
        PROVIDER_SEGMENT (ClassVar[MarketSegment]): The segment of the statistics compared with the crawled providers.
        time (TimeAxis): The time axis.
        transformer (SeriesTransformer): The series transformer, pairing two metrics.
        logger (Logger): The builder logger.

    Notes:
        The share of a bloc sums the top-level shares of its players (not those included in an aggregate, e.g.
        Amazon within the big three, which would be counted twice), the computed share of the others going to the
        `OTHER` bloc: the blocs of a report sum to 100% when its leaders are quantified.
    """

    PROVIDER_REGION: ClassVar[MarketRegion] = MarketRegion.WORLDWIDE
    PROVIDER_SEGMENT: ClassVar[MarketSegment] = MarketSegment.CLOUD_INFRASTRUCTURE

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            logger (Optional[Logger]): The builder logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.time = TimeAxis(self.logger)
        self.transformer = SeriesTransformer(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _groups(self, reports: Sequence[MarketReport]) -> Dict[GroupKey, List[MarketReport]]:
        """Group reports by region and segment.

        Args:
            reports (Sequence[MarketReport]): The reports.

        Returns:
            Dict[GroupKey, List[MarketReport]]: The reports of each region and segment, in region then segment order,
                each in chronological order.
        """
        groups: Dict[GroupKey, List[MarketReport]] = {}
        for report in sorted(reports, key=lambda report: report.sort_key()):
            groups.setdefault((report.region, report.segment), []).append(report)
        regions, segments = list(MarketRegion), list(MarketSegment)
        order = sorted(groups, key=lambda key: (regions.index(key[0]), segments.index(key[1])))
        return {key: groups[key] for key in order}

    def _x(self, report: MarketReport, metric: ChartMetric) -> float:
        """Place a report on the time axis.

        Args:
            report (MarketReport): The report.
            metric (ChartMetric): The time metric: `PUBLISHED`, or the period otherwise.

        Returns:
            float: The month ordinal of its publication, or of its period.
        """
        return self.time.ordinal(report.published) if metric is ChartMetric.PUBLISHED else self.time.period(report)

    def _bloc_shares(self, report: MarketReport) -> Dict[GeoBloc, float]:
        """Sum the top-level shares of a report per bloc, the computed others in the `OTHER` bloc.

        Args:
            report (MarketReport): The report.

        Returns:
            Dict[GeoBloc, float]: The share of each bloc having one, in percent.
        """
        shares = [share for share in report.shares if share.part_of is None]
        others = report.others()
        if others is not None:
            shares.append(others)
        blocs: Dict[GeoBloc, float] = {}
        for share in shares:
            blocs[share.player.bloc] = blocs.get(share.player.bloc, 0.0) + share.share_pct
        return blocs

    def _shares(
        self, report: MarketReport, grouping: SeriesGrouping, players: Sequence[MarketPlayer], stacked: bool
    ) -> Dict[str, float]:
        """Get the shares of a report per series key.

        Args:
            report (MarketReport): The report.
            grouping (SeriesGrouping): `PLAYER`, `PROVIDER` (the players which are crawled providers) or `BLOC`.
            players (Sequence[MarketPlayer]): The players shown when grouping by player.
            stacked (bool): Whether the shares are stacked: the players within an aggregate are left out.

        Returns:
            Dict[str, float]: The share of each key, in percent.
        """
        match grouping:
            case SeriesGrouping.BLOC:
                return {bloc.value: share for bloc, share in self._bloc_shares(report).items()}
            case SeriesGrouping.PROVIDER:
                return {
                    provider.value: share.share_pct
                    for share in report.shares
                    if (provider := share.player.provider) is not None
                }
            case _:
                return {
                    player.value: share.share_pct
                    for player in players
                    if (share := report.share_of(player)) is not None and not (stacked and share.part_of is not None)
                }

    def _values(
        self,
        report: MarketReport,
        metric: ChartMetric,
        grouping: SeriesGrouping,
        players: Sequence[MarketPlayer],
        stacked: bool,
    ) -> Dict[str, float]:
        """Get the values of a metric in a report, per series key.

        Args:
            report (MarketReport): The report.
            metric (ChartMetric): The metric.
            grouping (SeriesGrouping): The grouping of the player metrics.
            players (Sequence[MarketPlayer]): The players shown when grouping by player.
            stacked (bool): Whether the values are stacked: the players within an aggregate are left out.

        Returns:
            Dict[str, float]: The value of each key (an empty key for a market-wide metric), empty when unknown.
        """
        match metric:
            case ChartMetric.SHARE:
                return self._shares(report, grouping, players, stacked)
            case ChartMetric.REVENUE if report.market_size_bn is not None:
                size = report.market_size_bn
                return {
                    key: share / 100 * size for key, share in self._shares(report, grouping, players, stacked).items()
                }
            case ChartMetric.MARKET_SIZE if report.market_size_bn is not None:
                return {"": report.market_size_bn}
            case ChartMetric.TWELVE_MONTH if report.twelve_month_bn is not None:
                return {"": report.twelve_month_bn}
            case ChartMetric.GROWTH if report.growth_pct is not None:
                return {"": report.growth_pct}
            case _:
                return {}

    def _series(
        self,
        groups: Dict[GroupKey, List[MarketReport]],
        metric: ChartMetric,
        time: ChartMetric,
        grouping: SeriesGrouping,
        players: Sequence[MarketPlayer],
        keep_groups: bool = True,
        stacked: bool = False,
    ) -> List[MetricSeries]:
        """Build the series of a metric: one per region, segment and key.

        Args:
            groups (Dict[GroupKey, List[MarketReport]]): The reports of each region and segment.
            metric (ChartMetric): The metric of the values.
            time (ChartMetric): The time metric placing the reports: `PERIOD` or `PUBLISHED`.
            grouping (SeriesGrouping): The grouping of the player metrics.
            players (Sequence[MarketPlayer]): The players shown when grouping by player.
            keep_groups (bool): Whether the series name their region and segment.
            stacked (bool): Whether the values are stacked: the players within an aggregate are left out.

        Returns:
            List[MetricSeries]: The series having values, their points named after the report periods.
        """
        built: List[MetricSeries] = []
        for (region, segment), reports in groups.items():
            points: Dict[str, List[MetricPoint]] = {}
            for report in reports:
                for key, value in self._values(report, metric, grouping, players, stacked).items():
                    point = MetricPoint(x=self._x(report, time), y=value, label=report.period)
                    points.setdefault(key, []).append(point)
            order = [player.value for player in players] + [bloc.value for bloc in GeoBloc]
            keys = sorted(points, key=lambda key: order.index(key) if key in order else len(order))
            for key in keys:
                built.append(
                    MetricSeries(
                        key=key,
                        region=region if keep_groups else None,
                        segment=segment if keep_groups else None,
                        currency=reports[-1].currency if metric.unit is MetricUnit.BILLIONS else None,
                        points=sorted(points[key], key=lambda point: point.x),
                    )
                )
        return built

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(self, reports: Sequence[MarketReport], players: Sequence[MarketPlayer], axes: ChartAxes) -> TrendResult:
        """Build the series of the statistics tab: one per region, segment and player (or bloc, or the market).

        Args:
            reports (Sequence[MarketReport]): The reports in the perimeter.
            players (Sequence[MarketPlayer]): The players shown when grouping by player.
            axes (ChartAxes): The chart axes.

        Returns:
            TrendResult: The raw series (before the forecast, transform and selection), the methodology breaks of a
                time axis and the caveats.
        """
        groups = self._groups(reports)
        timed = axes.x.kind is MetricKind.TIME
        time = axes.x if timed else ChartMetric.PERIOD
        stacked = axes.chart is ChartKind.AREA
        series = self._series(groups, axes.y, time, axes.series_by, players, stacked=stacked)
        if not timed:
            series = self.transformer.pair(self._series(groups, axes.x, time, axes.series_by, players), series)
        breaks = sorted(
            {self._x(report, time) for group in groups.values() for report in group if report.methodology_break}
        )
        notes: List[ChartNote] = []
        if breaks and timed:
            notes.append(ChartNote.METHODOLOGY_BREAK)
        if len({one.currency for one in series if one.currency}) > 1:
            notes.append(ChartNote.MIXED_CURRENCIES)
        self.logger.debug("%d statistics series built from %d reports.", len(series), len(reports))
        return TrendResult(series=series, breaks=breaks if timed else [], notes=notes)

    def provider_series(
        self, statistics: Optional[MarketStatistics], metric: ChartMetric, grouping: SeriesGrouping
    ) -> List[MetricSeries]:
        """Build the series of a statistics metric comparable with the crawled providers.

        Args:
            statistics (Optional[MarketStatistics]): The stored statistics, `None` when never crawled.
            metric (ChartMetric): The statistics metric.
            grouping (SeriesGrouping): `PROVIDER` or `BLOC`.

        Returns:
            List[MetricSeries]: One series per provider or bloc (or one for the market), without region or segment,
                over the report periods.

        Notes:
            The worldwide cloud infrastructure services reports are read: their players are the crawled providers (by
            provider) or their blocs.
        """
        if statistics is None:
            return []
        reports = [
            report
            for report in statistics.reports
            if report.region is self.PROVIDER_REGION and report.segment is self.PROVIDER_SEGMENT
        ]
        series = self._series(self._groups(reports), metric, ChartMetric.PERIOD, grouping, [], keep_groups=False)
        self.logger.debug("%d %s statistics series of the providers built.", len(series), metric.value)
        return series
