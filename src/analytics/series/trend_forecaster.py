from __future__ import annotations

# Standard Library Imports.
import itertools
import math
import statistics
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# First Party Imports.
from models.trends.enums import ChartMetric, ForecastMethod
from models.trends.metric_point import MetricPoint
from models.trends.metric_series import MetricSeries


class TrendForecaster:
    """Extrapolate the trend of time series: a least-squares fit of their latest observations.

    Attributes:
        WINDOW (ClassVar[int]): The number of latest observations fitted.
        HORIZON (ClassVar[int]): The number of projected steps.
        MINIMUM (ClassVar[int]): The smallest number of observations a series needs to be projected.
        DEFAULT_STEP (ClassVar[float]): The step between two projected points when the series give none, in months.
        logger (Logger): The forecaster logger.

    Notes:
        The forecast is a trend, not a prediction: a straight line (or a constant growth rate for the sizes, which
        compound) fitted on the latest points of each series, projected a few steps ahead. Every series is projected on
        the same future x values, so that stacked or compared series stay aligned.
    """

    WINDOW: ClassVar[int] = 8
    HORIZON: ClassVar[int] = 4
    MINIMUM: ClassVar[int] = 3
    DEFAULT_STEP: ClassVar[float] = 3.0

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the forecaster.

        Args:
            logger (Optional[Logger]): The forecaster logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _fit(self, xs: List[float], ys: List[float]) -> Tuple[float, float]:
        """Fit a straight line by ordinary least squares.

        Args:
            xs (List[float]): The x values.
            ys (List[float]): The y values.

        Returns:
            Tuple[float, float]: The slope and the intercept (a flat line through the mean when x does not vary).
        """
        mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
        spread = sum((x - mean_x) ** 2 for x in xs)
        if spread == 0:
            return 0.0, mean_y
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / spread
        return slope, mean_y - slope * mean_x

    def _observed(self, series: MetricSeries) -> List[MetricPoint]:
        """Get the latest observations of a series, without its projected points.

        Args:
            series (MetricSeries): The series.

        Returns:
            List[MetricPoint]: The latest `WINDOW` observations, in increasing x order.
        """
        return [point for point in series.points if not point.projected][-self.WINDOW :]

    def _step(self, series: List[MetricSeries]) -> float:
        """Get the step between two projected points: the median gap between the latest observations.

        Args:
            series (List[MetricSeries]): The series.

        Returns:
            float: The step, in x units (months on a time axis).
        """
        gaps: List[float] = []
        for one in series:
            observed = self._observed(one)
            gaps += [second.x - first.x for first, second in itertools.pairwise(observed)]
        positive = [gap for gap in gaps if gap > 0]
        return statistics.median(positive) if positive else self.DEFAULT_STEP

    def _clamp(self, value: float, metric: ChartMetric) -> float:
        """Keep a projected value within the bounds of its metric (e.g. a share between 0% and 100%).

        Args:
            value (float): The projected value.
            metric (ChartMetric): The metric.

        Returns:
            float: The value within the bounds.
        """
        low, high = metric.bounds
        if low is not None:
            value = max(value, low)
        if high is not None:
            value = min(value, high)
        return value

    def _project(self, series: MetricSeries, metric: ChartMetric, grid: List[float]) -> MetricSeries:
        """Extrapolate a series on the future x values.

        Args:
            series (MetricSeries): The series.
            metric (ChartMetric): The metric of its values.
            grid (List[float]): The future x values.

        Returns:
            MetricSeries: The series with its projected points and annual trend, unchanged when it has too few
                observations.
        """
        observed = self._observed(series)
        if len(observed) < self.MINIMUM:
            return series
        xs, ys = [point.x for point in observed], [point.y for point in observed]
        compounding = metric.forecast_method is ForecastMethod.LOG_LINEAR and all(y > 0 for y in ys)
        if compounding:
            slope, intercept = self._fit(xs, [math.log(y) for y in ys])
            values = [math.exp(min(intercept + slope * x, 700.0)) for x in grid]
            trend: Optional[float] = (math.exp(12 * slope) - 1) * 100
        else:
            slope, intercept = self._fit(xs, ys)
            values = [intercept + slope * x for x in grid]
            trend = 12 * slope / abs(ys[-1]) * 100 if ys[-1] else None
        last = observed[-1].x
        projected = [
            MetricPoint(x=x, y=self._clamp(value, metric), projected=True)
            for x, value in zip(grid, values, strict=True)
            if x > last
        ]
        kept = [point for point in series.points if not point.projected]
        return series.model_copy(update={"points": kept + projected, "trend_pct": trend})

    ############################
    # Publicly Exposed Methods #
    ############################

    def project(self, series: List[MetricSeries], metric: ChartMetric) -> List[MetricSeries]:
        """Extrapolate the trend of every series, on the same future x values.

        Args:
            series (List[MetricSeries]): The time series, their points in increasing x order.
            metric (ChartMetric): The metric of their values, which sets the forecast method and bounds.

        Returns:
            List[MetricSeries]: The series with their projected points (`projected=True`) and annual trend.
        """
        observed = [points[-1].x for one in series if (points := self._observed(one))]
        if not observed:
            return series
        step = self._step(series)
        start = max(observed)
        grid = [start + step * index for index in range(1, self.HORIZON + 1)]
        projected = [self._project(one, metric, grid) for one in series]
        self.logger.debug(
            "%d series projected %d steps of %.1f after %.1f (%s).",
            len(series),
            self.HORIZON,
            step,
            start,
            metric.forecast_method.value,
        )
        return projected
