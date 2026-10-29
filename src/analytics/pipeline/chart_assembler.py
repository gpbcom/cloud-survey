from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# First Party Imports.
from analytics.series.axis_rules import AxisRules
from analytics.series.series_transformer import SeriesTransformer
from analytics.series.trend_forecaster import TrendForecaster
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartNote, MetricKind, ValueTransform
from models.trends.metric_series import MetricSeries
from models.trends.trend_result import TrendResult


class ChartAssembler:
    """Turn raw chart series into the drawn ones: aligned, extrapolated, transformed, the largest kept.

    Attributes:
        rules (AxisRules): The chart rules, telling whether the series can be extrapolated.
        forecaster (TrendForecaster): The trend forecaster.
        transformer (SeriesTransformer): The series transformer.
        logger (Logger): The assembler logger.

    Notes:
        - The forecast extrapolates the raw values: a share of total or a rank of the projected values is then
          computed like any other.
        - The largest series are chosen by their latest raw value, before any transform.
        - The derivative (rate of change) is taken last, from the transformed values: the rate of change of a share
          of total, of an index or of the raw values.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the assembler.

        Args:
            logger (Optional[Logger]): The assembler logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rules = AxisRules(self.logger)
        self.forecaster = TrendForecaster(self.logger)
        self.transformer = SeriesTransformer(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _notes(self, raw: TrendResult, added: List[ChartNote]) -> List[ChartNote]:
        """Merge the caveats of the raw series with those of the assembly, once each.

        Args:
            raw (TrendResult): The raw series and their caveats.
            added (List[ChartNote]): The caveats of the assembly.

        Returns:
            List[ChartNote]: The caveats, in order of appearance.
        """
        return list(dict.fromkeys([*raw.notes, *added]))

    def _assemble_series(
        self, axes: ChartAxes, raw: TrendResult, key_weights: Optional[Dict[str, float]] = None
    ) -> TrendResult:
        """Turn raw series into the series a chart (or a facet) draws.

        Args:
            axes (ChartAxes): The chart axes (valid).
            raw (TrendResult): The raw series, their methodology breaks and caveats.
            key_weights (Optional[Dict[str, float]]): The weight of each series key keeping the largest series, their
                own latest value when `None` (the facets weigh the keys over every facet, to keep the same ones).

        Returns:
            TrendResult: The drawn series, the largest first, with the number of series before the selection and the
                x value of the latest observation.
        """
        series: List[MetricSeries] = [
            one.model_copy(update={"points": sorted(one.points, key=lambda point: point.x)})
            for one in raw.series
            if one.points
        ]
        weights = self.transformer.weights(series)
        if key_weights is not None:
            weights = {identity: key_weights.get(identity[0], 0.0) for identity in weights}
        notes: List[ChartNote] = []
        timed = axes.x.kind is MetricKind.TIME and axes.chart is not ChartKind.BUBBLE
        observed = [point.x for one in series for point in one.points if not point.projected]
        last_actual = max(observed) if observed and timed else None
        if timed:
            if axes.chart is ChartKind.AREA or axes.transform in (ValueTransform.SHARE_OF_TOTAL, ValueTransform.RANK):
                series = self.transformer.align(series, axes.y)
            if axes.forecast and self.rules.forecastable(axes) is None and series:
                series = self.forecaster.project(series, axes.y)
                notes.append(ChartNote.FORECAST_METHOD)
            series = self.transformer.transform(series, axes.transform)
        if axes.derivative and self.rules.derivable(axes) is None:
            series = self.transformer.derivative(series, axes.x.kind is MetricKind.TIME)
            notes.append(ChartNote.DERIVATIVE)
        kept = self.transformer.top(series, axes.top, weights, merge=axes.chart is ChartKind.AREA)
        total = sum(1 for one in series if one.key)
        self.logger.debug("Chart assembled: %d of %d series kept.", sum(1 for one in kept if one.key), total)
        return TrendResult(
            series=kept,
            breaks=raw.breaks if timed else [],
            notes=self._notes(raw, notes),
            total_count=total,
            last_actual=last_actual,
            as_of=raw.as_of,
        )

    def _assemble_facets(self, axes: ChartAxes, raw: TrendResult) -> TrendResult:
        """Turn raw series into the series of a faceted chart: each facet assembled on its own.

        Args:
            axes (ChartAxes): The chart axes (valid), with a facet grouping.
            raw (TrendResult): The raw series of every facet, tagged with their facet.

        Returns:
            TrendResult: The drawn series of every facet, tagged with their facet, the largest facet first.

        Notes:
            Each facet is transformed on its own (e.g. its shares add up to 100), and keeps the same series: the keys
            heaviest over every facet, so that the small charts can be compared.
        """
        groups: Dict[str, List[MetricSeries]] = {}
        for one in raw.series:
            if one.facet is not None and one.points:
                groups.setdefault(one.facet, []).append(one)
        key_weights: Dict[str, float] = {}
        facet_weights: Dict[str, float] = {}
        for facet, group in groups.items():
            for identity, weight in self.transformer.weights(group).items():
                key_weights[identity[0]] = key_weights.get(identity[0], 0.0) + weight
                facet_weights[facet] = facet_weights.get(facet, 0.0) + weight
        series: List[MetricSeries] = []
        notes: List[ChartNote] = []
        totals: List[int] = []
        lasts: List[float] = []
        for facet in sorted(groups, key=lambda name: facet_weights[name], reverse=True):
            facet_raw = raw.model_copy(update={"series": groups[facet]})
            assembled = self._assemble_series(axes, facet_raw, key_weights)
            series += [one.model_copy(update={"facet": facet}) for one in assembled.series]
            notes += [note for note in assembled.notes if note not in notes]
            totals.append(assembled.total_count)
            if assembled.last_actual is not None:
                lasts.append(assembled.last_actual)
        self.logger.debug("Faceted chart assembled: %d facets, %d series.", len(groups), len(series))
        return TrendResult(
            series=series,
            breaks=raw.breaks,
            notes=notes or list(raw.notes),
            total_count=max(totals, default=0),
            last_actual=max(lasts, default=None),
            as_of=raw.as_of,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def assemble(self, axes: ChartAxes, raw: TrendResult) -> TrendResult:
        """Turn raw series into the series a chart draws.

        Args:
            axes (ChartAxes): The chart axes (valid).
            raw (TrendResult): The raw series, their methodology breaks and caveats.

        Returns:
            TrendResult: The drawn series, the largest first, with the number of series before the selection and the
                x value of the latest observation, tagged with their facet and the largest facet first for a faceted
                chart.
        """
        if axes.facet_by is not None:
            return self._assemble_facets(axes, raw)
        return self._assemble_series(axes, raw)
