from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence

# First Party Imports.
from gui.theme import Theme
from models.drivers.enums import DriverRole, DriverScope, DriverWarningKind, MetricFamily, ProviderMetric
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.metric_coverage import MetricCoverage


class CriterionTooltip:
    """Write the tooltips of the Rise drivers card: each criterion, choice and button.

    Attributes:
        theme (Theme): The application theme.
        catalog (MetricCatalog): The definitions of the criteria and the targets.
        help (DriverHelp): The explanations of the roles, the scales, the scopes and the warnings.
        coverage (Dict[ProviderMetric, MetricCoverage]): What the stored measures of each criterion cover, empty
            until read.
        logger (Logger): The writer logger.

    Notes:
        A criterion says what it measures, from where, transformed
        how and what is stored of it, the Run button
        what a run will compute with the parameters picked.
        Every text comes from `conf/metrics/metrics.yaml`
        (the definitions) and the `drivers` block of
        `conf/help.yaml` (the roles, the scales, the scopes, the warnings),
        the coverage from the stored `provider_metrics`.
    """

    def __init__(
        self, theme: Theme, catalog: MetricCatalog, help_: DriverHelp, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the writer.

        Args:
            theme (Theme): The application theme.
            catalog (MetricCatalog): The definitions of the criteria and the targets.
            help_ (DriverHelp): The explanations.
            logger (Optional[Logger]): The writer logger.
        """
        self.theme, self.catalog, self.help = theme, catalog, help_
        self.logger = logger if logger else getLogger(__name__)
        self.coverage: Dict[ProviderMetric, MetricCoverage] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _title(self, text: str) -> str:
        """Write the first line of a tooltip.

        Args:
            text (str): The title.

        Returns:
            str: The rich text line.
        """
        return f"<p style='margin:0'><b style='color:{self.theme.ACCENT}'>{html.escape(text)}</b></p>"

    def _stored(self, metric: ProviderMetric) -> str:
        """Say what is stored of a criterion.

        Args:
            metric (ProviderMetric): The criterion.

        Returns:
            str: The rich text paragraph.
        """
        stored = self.coverage.get(metric)
        if stored is None:
            return "<p><b>Stored:</b> nothing yet (crawl its source, or wait for the coverage to be read).</p>"
        sources = ", ".join(source.value for source in stored.sources)
        return (
            f"<p><b>Stored:</b> {stored.providers} providers, {stored.first} to {stored.last}, "
            f"{stored.observations} measures ({html.escape(sources)}).</p>"
        )

    def _transform(self, metric: ProviderMetric) -> str:
        """Say how a criterion is transformed before the statistics.

        Args:
            metric (ProviderMetric): The criterion.

        Returns:
            str: The explanation of its scale, empty without definition.
        """
        definition = self.catalog.get(metric)
        explained = self.help.choice(definition.scale.value) if definition is not None else None
        return explained.summary if explained is not None else ""

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_coverage(self, coverage: Sequence[MetricCoverage]) -> None:
        """Keep what the stored measures cover.

        Args:
            coverage (Sequence[MetricCoverage]): One entry per stored criterion.
        """
        self.coverage = {entry.metric: entry for entry in coverage}
        self.logger.debug("Coverage of %d criteria kept for the tooltips.", len(self.coverage))

    def metric(self, metric: ProviderMetric, role: DriverRole) -> str:
        """Explain a criterion in the role it would play.

        Args:
            metric (ProviderMetric): The criterion.
            role (DriverRole): Target, criterion or control.

        Returns:
            str: The rich text tooltip.
        """
        definition = self.catalog.get(metric)
        if definition is None:
            self.logger.warning("The metric %s has no definition: its tooltip is its key.", metric.value)
            return metric.value
        parts = [
            self._title(definition.label),
            f"<p>{html.escape(definition.description)}</p>",
            f"<p><b>Family:</b> {html.escape(definition.family.value)}. <b>Unit:</b> {html.escape(definition.unit)}. "
            f"<b>Source:</b> {html.escape(', '.join(definition.sources))}.</p>",
            f"<p><b>Transformed:</b> {html.escape(self._transform(metric))}</p>",
            self._stored(metric),
        ]
        explained = self.help.role(role)
        if explained is not None:
            parts.append(f"<p><b>Role ({html.escape(explained.title)}):</b> {html.escape(explained.summary)}</p>")
        common = self.help.warning(DriverWarningKind.COMMON_CRITERION)
        if definition.family is MetricFamily.SUPPLY_CONTEXT and common is not None:
            parts.append(f"<p><b>{html.escape(common.title)}:</b> {html.escape(common.meaning)}</p>")
        return "<qt>" + "".join(parts) + "</qt>"

    def scope(self, scope: DriverScope) -> str:
        """Explain a scope.

        Args:
            scope (DriverScope): The scope.

        Returns:
            str: The rich text tooltip.
        """
        explained = self.help.choice(scope.value)
        if explained is None:
            self.logger.warning("The scope %s is not explained in the drivers help.", scope.value)
        return "<qt>" + self._title(scope.value) + f"<p>{html.escape(explained.summary if explained else '')}</p></qt>"

    def role(self, role: DriverRole) -> str:
        """Explain a parameter by its role (the lag, the scope list).

        Args:
            role (DriverRole): The role.

        Returns:
            str: The rich text tooltip.
        """
        explained = self.help.role(role)
        if explained is None:
            self.logger.warning("The role %s is not explained in the drivers help: its tooltip is its key.", role.value)
            return role.value
        return (
            "<qt>"
            + self._title(explained.title)
            + f"<p>{html.escape(explained.summary)}</p><p>{html.escape(explained.details)}</p></qt>"
        )

    def picked(self, role: DriverRole, metrics: List[ProviderMetric]) -> str:
        """Explain a criteria or controls button: its role and what is checked.

        Args:
            role (DriverRole): Criterion or control.
            metrics (List[ProviderMetric]): The checked criteria.

        Returns:
            str: The rich text tooltip.
        """
        explained = self.help.role(role)
        names = ", ".join(html.escape(self.catalog.label(metric)) for metric in metrics) or "none"
        head = self._title(explained.title if explained else role.value)
        body = f"<p>{html.escape(explained.details)}</p>" if explained else ""
        return f"<qt>{head}{body}<p><b>Checked ({len(metrics)}):</b> {names}.</p></qt>"

    def run(
        self,
        target: Optional[ProviderMetric],
        criteria: List[ProviderMetric],
        controls: List[ProviderMetric],
        scope: DriverScope,
        lag: int,
        resamples: int,
    ) -> str:
        """Say exactly what a run will compute with the parameters picked.

        Args:
            target (Optional[ProviderMetric]): The target, `None` without any.
            criteria (List[ProviderMetric]): The criteria.
            controls (List[ProviderMetric]): The controls.
            scope (DriverScope): The scope.
            lag (int): The lag, in quarters (panel only).
            resamples (int): The bootstrap resamples of the intervals.

        Returns:
            str: The rich text tooltip.
        """
        if target is None or not criteria:
            self.logger.debug("Run tooltip without a target or a criterion: it asks for them.")
            return "<qt>" + self._title("Run") + "<p>Pick a target and at least one criterion.</p></qt>"
        self.logger.debug(
            "Run tooltip of %s: %d criteria, %d controls, %s scope, %d resamples.",
            target.value,
            len(criteria),
            len(controls),
            scope.value,
            resamples,
        )
        names = ", ".join(html.escape(self.catalog.label(metric)) for metric in criteria)
        held = ", ".join(html.escape(self.catalog.label(metric)) for metric in controls) or "none"
        explained_scope = self.help.choice(scope.value)
        criterion_role = self.help.role(DriverRole.CRITERION)
        parts = [
            self._title("Run"),
            f"<p><b>Explain</b> {html.escape(self.catalog.label(target))} ({html.escape(self._transform(target))})</p>",
            f"<p><b>With {len(criteria)} criteria:</b> {names}.</p>",
            f"<p><b>Held constant:</b> {held}.</p>",
            f"<p><b>Observations:</b> {html.escape(explained_scope.summary if explained_scope else scope.value)}</p>",
        ]
        if scope is DriverScope.PANEL:
            quarters = "quarter" if lag == 1 else "quarters"
            parts.append(f"<p><b>Lag:</b> the criteria {lag} {quarters} before the target.</p>")
        if criterion_role is not None:
            parts.append(f"<p><b>Statistics:</b> {html.escape(criterion_role.details)}</p>")
        parts.append(f"<p><b>Intervals:</b> {resamples} bootstrap resamples, drawn by provider.</p>")
        return "<qt>" + "".join(parts) + "</qt>"
