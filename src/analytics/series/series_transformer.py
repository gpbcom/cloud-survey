from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Set, Tuple

# First Party Imports.
from analytics.series.time_axis import TimeAxis
from models.cloud.enums import MarketRegion, MarketSegment
from models.trends.enums import ChartMetric, MetricUnit, ValueTransform
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries

SeriesIdentity = Tuple[str, Optional[MarketRegion], Optional[MarketSegment]]
BucketValues = Dict[float, Tuple[float, Optional[str]]]


class SeriesTransformer:
    """Reshape chart series: align them, transform their values, pair two metrics, keep the largest series.

    Attributes:
        OTHERS_KEY (ClassVar[str]): The key of the series merging the series not kept.
        YOY_MONTHS (ClassVar[float]): The distance of the year-on-year comparison, in months.
        TOLERANCE (ClassVar[float]): How far two x values may be and still be the same point.
        time (TimeAxis): The time axis.
        logger (Logger): The transformer logger.
    """

    OTHERS_KEY: ClassVar[str] = "*"
    YOY_MONTHS: ClassVar[float] = 12.0
    TOLERANCE: ClassVar[float] = 0.5

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the transformer.

        Args:
            logger (Optional[Logger]): The transformer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.time = TimeAxis(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _identity(self, series: MetricSeries) -> SeriesIdentity:
        """Get what tells a series apart from the others.

        Args:
            series (MetricSeries): The series.

        Returns:
            SeriesIdentity: Its key, region and segment.
        """
        return series.key, series.region, series.segment

    def _x(self, value: float) -> float:
        """Round an x value so that equal values compare equal.

        Args:
            value (float): The x value.

        Returns:
            float: The rounded value.
        """
        return round(value, 6)

    def _share_of_total(self, series: List[MetricSeries]) -> List[MetricSeries]:
        """Turn each value into its share of the total of every series at the same x.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            List[MetricSeries]: The shares, in percent (0 where the total is 0).
        """
        totals: Dict[float, float] = {}
        for one in series:
            for point in one.points:
                totals[self._x(point.x)] = totals.get(self._x(point.x), 0.0) + point.y
        return [
            one.model_copy(
                update={
                    "points": [
                        point.model_copy(
                            update={"y": point.y / totals[self._x(point.x)] * 100 if totals[self._x(point.x)] else 0}
                        )
                        for point in one.points
                    ]
                }
            )
            for one in series
        ]

    def _indexed(self, series: List[MetricSeries]) -> List[MetricSeries]:
        """Index each series to 100 at its first non-zero value.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            List[MetricSeries]: The indexed series, the points before the base dropped.
        """
        indexed: List[MetricSeries] = []
        for one in series:
            start = next((index for index, point in enumerate(one.points) if point.y != 0), None)
            if start is None:
                indexed.append(one.model_copy(update={"points": []}))
                continue
            base = one.points[start].y
            points = [point.model_copy(update={"y": point.y / base * 100}) for point in one.points[start:]]
            indexed.append(one.model_copy(update={"points": points}))
        return indexed

    def _year_on_year(self, series: List[MetricSeries]) -> List[MetricSeries]:
        """Turn each value into its change from the value twelve months before.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            List[MetricSeries]: The changes, in percent, the points without a non-zero value a year before dropped.
        """
        changed: List[MetricSeries] = []
        for one in series:
            points: List[MetricPoint] = []
            for point in one.points:
                before = [
                    other
                    for other in one.points
                    if abs(other.x - (point.x - self.YOY_MONTHS)) <= self.TOLERANCE and other.y != 0
                ]
                if before:
                    points.append(point.model_copy(update={"y": (point.y / before[-1].y - 1) * 100}))
            changed.append(one.model_copy(update={"points": points}))
        return changed

    def _rank(self, series: List[MetricSeries]) -> List[MetricSeries]:
        """Turn each value into its rank among every series at the same x, 1 being the highest.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            List[MetricSeries]: The ranks (tied values share the best rank).
        """
        values: Dict[float, List[float]] = {}
        for one in series:
            for point in one.points:
                values.setdefault(self._x(point.x), []).append(point.y)
        return [
            one.model_copy(
                update={
                    "points": [
                        point.model_copy(
                            update={"y": 1.0 + sum(1 for other in values[self._x(point.x)] if other > point.y)}
                        )
                        for point in one.points
                    ]
                }
            )
            for one in series
        ]

    def _buckets(self, series: MetricSeries, grain: Optional[ChartMetric]) -> BucketValues:
        """Get the last value (and point label) of a series in each bucket.

        Args:
            series (MetricSeries): The series, its points in increasing x order.
            grain (Optional[ChartMetric]): The calendar bucket, `None` to pair the exact x values.

        Returns:
            BucketValues: The value and label of each bucket ordinal.
        """
        buckets: BucketValues = {}
        for point in series.points:
            if point.projected:
                continue
            at = self.time.bucket(point.x, grain) if grain is not None else self._x(point.x)
            buckets[at] = (point.y, point.label)
        return buckets

    def _indexes(
        self, series: List[MetricSeries], grain: Optional[ChartMetric]
    ) -> Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]]:
        """Index series by identity, with their bucket values.

        Args:
            series (List[MetricSeries]): The series.
            grain (Optional[ChartMetric]): The calendar bucket, `None` to pair the exact x values.

        Returns:
            Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]]: Each series and its bucket values.
        """
        return {self._identity(one): (one, self._buckets(one, grain)) for one in series}

    def _identities(self, *indexes: Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]]) -> List[SeriesIdentity]:
        """Get the identities of the paired series: every keyed series, the market-wide ones applying to every key.

        Args:
            *indexes (Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]]): The indexed series of each metric.

        Returns:
            List[SeriesIdentity]: The identities, in order of appearance, the market-wide ones only when no metric is
                keyed.
        """
        identities = list(dict.fromkeys(identity for index in indexes for identity in index))
        keyed = [identity for identity in identities if identity[0]]
        return keyed if keyed else identities

    def _lookup(
        self, index: Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]], identity: SeriesIdentity
    ) -> Optional[Tuple[MetricSeries, BucketValues]]:
        """Find the series of an identity, or the market-wide series of its region and segment.

        Args:
            index (Dict[SeriesIdentity, Tuple[MetricSeries, BucketValues]]): The indexed series of a metric.
            identity (SeriesIdentity): The identity.

        Returns:
            Optional[Tuple[MetricSeries, BucketValues]]: The series and its bucket values, `None` when unknown.
        """
        return index.get(identity) or index.get(("", identity[1], identity[2]))

    ############################
    # Publicly Exposed Methods #
    ############################

    def align(self, series: List[MetricSeries], metric: ChartMetric) -> List[MetricSeries]:
        """Give every series a point at every x value of any series.

        Args:
            series (List[MetricSeries]): The series, their points in increasing x order.
            metric (ChartMetric): The metric of their values.

        Returns:
            List[MetricSeries]: The aligned series.

        Notes:
            A level (e.g. the listed items) is carried forward from its last value, and is 0 before its first value
            when it counts items. A flow (e.g. the added items) is 0 where the series has no point.
        """
        xs = sorted({self._x(point.x) for one in series for point in one.points})
        counts = metric.unit is MetricUnit.COUNT
        aligned: List[MetricSeries] = []
        for one in series:
            by_x = {self._x(point.x): point for point in one.points}
            points: List[MetricPoint] = []
            previous: Optional[MetricPoint] = None
            for x in xs:
                point = by_x.get(x)
                if point is not None:
                    previous = point
                    points.append(point)
                elif not metric.stock:
                    points.append(MetricPoint(x=x, y=0.0))
                elif previous is not None:
                    points.append(previous.model_copy(update={"x": x, "label": None}))
                elif counts:
                    points.append(MetricPoint(x=x, y=0.0))
            aligned.append(one.model_copy(update={"points": points}))
        self.logger.debug("%d series aligned on %d x values.", len(series), len(xs))
        return aligned

    def extend(self, series: List[MetricSeries], until: float) -> List[MetricSeries]:
        """Carry the last value of level series forward to a later x value (e.g. the current bucket).

        Args:
            series (List[MetricSeries]): The series of a level metric.
            until (float): The x value the series must reach.

        Returns:
            List[MetricSeries]: The series, ending at `until` at least.
        """
        extended: List[MetricSeries] = []
        for one in series:
            if one.points and one.points[-1].x < until:
                last = one.points[-1].model_copy(update={"x": until, "label": None})
                one = one.model_copy(update={"points": [*one.points, last]})
            extended.append(one)
        return extended

    def combine(self, series: List[MetricSeries], keys: Dict[str, str], metric: ChartMetric) -> List[MetricSeries]:
        """Sum series into groups (e.g. the providers into their bloc), once aligned.

        Args:
            series (List[MetricSeries]): The series to sum.
            keys (Dict[str, str]): The group key of each series key.
            metric (ChartMetric): The metric of their values.

        Returns:
            List[MetricSeries]: One series per group, its value the sum of its series at each x.
        """
        totals: Dict[str, Dict[float, float]] = {}
        for one in self.align(series, metric):
            group = keys.get(one.key, one.key)
            for point in one.points:
                sums = totals.setdefault(group, {})
                sums[self._x(point.x)] = sums.get(self._x(point.x), 0.0) + point.y
        return [
            MetricSeries(key=group, points=[MetricPoint(x=x, y=value) for x, value in sorted(sums.items())])
            for group, sums in totals.items()
        ]

    def transform(self, series: List[MetricSeries], transform: ValueTransform) -> List[MetricSeries]:
        """Transform the values of the series.

        Args:
            series (List[MetricSeries]): The series, their points in increasing x order.
            transform (ValueTransform): The transform.

        Returns:
            List[MetricSeries]: The transformed series.
        """
        self.logger.debug("Transforming %d series: %s.", len(series), transform.value)
        match transform:
            case ValueTransform.SHARE_OF_TOTAL:
                return self._share_of_total(series)
            case ValueTransform.INDEXED:
                return self._indexed(series)
            case ValueTransform.YOY:
                return self._year_on_year(series)
            case ValueTransform.RANK:
                return self._rank(series)
            case _:
                return series

    def pair(
        self,
        xs: List[MetricSeries],
        ys: List[MetricSeries],
        grain: Optional[ChartMetric] = None,
    ) -> List[MetricSeries]:
        """Pair the values of two metrics: a point per bucket where both are known, x from one, y from the other.

        Args:
            xs (List[MetricSeries]): The series of the x metric.
            ys (List[MetricSeries]): The series of the y metric.
            grain (Optional[ChartMetric]): The calendar bucket both are compared in, `None` for the exact x values.

        Returns:
            List[MetricSeries]: The paired series, their points in increasing x order, named after their bucket.

        Notes:
            A market-wide series (empty key) pairs with every keyed series of the same region and segment.
        """
        x_index, y_index = self._indexes(xs, grain), self._indexes(ys, grain)
        paired: List[MetricSeries] = []
        for identity in self._identities(y_index, x_index):
            x_found, y_found = self._lookup(x_index, identity), self._lookup(y_index, identity)
            if x_found is None or y_found is None:
                continue
            (template, y_buckets), x_buckets = y_found, x_found[1]
            points = [
                MetricPoint(
                    x=x_buckets[at][0],
                    y=value,
                    label=label or x_buckets[at][1] or (self.time.label(grain, at) if grain else None),
                )
                for at, (value, label) in sorted(y_buckets.items())
                if at in x_buckets
            ]
            if points:
                currency = template.currency or x_found[0].currency
                points.sort(key=lambda point: point.x)
                paired.append(
                    MetricSeries(
                        key=identity[0], region=identity[1], segment=identity[2], currency=currency, points=points
                    )
                )
        self.logger.debug("%d paired series from %d x and %d y series.", len(paired), len(xs), len(ys))
        return paired

    def snapshot(
        self,
        xs: List[MetricSeries],
        ys: List[MetricSeries],
        sizes: List[MetricSeries],
        grain: ChartMetric,
    ) -> Tuple[List[MetricSeries], Optional[float]]:
        """Position one bubble per series: its x, y and size values in the latest bucket where they are all known.

        Args:
            xs (List[MetricSeries]): The series of the x metric.
            ys (List[MetricSeries]): The series of the y metric.
            sizes (List[MetricSeries]): The series of the size metric, empty for bubbles of the same size.
            grain (ChartMetric): The calendar bucket the metrics are compared in.

        Returns:
            Tuple[List[MetricSeries], Optional[float]]: A one-point series per bubble, and the latest bucket used.
        """
        x_index, y_index, size_index = self._indexes(xs, grain), self._indexes(ys, grain), self._indexes(sizes, grain)
        bubbles: List[MetricSeries] = []
        latest: Optional[float] = None
        for identity in self._identities(y_index, x_index, size_index):
            x_found, y_found = self._lookup(x_index, identity), self._lookup(y_index, identity)
            size_found = self._lookup(size_index, identity) if sizes else None
            if x_found is None or y_found is None or (sizes and size_found is None):
                continue
            common: Set[float] = set(x_found[1]) & set(y_found[1])
            if size_found is not None:
                common &= set(size_found[1])
            if not common:
                continue
            at = max(common)
            size = size_found[1][at][0] if size_found is not None else None
            point = MetricPoint(x=x_found[1][at][0], y=y_found[1][at][0], size=size, label=self.time.label(grain, at))
            currency = y_found[0].currency or x_found[0].currency
            bubbles.append(
                MetricSeries(
                    key=identity[0], region=identity[1], segment=identity[2], currency=currency, points=[point]
                )
            )
            latest = at if latest is None else max(latest, at)
        self.logger.debug("%d bubbles positioned, latest bucket %s.", len(bubbles), latest)
        return bubbles, latest

    def weights(self, series: List[MetricSeries]) -> Dict[SeriesIdentity, float]:
        """Weigh the series by their latest observed value, to keep the largest ones.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            Dict[SeriesIdentity, float]: The weight of each series (its size for a bubble).
        """
        weights: Dict[SeriesIdentity, float] = {}
        for one in series:
            observed = [point for point in one.points if not point.projected]
            last = observed[-1] if observed else None
            weight = 0.0 if last is None else (last.size if last.size is not None else last.y)
            weights[self._identity(one)] = weight
        return weights

    def top(
        self,
        series: List[MetricSeries],
        count: Optional[int],
        weights: Dict[SeriesIdentity, float],
        merge: bool = False,
    ) -> List[MetricSeries]:
        """Keep the largest series, the others dropped or merged into one series.

        Args:
            series (List[MetricSeries]): The series.
            count (Optional[int]): The largest number of keyed series kept, `None` to keep every series.
            weights (Dict[SeriesIdentity, float]): The weight of each series, the heaviest kept first.
            merge (bool): Whether the series not kept are summed into an `OTHERS_KEY` series (stacked charts).

        Returns:
            List[MetricSeries]: The kept series, the heaviest first, then the merged one.

        Notes:
            The market-wide series (empty key) are always kept.
        """
        keyed = sorted(
            (one for one in series if one.key),
            key=lambda one: weights.get(self._identity(one), 0.0),
            reverse=True,
        )
        kept, rest = (keyed, []) if count is None else (keyed[:count], keyed[count:])
        result = [one for one in series if not one.key] + kept
        if merge and rest:
            sums: Dict[float, float] = {}
            projected: Set[float] = set()
            for one in rest:
                for point in one.points:
                    sums[self._x(point.x)] = sums.get(self._x(point.x), 0.0) + point.y
                    if point.projected:
                        projected.add(self._x(point.x))
            points = [MetricPoint(x=x, y=value, projected=x in projected) for x, value in sorted(sums.items())]
            result.append(MetricSeries(key=self.OTHERS_KEY, points=points))
        return result
