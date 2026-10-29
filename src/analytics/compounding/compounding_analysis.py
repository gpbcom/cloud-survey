from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.compounding.data.covariates.category_density import CategoryDensity
from analytics.compounding.data.covariates.foundation_share import FoundationShare
from analytics.compounding.data.entry_panel import EntryPanel
from analytics.compounding.data.risk_set import RiskSet
from analytics.compounding.data.risk_set_builder import RiskSetBuilder
from analytics.compounding.estimators.curves.growth_fitter import GrowthFitter
from analytics.compounding.estimators.curves.heaps_fitter import HeapsFitter
from analytics.compounding.estimators.curves.ordinary_least_squares import OrdinaryLeastSquares
from analytics.compounding.estimators.logit_estimator import LogitEstimator
from analytics.compounding.estimators.logit_fit import LogitFit
from analytics.compounding.estimators.placebo_test import PlaceboTest
from analytics.compounding.estimators.roc_scorer import RocScorer
from analytics.compounding.summary_builder import SummaryBuilder
from models.cloud.enums import CloudProvider
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.enums import CompoundingWarningKind, FitKind, FoundationSource, Specification, ValueOrigin
from models.compounding.results.fits.estimate import Estimate
from models.compounding.results.fits.regression_fit import RegressionFit
from models.compounding.results.scores.compounding_warning import CompoundingWarning
from models.compounding.results.scores.placebo_result import PlaceboResult
from models.compounding.results.scores.transfer_score import TransferScore

type FoundationSets = Dict[CloudProvider, Dict[int, NDArray[numpy.intp]]]


class CompoundingAnalysis:
    """Fit the service-compounding models on AWS, on each provider analysed and on all of them pooled.

    Attributes:
        config (CompoundingConfig): The scope and the curated inputs.
        estimator (LogitEstimator): The logit estimator.
        scorer (RocScorer): The scorer of the predictions from AWS.
        least_squares (OrdinaryLeastSquares): The least-squares estimator.
        logger (Logger): The analysis logger.

    Notes:
        - It never opens the database: `CompoundingLoader` reads the data, and the Analysis tab and the
          `render-compounding-doc` script both show the report it returns.
        - Every provider is fitted on its own, the kept providers also pooled (with provider effects). An excluded
          provider is fitted on its own only, as a flagged robustness row.
        - The transfer fits the foundation hazard on AWS and predicts every other provider's entries with it, against
          the same model without the foundation terms.
    """

    def __init__(self, config: CompoundingConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the analysis.

        Args:
            config (CompoundingConfig): The scope and the curated inputs.
            logger (Optional[Logger]): The analysis logger.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.estimator = LogitEstimator(self.logger)
        self.scorer = RocScorer(self.logger)
        self.least_squares = OrdinaryLeastSquares(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _sets(
        self, source: FoundationSource, foundation: FoundationShare, providers: Sequence[CloudProvider]
    ) -> FoundationSets:
        """Get the foundation columns of each provider.

        Args:
            source (FoundationSource): Where the foundations come from.
            foundation (FoundationShare): The foundation covariate.
            providers (Sequence[CloudProvider]): The providers fitted.

        Returns:
            FoundationSets: The foundation columns of each dependent category, for each provider.
        """
        if source is FoundationSource.CURATED:
            curated = foundation.curated(self.config.foundation_sets())
            return {provider: curated for provider in providers}
        return {provider: foundation.data_driven(provider) for provider in providers}

    def _logit(
        self,
        builder: RiskSetBuilder,
        kind: FitKind,
        providers: Sequence[CloudProvider],
        query: CompoundingQuery,
        lag: int,
        sets: FoundationSets,
        label: Optional[CloudProvider],
    ) -> Tuple[RegressionFit, RiskSet, Optional[LogitFit]]:
        """Fit a density model or a foundation hazard.

        Args:
            builder (RiskSetBuilder): The risk set builder.
            kind (FitKind): The model.
            providers (Sequence[CloudProvider]): The providers fitted (several: pooled).
            query (CompoundingQuery): What is fitted.
            lag (int): The years the foundations must have been held.
            sets (FoundationSets): The foundation columns.
            label (Optional[CloudProvider]): The provider of the fit, `None` when pooled.

        Returns:
            Tuple[RegressionFit, RiskSet, Optional[LogitFit]]: The fit, its risk set and the raw logit (`None` when
                too few entries).
        """
        settings = self.config.settings
        risk_set = builder.build(kind, providers, query.specification, lag, sets)
        common = {
            "kind": kind,
            "provider": label,
            "specification": query.specification,
            "lag": lag,
            "source": query.source,
            "rows": risk_set.rows(),
            "events": risk_set.events(),
        }
        if risk_set.events() < settings.min_events:
            return RegressionFit(converged=False, **common), risk_set, None
        fit = self.estimator.fit(risk_set.x, risk_set.y)
        bounds = self.estimator.bootstrap(
            risk_set.x, risk_set.y, risk_set.columns, settings.bootstrap if fit.converged else 0, settings.seed
        )
        estimates = [
            Estimate(name=name, value=float(value), low=low, high=high)
            for name, value, (low, high) in zip(risk_set.names, fit.beta, bounds, strict=True)
            if not name.startswith("fe:")
        ]
        regression = RegressionFit(
            converged=fit.converged, log_likelihood=fit.log_likelihood, estimates=estimates, **common
        )
        return regression, risk_set, fit

    def _transfer(
        self,
        builder: RiskSetBuilder,
        query: CompoundingQuery,
        sets: FoundationSets,
        others: Sequence[CloudProvider],
    ) -> List[TransferScore]:
        """Predict the other providers' entries with the foundation hazard fitted on AWS.

        Args:
            builder (RiskSetBuilder): The risk set builder.
            query (CompoundingQuery): What is fitted.
            sets (FoundationSets): The foundation columns.
            others (Sequence[CloudProvider]): The providers predicted.

        Returns:
            List[TransferScore]: The score of each provider, none when the AWS fit fails.
        """
        aws = CloudProvider.AWS
        source = builder.build(FitKind.HAZARD, [aws], query.specification, query.lag, sets)
        full = self.estimator.fit(source.x, source.y)
        baseline = self.estimator.fit(source.x[:, 2:], source.y)
        if source.events() < self.config.settings.min_events or not full.converged or not baseline.converged:
            self.logger.warning("The AWS hazard did not fit: no transfer.")
            return []
        scores: List[TransferScore] = []
        for provider in others:
            target = builder.build(FitKind.HAZARD, [provider], query.specification, query.lag, sets)
            if target.rows() == 0:
                continue
            predicted = self.estimator.predict(full, target.x)
            reference = self.estimator.predict(baseline, target.x[:, 2:])
            scores.append(
                TransferScore(
                    provider=provider,
                    rows=target.rows(),
                    events=target.events(),
                    auc=self.scorer.auc(target.y, predicted),
                    baseline_auc=self.scorer.auc(target.y, reference),
                    log_score=self.scorer.log_score(target.y, predicted),
                    baseline_log_score=self.scorer.log_score(target.y, reference),
                )
            )
        return scores

    def _warnings(
        self,
        panel: EntryPanel,
        query: CompoundingQuery,
        providers: Sequence[CloudProvider],
        excluded: Sequence[CloudProvider],
        fits: Sequence[RegressionFit],
    ) -> List[CompoundingWarning]:
        """List the caveats of the analysis.

        Args:
            panel (EntryPanel): The yearly catalogues.
            query (CompoundingQuery): What is fitted.
            providers (Sequence[CloudProvider]): The providers fitted.
            excluded (Sequence[CloudProvider]): The providers outside the public-cloud scope.
            fits (Sequence[RegressionFit]): Every logit fit.

        Returns:
            List[CompoundingWarning]: The caveats.
        """
        warnings: List[CompoundingWarning] = []
        asked = query.providers or [*self.config.kept(), *(entry.provider for entry in self.config.excluded)]
        for provider in asked:
            if provider not in panel.windows:
                warnings.append(
                    CompoundingWarning(
                        kind=CompoundingWarningKind.NO_DATA, provider=provider, detail="No dated product kept."
                    )
                )
        for provider in excluded:
            reason = next((entry.reason for entry in self.config.excluded if entry.provider is provider), "")
            warnings.append(CompoundingWarning(kind=CompoundingWarningKind.EXCLUDED, provider=provider, detail=reason))
        for provider in providers:
            first, last = panel.windows[provider]
            if query.specification is Specification.SHARE and not any(
                (provider, year) in panel.shares for year in range(first, last + 1)
            ):
                warnings.append(
                    CompoundingWarning(
                        kind=CompoundingWarningKind.NO_SHARE, provider=provider, detail="No market share in its window."
                    )
                )
        for fit in fits:
            if fit.events < self.config.settings.min_events:
                warnings.append(
                    CompoundingWarning(
                        kind=CompoundingWarningKind.FEW_EVENTS,
                        provider=fit.provider,
                        detail=f"{fit.kind.value}: {fit.events} entries, {self.config.settings.min_events} needed.",
                    )
                )
            elif not fit.converged:
                warnings.append(
                    CompoundingWarning(
                        kind=CompoundingWarningKind.NOT_CONVERGED,
                        provider=fit.provider,
                        detail=f"{fit.kind.value} fit.",
                    )
                )
        manual = [year for year, (_, origin, _) in panel.market.items() if origin is ValueOrigin.MANUAL]
        if manual:
            warnings.append(
                CompoundingWarning(
                    kind=CompoundingWarningKind.MARKET_FALLBACK,
                    detail="Curated market sizes: " + ", ".join(str(year) for year in sorted(manual)) + ".",
                )
            )
        return warnings

    def _foundations(
        self, query: CompoundingQuery, foundation: FoundationShare, panel: EntryPanel
    ) -> Dict[str, List[str]]:
        """Get the foundation sets used, by category slug.

        Args:
            query (CompoundingQuery): What is fitted.
            foundation (FoundationShare): The foundation covariate.
            panel (EntryPanel): The yearly catalogues.

        Returns:
            Dict[str, List[str]]: The foundations of each dependent category (data-driven ones over every kept
                provider).
        """
        columns = (
            foundation.curated(self.config.foundation_sets())
            if query.source is FoundationSource.CURATED
            else foundation.data_driven(None)
        )
        names = panel.categories
        return {names[column]: [names[int(other)] for other in others] for column, others in sorted(columns.items())}

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self, query: CompoundingQuery, data: CompoundingData) -> CompoundingReport:
        """Fit every model of the query.

        Args:
            query (CompoundingQuery): What is fitted.
            data (CompoundingData): What the database holds.

        Returns:
            CompoundingReport: Every series, fit, test and caveat.
        """
        settings = self.config.settings
        panel = EntryPanel(data, self.config, self.logger).build()
        asked = query.providers or panel.providers()
        providers = [provider for provider in asked if provider in panel.windows]
        kept = [provider for provider in providers if provider in self.config.kept()]
        excluded = [provider for provider in providers if provider not in kept]
        density = CategoryDensity(panel.categories, data.snapshot, self.logger)
        foundation = FoundationShare(panel, settings, self.logger)
        builder = RiskSetBuilder(panel, density, foundation, self.logger)
        sets = self._sets(query.source, foundation, providers)
        heaps_fitter = HeapsFitter(self.least_squares, self.logger)
        growth_fitter = GrowthFitter(self.least_squares, self.logger)
        years = panel.provider_years()
        heaps = [
            heaps_fitter.fit(
                provider, [(float(row.size), float(row.categories)) for row in years if row.provider is provider]
            )
            for provider in providers
        ]
        growth = [growth_fitter.fit(panel, provider, query.specification) for provider in providers]
        groups: List[Tuple[List[CloudProvider], Optional[CloudProvider]]] = [
            ([provider], provider) for provider in providers
        ]
        if len(kept) > 1:
            groups.append((kept, None))
        entry: List[RegressionFit] = []
        hazard: List[RegressionFit] = []
        placebo: List[PlaceboResult] = []
        tester = PlaceboTest(builder, self.estimator, self.logger)
        for members, label in groups:
            entry.append(self._logit(builder, FitKind.ENTRY, members, query, 1, sets, label)[0])
            fit, risk_set, raw = self._logit(builder, FitKind.HAZARD, members, query, query.lag, sets, label)
            hazard.append(fit)
            if raw is not None and raw.converged and settings.placebo > 0:
                placebo.append(
                    tester.run(
                        risk_set,
                        {member: sets[member] for member in members},
                        len(panel.categories),
                        float(raw.beta[0]),
                        query.lag,
                        settings.placebo,
                        settings.seed,
                        label,
                    )
                )
        lags: List[RegressionFit] = []
        for lag in settings.lags:
            for members, label in [([CloudProvider.AWS], CloudProvider.AWS), (kept, None)]:
                if all(member in panel.windows for member in members) and members and (label or len(kept) > 1):
                    lags.append(self._logit(builder, FitKind.HAZARD, members, query, lag, sets, label)[0])
        transfer = (
            self._transfer(
                builder, query, sets, [provider for provider in providers if provider is not CloudProvider.AWS]
            )
            if CloudProvider.AWS in panel.windows
            else []
        )
        labels: List[Optional[CloudProvider]] = [*providers, None] if len(kept) > 1 else list(providers)
        summary = SummaryBuilder(settings.min_events, self.logger).build(
            labels, excluded, heaps, growth, entry, hazard, placebo, transfer
        )
        report = CompoundingReport(
            query=query,
            coverage=[row for row in panel.coverage() if row.provider in providers],
            provider_years=[row for row in years if row.provider in providers],
            market_years=panel.market_years(),
            heaps=heaps,
            growth=growth,
            entry=entry,
            hazard=hazard,
            lags=lags,
            placebo=placebo,
            transfer=transfer,
            summary=summary,
            foundations=self._foundations(query, foundation, panel),
            warnings=self._warnings(panel, query, providers, excluded, [*entry, *hazard]),
        )
        self.logger.info(
            "Compounding analysis: %d providers, %d hazard fits, %d placebo tests, %d transfers.",
            len(providers),
            len(hazard),
            len(placebo),
            len(transfer),
        )
        return report
