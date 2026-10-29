from __future__ import annotations

# Standard Library Imports.
from dataclasses import replace
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
import numpy

# First Party Imports.
from analytics.drivers.catalog.metric_catalog_loader import MetricCatalogLoader
from analytics.drivers.correlation.correlation_analysis import CorrelationAnalysis
from analytics.drivers.matrix.driver_matrix import DriverMatrix
from analytics.drivers.matrix.driver_panel import DriverPanel
from analytics.drivers.panel.granger_test import GrangerTest
from analytics.drivers.panel.panel_regression import PanelRegression
from analytics.drivers.regression.driver_regression import DriverRegression, RegressionOutcome
from models.drivers.enums import DriverScope, DriverWarningKind, MetricFamily, ProviderMetric
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.drivers.query.driver_query import DriverQuery
from models.drivers.results.correlation_cell import CorrelationCell
from models.drivers.results.driver_result import DriverResult
from models.drivers.results.driver_warning import DriverWarning


class DriverAnalysis:
    """Find which criteria are predominant in the rise of the cloud providers (the "Rise drivers" analysis).

    Attributes:
        FEW_PROVIDERS (ClassVar[int]): The providers measuring the target below which a criterion cannot be told
            apart from the identity of a provider.
        FEW_OBSERVATIONS (ClassVar[int]): The observations below which the results are fragile.
        COMMON_FAMILIES (ClassVar[Tuple[MetricFamily, ...]]): The families whose criteria take the same value for
            every provider in a quarter (a market context).
        catalog (MetricCatalog): The definitions of the criteria and the targets.
        panel (DriverPanel): The observations, from the stored measures.
        correlations (CorrelationAnalysis): The correlations of the criteria with the target.
        regression (DriverRegression): The cross-section regression and the split of its R².
        panel_regression (PanelRegression): The fixed effects regression.
        granger (GrangerTest): The lead test of each criterion (panel only).
        logger (Logger): The analysis logger.

    Notes:
        The method follows `docs/analysis/rise-drivers.md`: Spearman correlations with bootstrap intervals,
        q-values and partial correlations, then a standardized regression judged by its leave-one-out R², and the
        Shapley split of its R² ranking the criteria. A panel uses the yearly changes, the criteria lagged, with
        provider and quarter effects. In a panel each correlated criterion is also tested for leading the target
        (Granger), whether the regression runs or not: the test needs only the history of that criterion and of the
        target, not of every criterion.
    """

    FEW_PROVIDERS: ClassVar[int] = 3
    FEW_OBSERVATIONS: ClassVar[int] = 8
    COMMON_FAMILIES: ClassVar[Tuple[MetricFamily, ...]] = (MetricFamily.SUPPLY_CONTEXT,)

    def __init__(self, catalog: Optional[MetricCatalog] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the analysis.

        Args:
            catalog (Optional[MetricCatalog]): The definitions, read from `conf/metrics/metrics.yaml` by default.
            logger (Optional[Logger]): The analysis logger.

        Raises:
            MetricCatalogFileError: If the default catalogue cannot be loaded.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.catalog = catalog if catalog else MetricCatalogLoader(self.logger).load()
        self.panel = DriverPanel(self.catalog, logger=self.logger)
        self.correlations = CorrelationAnalysis(logger=self.logger)
        self.regression = DriverRegression(logger=self.logger)
        self.panel_regression = PanelRegression(self.regression, logger=self.logger)
        self.granger = GrangerTest(logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _caveats(self, query: DriverQuery, matrix: DriverMatrix) -> List[DriverWarning]:
        """Tell what limits the conclusions before any computation.

        Args:
            query (DriverQuery): The analysis.
            matrix (DriverMatrix): Its observations.

        Returns:
            List[DriverWarning]: The warnings.
        """
        warnings: List[DriverWarning] = []
        target = self.catalog.label(query.target)
        if matrix.target_providers <= self.FEW_PROVIDERS:
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.FEW_PROVIDERS,
                    message=f"Only {matrix.target_providers} providers measure {target}: a criterion cannot be told "
                    "apart from the identity of a provider.",
                )
            )
        complete = int(matrix.complete_rows().sum())
        if complete < self.FEW_OBSERVATIONS:
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.FEW_OBSERVATIONS,
                    message=f"{complete} complete observations: the results are fragile.",
                )
            )
        if matrix.dropped:
            holding = numpy.isfinite(matrix.y)
            coverage = sorted(
                (int((holding & numpy.isfinite(matrix.x[:, column])).sum()), criterion.value)
                for column, criterion in enumerate(matrix.criteria)
            )
            scarcest = ", ".join(f"{name} ({count})" for count, name in coverage[:3])
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.MISSING_VALUES,
                    message=f"{matrix.dropped} observations miss a criterion and are left out of the regression. "
                    f"The criteria measured least with the target: {scarcest}.",
                    subjects=[ProviderMetric(name) for _, name in coverage[:3]],
                )
            )
        common = [
            metric
            for metric in [*query.criteria, *query.controls]
            if (definition := self.catalog.get(metric)) is not None and definition.family in self.COMMON_FAMILIES
        ]
        if common:
            names = ", ".join(self.catalog.label(metric) for metric in common)
            reach = (
                "on the latest quarter they differ between providers only when their latest quarters differ: "
                "their correlation there says nothing about the providers"
                if query.scope is DriverScope.CROSS_SECTION
                else "the panel correlations and Granger tests use their changes over time, the regression's quarter "
                "effects absorb them"
            )
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.COMMON_CRITERION,
                    message=f"{names}: the same value for every provider in a quarter; {reach}.",
                    subjects=common,
                )
            )
        if warnings:
            self.logger.warning(
                "%d caveats on the analysis of %s: %s.",
                len(warnings),
                query.target,
                ", ".join(warning.kind for warning in warnings),
            )
        else:
            self.logger.debug("No caveat on the analysis of %s.", query.target)
        return warnings

    def _usable(self, matrix: DriverMatrix, usable: List[ProviderMetric]) -> DriverMatrix:
        """Keep the criteria the correlations could use (a criterion missing or constant would empty the regression).

        Args:
            matrix (DriverMatrix): The observations.
            usable (List[ProviderMetric]): The criteria correlated with the target.

        Returns:
            DriverMatrix: The observations of these criteria only.
        """
        columns = [column for column, criterion in enumerate(matrix.criteria) if criterion in usable]
        kept = replace(matrix, criteria=[matrix.criteria[column] for column in columns], x=matrix.x[:, columns])
        complete = int(kept.complete_rows().sum())
        self.logger.debug(
            "%d of %d criteria usable, %d complete observations.", len(columns), len(matrix.criteria), complete
        )
        return replace(kept, dropped=int(numpy.isfinite(kept.y).sum()) - complete)

    def _leads(
        self, query: DriverQuery, matrix: DriverMatrix, correlations: List[CorrelationCell]
    ) -> List[CorrelationCell]:
        """Test whether each correlated criterion leads the target (panel only).

        Args:
            query (DriverQuery): The analysis.
            matrix (DriverMatrix): Its observations (their series of yearly changes).
            correlations (List[CorrelationCell]): The correlations.

        Returns:
            List[CorrelationCell]: The correlations with their Granger p-values (`None` without enough history), as
                they are on the latest quarter.
        """
        if query.scope is not DriverScope.PANEL:
            return correlations
        tested = [
            cell.model_copy(
                update={"granger_p": self.granger.p_value(matrix.series, query.target, cell.criterion, query.lag)}
            )
            for cell in correlations
        ]
        self.logger.debug(
            "Granger tests of %s: %d of %d criteria tested.",
            query.target,
            sum(cell.granger_p is not None for cell in tested),
            len(tested),
        )
        return tested

    def _regress(self, query: DriverQuery, matrix: DriverMatrix) -> RegressionOutcome:
        """Run the regression of the scope.

        Args:
            query (DriverQuery): The analysis.
            matrix (DriverMatrix): Its observations.

        Returns:
            RegressionOutcome: The fit, the coefficients and the warnings.
        """
        match query.scope:
            case DriverScope.PANEL:
                return self.panel_regression.regress(matrix, query.bootstrap, query.seed)
            case _:
                rows = numpy.flatnonzero(matrix.complete_rows())
                return self.regression.regress(
                    matrix.y[rows],
                    matrix.x[rows],
                    matrix.criteria,
                    [matrix.providers[row] for row in rows],
                    query.bootstrap,
                    query.seed,
                )

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self, query: DriverQuery, values: List[ProviderMetricValue]) -> DriverResult:
        """Run an analysis on the stored measures.

        Args:
            query (DriverQuery): The target, the criteria, the scope, the lag and the controls.
            values (List[ProviderMetricValue]): The measures of the providers.

        Returns:
            DriverResult: The correlations, the regression, the criteria ranked by importance, and the warnings.
        """
        self.logger.debug("Analysing the drivers of %s (%s).", query.target, query.scope)
        matrix = self.panel.build(query, values)
        correlations, found = self.correlations.analyse(matrix, query.bootstrap, query.seed)
        correlations = self._leads(query, matrix, correlations)
        usable = [cell.criterion for cell in correlations]
        left_out = [criterion for criterion in matrix.criteria if criterion not in usable]
        matrix = self._usable(matrix, usable)
        warnings = self._caveats(query, matrix)
        if not usable:
            history = query.scope is DriverScope.PANEL
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.NOTHING_CORRELATED,
                    message="No criterion can be correlated with the target"
                    + (": a panel needs a year of history per provider." if history else "."),
                )
            )
        if left_out and usable:
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.LEFT_OUT,
                    message="Left out of the regression (not correlated with the target): "
                    + ", ".join(criterion.value for criterion in left_out)
                    + ".",
                    subjects=left_out,
                )
            )
        fit, coefficients, regressed = self._regress(query, matrix) if usable else (None, [], [])
        leads = {cell.criterion: cell.granger_p for cell in correlations}
        coefficients = [
            coefficient.model_copy(update={"granger_p": leads.get(coefficient.criterion)})
            for coefficient in coefficients
        ]
        complete = matrix.complete_rows()
        result = DriverResult(
            query=query,
            observations=int(complete.sum()),
            providers=len({provider for provider, kept in zip(matrix.providers, complete, strict=True) if kept}),
            r2=fit.r2 if fit is not None else None,
            loo_r2=fit.loo_r2 if fit is not None else None,
            correlations=correlations,
            coefficients=coefficients,
            warnings=[*{(warning.kind, warning.message): warning for warning in warnings + found + regressed}.values()],
        )
        if result.warnings:
            self.logger.warning("Drivers of %s: %d warnings.", query.target, len(result.warnings))
        self.logger.info(
            "Drivers of %s: %d observations, R2 %s.",
            query.target,
            result.observations,
            "n/a" if result.r2 is None else f"{result.r2:.3f}",
        )
        return result
