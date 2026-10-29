from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# First Party Imports.
from models.storage.enums import DatasetKind
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartScope,
    MatrixCell,
    MetricKind,
    OptionBlock,
    SeriesGrouping,
    ValueTransform,
)

MetricOption = Tuple[ChartMetric, Optional[OptionBlock]]
GroupingOption = Tuple[SeriesGrouping, Optional[OptionBlock]]
TransformOption = Tuple[ValueTransform, Optional[OptionBlock]]


class AxisRules:
    """Tell which chart options each scope offers, which of them can be combined, and repair the combinations.

    Attributes:
        KINDS (ClassVar[Dict[ChartScope, Tuple[ChartKind, ...]]]): The chart kinds of each scope.
        X_METRICS (ClassVar[Dict[ChartScope, Tuple[ChartMetric, ...]]]): The x axis metrics of each scope.
        Y_METRICS (ClassVar[Dict[ChartScope, Tuple[ChartMetric, ...]]]): The y axis metrics of each scope.
        GROUPINGS (ClassVar[Dict[ChartScope, Tuple[SeriesGrouping, ...]]]): The series groupings of each scope.
        MATRIX_GROUPINGS (ClassVar[Tuple[SeriesGrouping, ...]]): The rows and columns of the matrix charts.
        TRANSFORMS (ClassVar[Dict[ChartKind, Tuple[ValueTransform, ...]]]): The transforms of each chart kind.
        CALENDAR_METRICS (ClassVar[FrozenSet[ChartMetric]]): The time metrics counting calendar buckets or periods.
        ITEM_GROUPINGS (ClassVar[FrozenSet[SeriesGrouping]]): The groupings known per stored item only (the audience
            the domain and the category for the products and the software, the delivery for the software).
        DATA_BLOCKS (ClassVar[Dict[DatasetKind, OptionBlock]]): Why an option needing a dataset not stored yet is
            blocked.
        FACETS (ClassVar[Dict[ChartScope, Tuple[SeriesGrouping, ...]]]): The facet groupings of each scope (one small
            chart per value).
        FACET_KINDS (ClassVar[FrozenSet[ChartKind]]): The chart kinds which can be split into facets.
        FACET_GRAINS (ClassVar[FrozenSet[ChartMetric]]): The x axes of the facets: calendar buckets of the items.
        FACET_METRICS (ClassVar[FrozenSet[ChartMetric]]): The y axes of the facets: counted from the dated items.
        logger (Logger): The rules logger.

    Notes:
        Every option of a scope is listed with the reason it cannot be chosen with the other options, if any: the
        pickers show the blocked options disabled, with that reason, and never produce an invalid chart.
    """

    KINDS: ClassVar[Dict[ChartScope, Tuple[ChartKind, ...]]] = {
        ChartScope.STATISTICS: (ChartKind.LINE, ChartKind.AREA),
        ChartScope.CATALOGUE: (ChartKind.LINE, ChartKind.AREA, ChartKind.HEATMAP, ChartKind.MIX),
        ChartScope.MARKETPLACE: (ChartKind.LINE, ChartKind.AREA, ChartKind.HEATMAP, ChartKind.MIX),
        ChartScope.ANALYSIS: (ChartKind.LINE, ChartKind.AREA, ChartKind.BUBBLE),
    }
    X_METRICS: ClassVar[Dict[ChartScope, Tuple[ChartMetric, ...]]] = {
        ChartScope.STATISTICS: (
            ChartMetric.PERIOD,
            ChartMetric.PUBLISHED,
            ChartMetric.SHARE,
            ChartMetric.REVENUE,
            ChartMetric.MARKET_SIZE,
            ChartMetric.TWELVE_MONTH,
            ChartMetric.GROWTH,
        ),
        ChartScope.CATALOGUE: (
            ChartMetric.QUARTER,
            ChartMetric.MONTH,
            ChartMetric.YEAR,
            ChartMetric.CRAWL_DATE,
            ChartMetric.LISTED,
            ChartMetric.SHARE,
            ChartMetric.MARKETPLACE_SIZE,
        ),
        ChartScope.MARKETPLACE: (
            ChartMetric.QUARTER,
            ChartMetric.MONTH,
            ChartMetric.YEAR,
            ChartMetric.CRAWL_DATE,
            ChartMetric.LISTED,
            ChartMetric.SHARE,
            ChartMetric.CATALOGUE_SIZE,
        ),
        ChartScope.ANALYSIS: (
            ChartMetric.QUARTER,
            ChartMetric.YEAR,
            ChartMetric.SHARE,
            ChartMetric.REVENUE,
            ChartMetric.CATALOGUE_SIZE,
            ChartMetric.MARKETPLACE_SIZE,
            ChartMetric.PUBLISHERS,
        ),
    }
    Y_METRICS: ClassVar[Dict[ChartScope, Tuple[ChartMetric, ...]]] = {
        ChartScope.STATISTICS: (
            ChartMetric.SHARE,
            ChartMetric.REVENUE,
            ChartMetric.MARKET_SIZE,
            ChartMetric.TWELVE_MONTH,
            ChartMetric.GROWTH,
        ),
        ChartScope.CATALOGUE: (ChartMetric.LISTED, ChartMetric.ADDED, ChartMetric.DELETED, ChartMetric.UPDATED),
        ChartScope.MARKETPLACE: (
            ChartMetric.LISTED,
            ChartMetric.ADDED,
            ChartMetric.DELETED,
            ChartMetric.UPDATED,
            ChartMetric.PUBLISHERS,
        ),
        ChartScope.ANALYSIS: (
            ChartMetric.MARKETPLACE_SIZE,
            ChartMetric.CATALOGUE_SIZE,
            ChartMetric.PUBLISHERS,
            ChartMetric.SHARE,
            ChartMetric.REVENUE,
        ),
    }
    GROUPINGS: ClassVar[Dict[ChartScope, Tuple[SeriesGrouping, ...]]] = {
        ChartScope.STATISTICS: (SeriesGrouping.PLAYER, SeriesGrouping.BLOC),
        ChartScope.CATALOGUE: (
            SeriesGrouping.PROVIDER,
            SeriesGrouping.BLOC,
            SeriesGrouping.AUDIENCE,
            SeriesGrouping.DOMAIN,
            SeriesGrouping.CATEGORY,
        ),
        ChartScope.MARKETPLACE: (
            SeriesGrouping.PROVIDER,
            SeriesGrouping.BLOC,
            SeriesGrouping.DELIVERY,
            SeriesGrouping.AUDIENCE,
            SeriesGrouping.DOMAIN,
            SeriesGrouping.CATEGORY,
        ),
        ChartScope.ANALYSIS: (SeriesGrouping.PROVIDER, SeriesGrouping.BLOC),
    }
    MATRIX_GROUPINGS: ClassVar[Tuple[SeriesGrouping, ...]] = (
        SeriesGrouping.PROVIDER,
        SeriesGrouping.BLOC,
        SeriesGrouping.DELIVERY,
        SeriesGrouping.AUDIENCE,
        SeriesGrouping.DOMAIN,
        SeriesGrouping.CATEGORY,
    )
    TRANSFORMS: ClassVar[Dict[ChartKind, Tuple[ValueTransform, ...]]] = {
        ChartKind.LINE: (
            ValueTransform.RAW,
            ValueTransform.SHARE_OF_TOTAL,
            ValueTransform.INDEXED,
            ValueTransform.YOY,
            ValueTransform.RANK,
        ),
        ChartKind.AREA: (ValueTransform.RAW, ValueTransform.SHARE_OF_TOTAL),
    }
    CALENDAR_METRICS: ClassVar[FrozenSet[ChartMetric]] = frozenset(
        {ChartMetric.PERIOD, ChartMetric.YEAR, ChartMetric.QUARTER, ChartMetric.MONTH}
    )
    ITEM_GROUPINGS: ClassVar[FrozenSet[SeriesGrouping]] = frozenset(
        {
            SeriesGrouping.DELIVERY,
            SeriesGrouping.AUDIENCE,
            SeriesGrouping.DOMAIN,
            SeriesGrouping.CATEGORY,
        }
    )
    DATA_BLOCKS: ClassVar[Dict[DatasetKind, OptionBlock]] = {
        DatasetKind.CATALOGUE: OptionBlock.NO_CATALOGUES,
        DatasetKind.MARKETPLACE: OptionBlock.NO_MARKETPLACES,
        DatasetKind.STATISTICS: OptionBlock.NO_STATISTICS,
    }

    FACETS: ClassVar[Dict[ChartScope, Tuple[SeriesGrouping, ...]]] = {
        ChartScope.STATISTICS: (),
        ChartScope.CATALOGUE: (
            SeriesGrouping.PROVIDER,
            SeriesGrouping.BLOC,
            SeriesGrouping.AUDIENCE,
            SeriesGrouping.DOMAIN,
            SeriesGrouping.CATEGORY,
        ),
        ChartScope.MARKETPLACE: (
            SeriesGrouping.PROVIDER,
            SeriesGrouping.BLOC,
            SeriesGrouping.DELIVERY,
            SeriesGrouping.AUDIENCE,
            SeriesGrouping.DOMAIN,
            SeriesGrouping.CATEGORY,
        ),
        ChartScope.ANALYSIS: (SeriesGrouping.PROVIDER, SeriesGrouping.BLOC),
    }
    FACET_KINDS: ClassVar[FrozenSet[ChartKind]] = frozenset({ChartKind.LINE, ChartKind.AREA})
    FACET_GRAINS: ClassVar[FrozenSet[ChartMetric]] = frozenset(
        {ChartMetric.YEAR, ChartMetric.QUARTER, ChartMetric.MONTH}
    )
    FACET_METRICS: ClassVar[FrozenSet[ChartMetric]] = frozenset(
        {
            ChartMetric.ADDED,
            ChartMetric.DELETED,
            ChartMetric.LISTED,
            ChartMetric.PUBLISHERS,
            ChartMetric.CATALOGUE_SIZE,
            ChartMetric.MARKETPLACE_SIZE,
        }
    )

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the rules.

        Args:
            logger (Optional[Logger]): The rules logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _matrix_groupings(self, scope: ChartScope) -> List[SeriesGrouping]:
        """Get the rows and columns a matrix chart of a scope can have.

        Args:
            scope (ChartScope): The chart scope.

        Returns:
            List[SeriesGrouping]: The matrix groupings known for the items of the scope (no delivery nor type for the
                catalogue products).
        """
        return [grouping for grouping in self.MATRIX_GROUPINGS if grouping in self.GROUPINGS[scope]]

    def _data_block(
        self, metric: ChartMetric, scope: ChartScope, available: Optional[FrozenSet[DatasetKind]]
    ) -> Optional[OptionBlock]:
        """Tell whether the dataset of a metric is missing.

        Args:
            metric (ChartMetric): The metric.
            scope (ChartScope): The chart scope.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown (all assumed).

        Returns:
            Optional[OptionBlock]: Why the metric cannot be shown, `None` when its dataset is stored.
        """
        dataset = metric.source or scope.dataset
        if available is None or dataset is None or dataset in available:
            return None
        return self.DATA_BLOCKS[dataset]

    def _grouping_block(self, metric: ChartMetric, axes: ChartAxes) -> Optional[OptionBlock]:
        """Tell whether a metric is unknown per value of the series grouping.

        Args:
            metric (ChartMetric): The metric.
            axes (ChartAxes): The chart axes.

        Returns:
            Optional[OptionBlock]: `NOT_PER_GROUPING` when the metric is unknown per value, `None` otherwise.

        Notes:
            The delivery methods, the audiences, the domains and the categories are only known for the items of the
            chart's own dataset: the market statistics, the other datasets and the crawl records are not split by
            them.
        """
        if axes.series_by not in self.ITEM_GROUPINGS:
            return None
        own = metric.source in (None, axes.scope.dataset)
        recorded = metric in (ChartMetric.UPDATED, ChartMetric.CRAWL_DATE)
        return OptionBlock.NOT_PER_GROUPING if recorded or not own else None

    def _metric_block(
        self, metric: ChartMetric, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]]
    ) -> Optional[OptionBlock]:
        """Tell whether a metric is unknown per series or not stored yet.

        Args:
            metric (ChartMetric): The metric.
            axes (ChartAxes): The chart axes.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            Optional[OptionBlock]: Why the metric cannot be chosen, `None` when it can.
        """
        return self._grouping_block(metric, axes) or self._data_block(metric, axes.scope, available)

    def _pick[T](self, options: List[Tuple[T, Optional[OptionBlock]]], current: T) -> T:
        """Keep an option if it can be chosen, otherwise take the first one which can.

        Args:
            options (List[Tuple[T, Optional[OptionBlock]]]): The options, with why each is blocked.
            current (T): The chosen option.

        Returns:
            T: The chosen option if it is not blocked, the first option not blocked otherwise, the chosen one when
                every option is blocked.
        """
        allowed = [option for option, block in options if block is None]
        if current in allowed or not allowed:
            return current
        return allowed[0]

    ############################
    # Publicly Exposed Methods #
    ############################

    def kinds(self, scope: ChartScope) -> List[ChartKind]:
        """Get the chart kinds of a scope.

        Args:
            scope (ChartScope): The chart scope.

        Returns:
            List[ChartKind]: The chart kinds, the default first.
        """
        return list(self.KINDS[scope])

    def groupings(self, axes: ChartAxes) -> List[GroupingOption]:
        """Get the series groupings (the rows of a matrix chart) and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[GroupingOption]: Each grouping, with why it cannot be chosen (`None` when it can).
        """
        if axes.chart.is_matrix:
            pairs = axes.cell.publisher_pairs
            return [
                (grouping, OptionBlock.NEEDS_PROVIDERS if pairs and grouping is not SeriesGrouping.PROVIDER else None)
                for grouping in self._matrix_groupings(axes.scope)
            ]
        options: List[GroupingOption] = []
        for grouping in self.GROUPINGS[axes.scope]:
            grouped = axes.model_copy(update={"series_by": grouping})
            blocked = grouping in self.ITEM_GROUPINGS and axes.x is ChartMetric.CRAWL_DATE
            block = OptionBlock.NOT_PER_GROUPING if blocked else self._grouping_block(axes.y, grouped)
            options.append((grouping, block))
        return options

    def column_options(self, axes: ChartAxes) -> List[GroupingOption]:
        """Get the columns of a matrix chart and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[GroupingOption]: Each grouping, with why it cannot be the columns (`None` when it can).
        """
        options: List[GroupingOption] = []
        for grouping in self._matrix_groupings(axes.scope):
            if axes.cell.publisher_pairs:
                options.append((grouping, None if grouping is SeriesGrouping.PROVIDER else OptionBlock.NEEDS_PROVIDERS))
            else:
                options.append((grouping, OptionBlock.SAME_AS_ROWS if grouping is axes.series_by else None))
        return options

    def cell_options(self, axes: ChartAxes) -> List[MatrixCell]:
        """Get what the cells of a matrix chart can count.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[MatrixCell]: The cell metrics of the chart kind (a mix of bars always shows the row shares), without
                the publisher cells for the catalogue products (they have no publisher).
        """
        if axes.chart is ChartKind.MIX:
            return [MatrixCell.ROW_SHARE]
        if axes.scope is ChartScope.CATALOGUE:
            return [MatrixCell.LISTED, MatrixCell.ROW_SHARE]
        return list(MatrixCell)

    def x_options(self, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]] = None) -> List[MetricOption]:
        """Get the x axis metrics and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            List[MetricOption]: Each metric, with why it cannot be chosen (`None` when it can).
        """
        options: List[MetricOption] = []
        for metric in self.X_METRICS[axes.scope]:
            block: Optional[OptionBlock] = None
            if axes.chart is ChartKind.AREA and metric.kind is not MetricKind.TIME:
                block = OptionBlock.NEEDS_TIME_AXIS
            elif axes.chart is ChartKind.BUBBLE and metric.kind is MetricKind.TIME:
                block = OptionBlock.NEEDS_NUMERIC_AXIS
            options.append((metric, block or self._metric_block(metric, axes, available)))
        return options

    def y_options(self, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]] = None) -> List[MetricOption]:
        """Get the y axis metrics and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            List[MetricOption]: Each metric, with why it cannot be chosen (`None` when it can).
        """
        options: List[MetricOption] = []
        for metric in self.Y_METRICS[axes.scope]:
            block: Optional[OptionBlock] = None
            if metric is axes.x:
                block = OptionBlock.SAME_AS_X
            elif axes.chart is ChartKind.AREA and not metric.additive:
                block = OptionBlock.NOT_ADDITIVE
            elif axes.x is ChartMetric.CRAWL_DATE and not metric.from_crawls:
                block = OptionBlock.NOT_FROM_CRAWLS
            options.append((metric, block or self._metric_block(metric, axes, available)))
        return options

    def size_options(self, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]] = None) -> List[MetricOption]:
        """Get the bubble size metrics and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            List[MetricOption]: Each numeric metric of the scope, with why it cannot be chosen (`None` when it can).
        """
        metrics = dict.fromkeys(self.Y_METRICS[axes.scope] + self.X_METRICS[axes.scope])
        options: List[MetricOption] = []
        for metric in metrics:
            if metric.kind is MetricKind.TIME:
                continue
            same = metric in (axes.x, axes.y)
            options.append((metric, OptionBlock.SAME_AS_X if same else self._metric_block(metric, axes, available)))
        return options

    def transforms(self, axes: ChartAxes) -> List[TransformOption]:
        """Get the value transforms of the chart kind and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[TransformOption]: Each transform, with why it cannot be chosen (`None` when it can).
        """
        timed = axes.x.kind is MetricKind.TIME
        options: List[TransformOption] = []
        for transform in self.TRANSFORMS.get(axes.chart, (ValueTransform.RAW,)):
            block: Optional[OptionBlock] = None
            if transform is not ValueTransform.RAW and not timed:
                block = OptionBlock.NEEDS_TIME_AXIS
            elif transform is ValueTransform.YOY and axes.x not in self.CALENDAR_METRICS:
                block = OptionBlock.NEEDS_CALENDAR_AXIS
            elif transform is ValueTransform.SHARE_OF_TOTAL and not axes.y.additive:
                block = OptionBlock.NOT_ADDITIVE
            options.append((transform, block))
        return options

    def facet_options(self, axes: ChartAxes) -> List[Tuple[Optional[SeriesGrouping], Optional[OptionBlock]]]:
        """Get the facet groupings of a chart (one small chart per value) and why each is blocked.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[Tuple[Optional[SeriesGrouping], Optional[OptionBlock]]]: `None` first (one chart, always allowed),
                then each facet grouping of the scope, with why it cannot be chosen (`None` when it can).

        Notes:
            The facets split the items counted over calendar buckets (lines or areas): the market statistics and the
            crawl records are not split per item.
        """
        options: List[Tuple[Optional[SeriesGrouping], Optional[OptionBlock]]] = [(None, None)]
        common: Optional[OptionBlock] = None
        if axes.chart not in self.FACET_KINDS or axes.x.kind is not MetricKind.TIME:
            common = OptionBlock.NEEDS_TIME_AXIS
        elif axes.x not in self.FACET_GRAINS:
            common = OptionBlock.NEEDS_CALENDAR_AXIS
        elif axes.y not in self.FACET_METRICS:
            common = OptionBlock.NOT_PER_GROUPING
        for grouping in self.FACETS[axes.scope]:
            if common is not None:
                options.append((grouping, common))
            elif grouping is axes.series_by:
                options.append((grouping, OptionBlock.SAME_AS_SERIES))
            else:
                options.append(
                    (grouping, self._grouping_block(axes.y, axes.model_copy(update={"series_by": grouping})))
                )
        return options

    def forecastable(self, axes: ChartAxes) -> Optional[OptionBlock]:
        """Tell whether the series of a chart can be extrapolated.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            Optional[OptionBlock]: Why there is no forecast (it needs lines or areas over time), `None` when allowed.
        """
        if axes.chart in (ChartKind.LINE, ChartKind.AREA) and axes.x.kind is MetricKind.TIME:
            return None
        return OptionBlock.NEEDS_TIME_AXIS

    def derivable(self, axes: ChartAxes) -> Optional[OptionBlock]:
        """Tell whether a chart can draw the rate of change of its series.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            Optional[OptionBlock]: Why there is no derivative (it needs a line chart), `None` when allowed.
        """
        return None if axes.chart is ChartKind.LINE else OptionBlock.NEEDS_LINE_CHART

    def repair(self, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]] = None) -> ChartAxes:
        """Turn axes into a valid combination, keeping every choice which can be kept.

        Args:
            axes (ChartAxes): The chart axes, maybe invalid (e.g. restored from a former version).
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            ChartAxes: The valid axes, equal to the given ones when they are valid.

        Notes:
            The options are settled in dependency order: the chart kind, then the grouping (or the matrix cell, rows and
            columns), the x axis, the y axis, the bubble size, the transform, the forecast and the facets. An option
            which cannot be kept is replaced with the first one which can.
        """
        kinds = self.kinds(axes.scope)
        fixed = axes if axes.chart in kinds else axes.model_copy(update={"chart": kinds[0]})
        if fixed.chart.is_matrix:
            cells = self.cell_options(fixed)
            fixed = fixed if fixed.cell in cells else fixed.model_copy(update={"cell": cells[0]})
            fixed = fixed.model_copy(update={"series_by": self._pick(self.groupings(fixed), fixed.series_by)})
            fixed = fixed.model_copy(update={"columns": self._pick(self.column_options(fixed), fixed.columns)})
            update = {
                "transform": ValueTransform.RAW,
                "forecast": False,
                "log_scale": False,
                "derivative": False,
                "size": None,
                "facet_by": None,
            }
            repaired = fixed.model_copy(update=update)
        else:
            fixed = fixed.model_copy(update={"series_by": self._pick(self.groupings(fixed), fixed.series_by)})
            fixed = fixed.model_copy(update={"x": self._pick(self.x_options(fixed, available), fixed.x)})
            fixed = fixed.model_copy(update={"y": self._pick(self.y_options(fixed, available), fixed.y)})
            # The grouping may only be known now that the axes are settled.
            fixed = fixed.model_copy(update={"series_by": self._pick(self.groupings(fixed), fixed.series_by)})
            size: Optional[ChartMetric] = None
            if fixed.chart is ChartKind.BUBBLE:
                sizes = self.size_options(fixed, available)
                allowed = [metric for metric, block in sizes if block is None]
                size = fixed.size if fixed.size in allowed else (allowed[0] if allowed else None)
            transform = self._pick(self.transforms(fixed), fixed.transform)
            repaired = fixed.model_copy(
                update={
                    "size": size,
                    "transform": transform,
                    "forecast": fixed.forecast and self.forecastable(fixed) is None,
                    "log_scale": fixed.log_scale and fixed.chart is ChartKind.BUBBLE,
                    "derivative": fixed.derivative and self.derivable(fixed) is None,
                }
            )
            facets = dict(self.facet_options(repaired))
            if repaired.facet_by is not None and facets.get(repaired.facet_by, OptionBlock.NOT_PER_GROUPING):
                repaired = repaired.model_copy(update={"facet_by": None})
        if repaired != axes:
            self.logger.debug("Chart axes repaired: %s became %s.", axes, repaired)
        return repaired

    def is_valid(self, axes: ChartAxes, available: Optional[FrozenSet[DatasetKind]] = None) -> bool:
        """Tell whether axes are a valid combination.

        Args:
            axes (ChartAxes): The chart axes.
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.

        Returns:
            bool: Whether repairing the axes leaves them unchanged.
        """
        return self.repair(axes, available) == axes
