from __future__ import annotations

# Standard Library Imports.
import math
from dataclasses import replace
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
import numpy

# First Party Imports.
from analytics.drivers.matrix.driver_matrix import DriverMatrix
from analytics.drivers.matrix.quarter_calendar import QuarterCalendar
from models.cloud.enums import CloudProvider
from models.drivers.enums import DriverScope, MetricScale, MetricSource, ProviderMetric
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.drivers.query.driver_query import DriverQuery


class DriverPanel:
    """Build the numeric observations of a driver analysis from the measures of the providers.

    Attributes:
        SOURCE_PREFERENCE (ClassVar[List[MetricSource]]): The sources, the most trusted first.
        CHANGE_SPAN (ClassVar[int]): The quarters a change is measured over in a panel (a year).
        catalog (MetricCatalog): The catalogue, which gives the scale of each metric.
        calendar (QuarterCalendar): The quarter arithmetic.
        logger (Logger): The panel logger.

    Notes:
        - When several sources measure the same provider, quarter and metric, the most trusted one is kept, in this
          order: typed in by hand (an annual report), SEC EDGAR, Synergy Research Group, Wikidata, PeeringDB, GitHub,
          and last the measures derived from the crawled data. Between two measures of the same source, the latest
          fetched wins.
        - Each value is transformed by the scale of its metric: `log(1 + x)` for a count (negative counts left out),
          `log(x)` for an amount (zero and negative amounts left out), a share as it is. A metric missing from the
          catalogue is used as it is.
        - A cross-section has one row per provider measuring the target: its latest quarter holding the target and
          every criterion (the controls at that quarter, or their latest value). A provider with no such quarter falls
          back to the latest value of each metric, the row being dated by its latest target.
        - A panel has one row per provider and quarter `t` holding the change of the target over a year
          (`value(t) - value(t - 4)` after the scale transform, so a change of logarithm for the counts and the amounts
          and a change of points for the shares). The criteria and the controls are the same changes taken `lag`
          quarters before the target. The rows missing a criterion are kept with `NaN` and counted, the regression
          leaving them out.
    """

    SOURCE_PREFERENCE: ClassVar[List[MetricSource]] = [
        MetricSource.MANUAL,
        MetricSource.EDGAR,
        MetricSource.SYNERGY,
        MetricSource.WIKIDATA,
        MetricSource.PEERINGDB,
        MetricSource.GITHUB,
        MetricSource.DERIVED,
    ]
    CHANGE_SPAN: ClassVar[int] = 4

    def __init__(
        self, catalog: MetricCatalog, calendar: Optional[QuarterCalendar] = None, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the panel.

        Args:
            catalog (MetricCatalog): The catalogue, which gives the scale of each metric.
            calendar (Optional[QuarterCalendar]): The quarter arithmetic.
            logger (Optional[Logger]): The panel logger.
        """
        self.catalog = catalog
        self.logger = logger if logger else getLogger(__name__)
        self.calendar = calendar if calendar else QuarterCalendar()

    ############################
    # Internal Helpers Methods #
    ############################

    def _rank(self, source: MetricSource) -> int:
        """Rank a source by trust.

        Args:
            source (MetricSource): The source.

        Returns:
            int: Its rank, 0 for the most trusted.
        """
        return self.SOURCE_PREFERENCE.index(source) if source in self.SOURCE_PREFERENCE else len(self.SOURCE_PREFERENCE)

    def _prefers(self, candidate: ProviderMetricValue, current: ProviderMetricValue) -> bool:
        """Tell whether a measure replaces another measure of the same provider, quarter and metric.

        Args:
            candidate (ProviderMetricValue): The new measure.
            current (ProviderMetricValue): The measure kept so far.

        Returns:
            bool: Whether its source is more trusted, or the same and fetched later.
        """
        candidate_rank, current_rank = self._rank(candidate.source), self._rank(current.source)
        if candidate_rank != current_rank:
            return candidate_rank < current_rank
        if candidate.fetched_at is None or current.fetched_at is None:
            return False
        return candidate.fetched_at > current.fetched_at

    def _metrics(self, query: DriverQuery) -> List[ProviderMetric]:
        """List the metrics an analysis reads.

        Args:
            query (DriverQuery): The analysis.

        Returns:
            List[ProviderMetric]: The target, the criteria and the controls, each once.
        """
        return [*dict.fromkeys([query.target, *query.criteria, *query.controls])]

    def _latest(self, series: Dict[str, float]) -> Optional[str]:
        """Get the latest quarter of a series.

        Args:
            series (Dict[str, float]): The values by quarter.

        Returns:
            Optional[str]: Its latest quarter, `None` when it is empty.
        """
        return max(series, key=self.calendar.index) if series else None

    def _cross_row(
        self, provider: CloudProvider, by_metric: Dict[ProviderMetric, Dict[str, float]], query: DriverQuery
    ) -> Tuple[CloudProvider, str, Dict[ProviderMetric, float]]:
        """Build the cross-section row of a provider measuring the target.

        Args:
            provider (CloudProvider): The provider.
            by_metric (Dict[ProviderMetric, Dict[str, float]]): Its transformed values by metric and quarter.
            query (DriverQuery): The analysis.

        Returns:
            Tuple[CloudProvider, str, Dict[ProviderMetric, float]]: The provider, the quarter of the row, and its values
                by metric.
        """
        target_series = by_metric.get(query.target, {})
        common = set(target_series)
        for criterion in query.criteria:
            common &= set(by_metric.get(criterion, {}))
        row: Dict[ProviderMetric, float] = {}
        if common:
            period = max(common, key=self.calendar.index)
            for metric in self._metrics(query):
                series = by_metric.get(metric, {})
                at = period if period in series else self._latest(series)
                if at is not None:
                    row[metric] = series[at]
            return provider, period, row
        self.logger.debug("%s: no quarter holds the target and every criterion, the latest values are used.", provider)
        for metric in self._metrics(query):
            series = by_metric.get(metric, {})
            latest = self._latest(series)
            if latest is not None:
                row[metric] = series[latest]
        return provider, self._latest(target_series) or "", row

    def _matrix(
        self,
        query: DriverQuery,
        rows: List[Tuple[CloudProvider, str, Dict[ProviderMetric, float]]],
        series: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]],
        target_providers: int,
    ) -> DriverMatrix:
        """Assemble the rows into arrays.

        Args:
            query (DriverQuery): The analysis.
            rows (List[Tuple[CloudProvider, str, Dict[ProviderMetric, float]]]): The provider, the quarter and the
                values by metric of each row.
            series (Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]): The transformed values by provider,
                metric and quarter.
            target_providers (int): The distinct providers holding at least one value of the target.

        Returns:
            DriverMatrix: The observations, `NaN` where a value is missing.
        """
        nan = math.nan
        y = numpy.array([row.get(query.target, nan) for _, _, row in rows], dtype=numpy.float64)
        x = numpy.array(
            [[row.get(criterion, nan) for criterion in query.criteria] for _, _, row in rows], dtype=numpy.float64
        ).reshape(len(rows), len(query.criteria))
        z = numpy.array(
            [[row.get(control, nan) for control in query.controls] for _, _, row in rows], dtype=numpy.float64
        ).reshape(len(rows), len(query.controls))
        matrix = DriverMatrix(
            target=query.target,
            criteria=list(query.criteria),
            controls=list(query.controls),
            y=y,
            x=x,
            z=z,
            providers=[provider for provider, _, _ in rows],
            periods=[period for _, period, _ in rows],
            dropped=0,
            target_providers=target_providers,
            series=series,
        )
        complete = int(matrix.complete_rows().sum())
        dropped = len(rows) - complete
        if dropped:
            self.logger.warning("%d of the %d observations miss a criterion and are left out.", dropped, len(rows))
        return replace(matrix, dropped=dropped)

    ############################
    # Publicly Exposed Methods #
    ############################

    def transform(self, metric: ProviderMetric, value: float) -> Optional[float]:
        """Transform a value by the scale of its metric.

        Args:
            metric (ProviderMetric): The metric.
            value (float): The raw value.

        Returns:
            Optional[float]: `log(1 + x)` for a count, `log(x)` for an amount, a share as it is, `None` when the
                value cannot be transformed (a negative count, an amount not above zero, an infinite value).
        """
        if not math.isfinite(value):
            return None
        definition = self.catalog.get(metric)
        scale = definition.scale if definition is not None else MetricScale.SHARE
        match scale:
            case MetricScale.COUNT:
                return math.log1p(value) if value >= 0 else None
            case MetricScale.AMOUNT:
                return math.log(value) if value > 0 else None
            case _:
                return value

    def natural(self, metric: ProviderMetric, value: float, scope: DriverScope) -> Optional[float]:
        """Turn a value of the analysis back into its natural unit (the inverse of `transform`).

        Args:
            metric (ProviderMetric): The metric.
            value (float): The transformed value (a level), or its change over a year in a panel.
            scope (DriverScope): The scope of the analysis.

        Returns:
            Optional[float]: The raw count or amount, a share as it is, or in a panel the yearly change in percent
                of a count or an amount (in points of a share). `None` when it overflows.
        """
        definition = self.catalog.get(metric)
        scale = definition.scale if definition is not None else MetricScale.SHARE
        if scale is MetricScale.SHARE:
            return value
        try:
            match scope:
                case DriverScope.PANEL:
                    return math.expm1(value) * 100.0
                case _:
                    return math.expm1(value) if scale is MetricScale.COUNT else math.exp(value)
        except OverflowError:
            self.logger.warning("The %s value %g overflows its natural unit.", metric, value)
            return None

    def levels(
        self, values: List[ProviderMetricValue], metrics: List[ProviderMetric], providers: List[CloudProvider]
    ) -> Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]:
        """Keep the most trusted measure of each provider, quarter and metric, transformed by its scale.

        Args:
            values (List[ProviderMetricValue]): The measures.
            metrics (List[ProviderMetric]): Only these metrics.
            providers (List[CloudProvider]): Only these providers, every provider when empty.

        Returns:
            Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]: The transformed values by provider, metric and
                quarter, the providers in alphabetical order.
        """
        wanted, allowed = set(metrics), set(providers)
        best: Dict[Tuple[CloudProvider, ProviderMetric, str], ProviderMetricValue] = {}
        for value in values:
            if value.metric not in wanted or (allowed and value.provider not in allowed):
                continue
            key = (value.provider, value.metric, value.period)
            current = best.get(key)
            if current is None or self._prefers(value, current):
                best[key] = value
        series: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]] = {}
        left_out = 0
        for (provider, metric, period), value in sorted(best.items(), key=lambda item: str(item[0][0])):
            transformed = self.transform(metric, value.value)
            if transformed is None:
                left_out += 1
                continue
            series.setdefault(provider, {}).setdefault(metric, {})[period] = transformed
        if left_out:
            self.logger.warning("%d values cannot be transformed by their scale and are left out.", left_out)
        self.logger.debug("Kept %d measures of %d providers.", len(best), len(series))
        return series

    def changes(
        self, levels: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]
    ) -> Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]:
        """Compute the changes over a year of transformed values.

        Args:
            levels (Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]): The transformed values by provider,
                metric and quarter.

        Returns:
            Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]]: The change `value(t) - value(t - 4)` by
                provider, metric and quarter `t`, for the quarters `t`
                whose year-earlier quarter is measured.
        """
        changes: Dict[CloudProvider, Dict[ProviderMetric, Dict[str, float]]] = {}
        for provider, by_metric in levels.items():
            for metric, series in by_metric.items():
                for period, value in series.items():
                    prior = self.calendar.shift(period, -self.CHANGE_SPAN)
                    if prior in series:
                        changes.setdefault(provider, {}).setdefault(metric, {})[period] = value - series[prior]
        if not changes:
            self.logger.warning("No yearly change: no series spans %d quarters.", self.CHANGE_SPAN)
        else:
            self.logger.debug("Yearly changes of %d of %d providers.", len(changes), len(levels))
        return changes

    def cross_section(self, query: DriverQuery, values: List[ProviderMetricValue]) -> DriverMatrix:
        """Build one observation per provider measuring the target.

        Args:
            query (DriverQuery): The analysis.
            values (List[ProviderMetricValue]): The measures.

        Returns:
            DriverMatrix: The observations, the latest quarter of each provider.
        """
        levels = self.levels(values, self._metrics(query), query.providers)
        rows = [
            self._cross_row(provider, by_metric, query)
            for provider, by_metric in levels.items()
            if by_metric.get(query.target)
        ]
        self.logger.info("Cross-section of %s: %d providers.", query.target, len(rows))
        return self._matrix(query, rows, levels, len(rows))

    def panel(self, query: DriverQuery, values: List[ProviderMetricValue]) -> DriverMatrix:
        """Build one observation per provider and quarter: the changes over a year, the criteria lagged.

        Args:
            query (DriverQuery): The analysis.
            values (List[ProviderMetricValue]): The measures.

        Returns:
            DriverMatrix: The observations, by provider then quarter.
        """
        levels = self.levels(values, self._metrics(query), query.providers)
        changes = self.changes(levels)
        rows: List[Tuple[CloudProvider, str, Dict[ProviderMetric, float]]] = []
        for provider, by_metric in changes.items():
            for period in sorted(by_metric.get(query.target, {}), key=self.calendar.index):
                row = {query.target: by_metric[query.target][period]}
                source = self.calendar.shift(period, -query.lag)
                for metric in self._metrics(query)[1:]:
                    change = by_metric.get(metric, {}).get(source)
                    if change is not None:
                        row[metric] = change
                rows.append((provider, period, row))
        target_providers = sum(1 for by_metric in levels.values() if by_metric.get(query.target))
        self.logger.info("Panel of %s: %d observations, lag %d.", query.target, len(rows), query.lag)
        return self._matrix(query, rows, changes, target_providers)

    def build(self, query: DriverQuery, values: List[ProviderMetricValue]) -> DriverMatrix:
        """Build the observations of an analysis, by its scope.

        Args:
            query (DriverQuery): The analysis.
            values (List[ProviderMetricValue]): The measures.

        Returns:
            DriverMatrix: The observations.
        """
        match query.scope:
            case DriverScope.PANEL:
                return self.panel(query, values)
            case _:
                return self.cross_section(query, values)
