from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.enums import CompoundingCard, CurveKind
from models.compounding.help.compounding_help import CompoundingHelp
from models.compounding.results.fits.estimate import Estimate
from models.compounding.results.fits.regression_fit import RegressionFit


class CompoundingDocRenderer:
    """Print the generated blocks of the service-compounding results document.

    Attributes:
        START (ClassVar[str]): The opening marker of a block.
        END (ClassVar[str]): The closing marker of a block.
        RUN (ClassVar[str]): The block saying when and with what the results were computed.
        ROBUSTNESS (ClassVar[str]): The block of the summaries of the other specifications.
        SCOPE (ClassVar[str]): The block of the curated scope (providers, domains, foundation sets with sources).
        help (CompoundingHelp): The titles of the columns, curves and verdicts.
        logger (Logger): The renderer logger.

    Notes:
        - There is one block per card of the Analysis tab section (`CompoundingCard`), so that the document and the
          GUI show the same tables: the GUI cards and the document blocks both read one `CompoundingReport`.
        - The scope block follows the configuration only: `render-compounding-doc --check` checks it without the
          database. Every other block needs the database.
    """

    START: ClassVar[str] = "<!-- compounding:{name}:start -->"
    END: ClassVar[str] = "<!-- compounding:{name}:end -->"
    RUN: ClassVar[str] = "run"
    ROBUSTNESS: ClassVar[str] = "robustness"
    SCOPE: ClassVar[str] = "scope"

    def __init__(self, help_texts: CompoundingHelp, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            help_texts (CompoundingHelp): The titles of the columns, curves and verdicts.
            logger (Optional[Logger]): The renderer logger.
        """
        self.help = help_texts
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _table(self, headers: Sequence[str], rows: List[List[str]]) -> str:
        """Print a Markdown table.

        Args:
            headers (Sequence[str]): The column titles.
            rows (List[List[str]]): The cells.

        Returns:
            str: The table, or a line saying it is empty.
        """
        if not rows:
            return "_Nothing to show: too few entries or no data._"
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        lines.extend("| " + " | ".join(cells) + " |" for cells in rows)
        return "\n".join(lines)

    def _provider(self, provider: Optional[CloudProvider]) -> str:
        """Name a provider.

        Args:
            provider (Optional[CloudProvider]): The provider, `None` for the pooled fit.

        Returns:
            str: Its key in backticks, `Pooled` for the pooled fit.
        """
        return f"`{provider.value}`" if provider else "Pooled"

    def _number(self, value: Optional[float], pattern: str = "{:.3g}") -> str:
        """Print a number.

        Args:
            value (Optional[float]): The number.
            pattern (str): Its format.

        Returns:
            str: The number, a dash when unknown.
        """
        return "-" if value is None else pattern.format(value)

    def _estimate(self, estimate: Optional[Estimate]) -> str:
        """Print a coefficient and its interval.

        Args:
            estimate (Optional[Estimate]): The coefficient.

        Returns:
            str: `+0.59 [-0.79, +1.48]`, in bold when the interval excludes zero, a dash when not fitted.
        """
        if estimate is None:
            return "-"
        if estimate.low is None or estimate.high is None:
            return f"{estimate.value:+.3g}"
        text = f"{estimate.value:+.3g} [{estimate.low:+.3g}, {estimate.high:+.3g}]"
        return f"**{text}**" if estimate.significant() else text

    def _fits(self, fits: List[RegressionFit], names: Sequence[str]) -> str:
        """Print logit fits.

        Args:
            fits (List[RegressionFit]): The fits.
            names (Sequence[str]): The coefficients printed.

        Returns:
            str: The table.
        """
        headers = ["Provider", "Entries", "Rows", *(self.help.title("columns", name) for name in names), "Converged"]
        rows = [
            [
                self._provider(fit.provider),
                str(fit.events),
                str(fit.rows),
                *(self._estimate(fit.estimate(name)) for name in names),
                "yes" if fit.converged else "no",
            ]
            for fit in fits
        ]
        return self._table(headers, rows)

    def _yearly(self, report: CompoundingReport, shares: bool) -> str:
        """Print a provider-by-year table of the catalogue sizes or of the shares.

        Args:
            report (CompoundingReport): The analysis.
            shares (bool): Whether to print the market shares, else the catalogue sizes.

        Returns:
            str: The table, one row per year.
        """
        providers: List[CloudProvider] = []
        values: Dict[int, Dict[CloudProvider, str]] = {}
        for row in report.provider_years:
            if row.provider not in providers:
                providers.append(row.provider)
            cell = self._number(row.share, "{:.1f}") if shares else str(row.size)
            values.setdefault(row.year, {})[row.provider] = cell + (
                " (dossier)" if shares and row.share_origin.value == "manual" else ""
            )
        rows = [[str(year), *(values[year].get(provider, "") for provider in providers)] for year in sorted(values)]
        if shares:
            rows = [row for row in rows if any(cell not in ("", "-") for cell in row[1:])]
        return self._table(["Year", *(self._provider(provider) for provider in providers)], rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    def foundations(self, config: CompoundingConfig) -> str:
        """Print the curated scope: the providers, the domains and the foundation sets with their sources.

        Args:
            config (CompoundingConfig): The configuration.

        Returns:
            str: The block.
        """
        providers = self._table(
            ["Provider", "Cloud start", "Source"],
            [
                [self._provider(scope.provider), str(scope.start or "first launch"), scope.source or "-"]
                for scope in config.providers
            ]
            + [[self._provider(entry.provider) + " (excluded)", "-", entry.reason] for entry in config.excluded],
        )
        links = self._table(
            ["Category", "Foundation", "Source"],
            [
                [f"`{entry.category}`", f"`{link.foundation}`", link.source]
                for entry in config.foundations
                for link in entry.links
            ],
        )
        domains = ", ".join(f"`{domain}`" for domain in config.domains)
        return f"{providers}\n\nDomains kept: {domains}.\n\n{links}"

    def run_stamp(self, report: CompoundingReport, day: date) -> str:
        """Print when and with what the main results were computed.

        Args:
            report (CompoundingReport): The main analysis.
            day (date): The day of the run.

        Returns:
            str: The block.
        """
        query = report.query
        return (
            f"Computed on {day.isoformat()} from the development database: controls "
            f"`{query.specification.value}`, foundations `{query.source.value}`, lag {query.lag} year(s), "
            f"{len(report.coverage)} providers."
        )

    def summary(self, report: CompoundingReport) -> str:
        """Print what every model says about each provider.

        Args:
            report (CompoundingReport): The analysis.

        Returns:
            str: The table.
        """
        return self._table(
            [
                "Provider",
                "Entries",
                "Heaps",
                "Launches per product",
                "Best curve",
                "Density",
                "Foundations",
                "Experience",
                "Size",
                "Share",
                "Market",
                "Placebo p",
                "Transfer gain",
                "Verdict",
            ],
            [
                [
                    self._provider(row.provider) + (" (excluded)" if row.excluded else ""),
                    str(row.events),
                    self._estimate(row.heaps),
                    self._estimate(row.growth),
                    self.help.title("curves", row.best_curve.value) if row.best_curve else "-",
                    self._estimate(row.density),
                    self._estimate(row.foundations),
                    self._estimate(row.experience),
                    self._estimate(row.size),
                    self._estimate(row.share),
                    self._estimate(row.market),
                    self._number(row.placebo, "{:.3f}"),
                    self._number(row.transfer, "{:+.3f}"),
                    f"**{self.help.title('verdicts', row.verdict.value)}**",
                ]
                for row in report.summary
            ],
        )

    def card(self, card: CompoundingCard, report: CompoundingReport) -> str:
        """Print the table of a card.

        Args:
            card (CompoundingCard): The card.
            report (CompoundingReport): The analysis.

        Returns:
            str: The block.
        """
        match card:
            case CompoundingCard.CONTROLS:
                coverage = self._table(
                    ["Provider", "Products", "Held", "Window", "Entries", "Share years"],
                    [
                        [
                            self._provider(row.provider) + (" (excluded)" if row.excluded else ""),
                            str(row.products),
                            str(row.held),
                            f"{row.first}-{row.last}",
                            str(row.events),
                            str(row.share_years),
                        ]
                        for row in report.coverage
                    ],
                )
                caveats = "\n".join(
                    f"- {self.help.title('warnings', warning.kind.value)}"
                    f"{' (' + self._provider(warning.provider) + ')' if warning.provider else ''}: {warning.detail}"
                    for warning in report.warnings
                )
                return f"{coverage}\n\n{caveats}" if caveats else coverage
            case CompoundingCard.LAUNCHES:
                return self._yearly(report, False)
            case CompoundingCard.SHARES:
                return self._yearly(report, True)
            case CompoundingCard.MARKET:
                return self._table(
                    ["Year", "Size (billion USD)", "Origin", "Log growth", "Older perimeter"],
                    [
                        [
                            str(year.year),
                            self._number(year.size_bn, "{:.1f}"),
                            year.origin.value,
                            self._number(year.growth, "{:.3f}"),
                            "yes" if year.perimeter_break else "",
                        ]
                        for year in report.market_years
                    ],
                )
            case CompoundingCard.HEAPS:
                return self._table(
                    ["Provider", "Heaps slope", "R²", "Years"],
                    [
                        [
                            self._provider(fit.provider),
                            self._estimate(fit.slope),
                            self._number(fit.r2, "{:.2f}"),
                            str(len(fit.points)),
                        ]
                        for fit in report.heaps
                    ],
                )
            case CompoundingCard.GROWTH:
                curves = list(CurveKind)
                return self._table(
                    [
                        "Provider",
                        "Launches per product",
                        "Share",
                        "Market growth",
                        "R²",
                        "Years",
                        "Best curve",
                        *(f"AIC {self.help.title('curves', curve.value)}" for curve in curves),
                    ],
                    [
                        [
                            self._provider(fit.provider),
                            self._estimate(fit.estimate("size")),
                            self._estimate(fit.estimate("share")),
                            self._estimate(fit.estimate("market")),
                            self._number(fit.r2, "{:.2f}"),
                            str(fit.years),
                            self.help.title("curves", fit.best.value) if fit.best else "-",
                            *(
                                self._number(
                                    next((found.aic for found in fit.curves if found.kind is curve), None), "{:.1f}"
                                )
                                for curve in curves
                            ),
                        ]
                        for fit in report.growth
                    ],
                )
            case CompoundingCard.ENTRY:
                return self._fits(report.entry, ["density", "size", "market", "share"])
            case CompoundingCard.HAZARD:
                return self._fits(report.hazard, ["foundations", "experience", "size", "market", "share"])
            case CompoundingCard.PLACEBO:
                return self._table(
                    ["Fit", "Real foundation coefficient", "Random sets", "Placebo p"],
                    [
                        [
                            self._provider(test.provider),
                            f"{test.real:+.3g}",
                            str(len(test.draws)),
                            self._number(test.p_value, "{:.3f}"),
                        ]
                        for test in report.placebo
                    ],
                )
            case CompoundingCard.LAGS:
                return self._table(
                    ["Fit", "Lag (years)", "Entries", "Foundations", "Experience"],
                    [
                        [
                            self._provider(fit.provider),
                            str(fit.lag),
                            str(fit.events),
                            self._estimate(fit.estimate("foundations")),
                            self._estimate(fit.estimate("experience")),
                        ]
                        for fit in report.lags
                    ],
                )
            case CompoundingCard.TRANSFER:
                return self._table(
                    [
                        "Provider",
                        "Entries",
                        "Rows",
                        "AUC",
                        "AUC without foundations",
                        "Gain",
                        "Log score",
                        "Without foundations",
                    ],
                    [
                        [
                            self._provider(score.provider),
                            str(score.events),
                            str(score.rows),
                            self._number(score.auc, "{:.3f}"),
                            self._number(score.baseline_auc, "{:.3f}"),
                            self._number(score.gain(), "{:+.3f}"),
                            self._number(score.log_score, "{:.4f}"),
                            self._number(score.baseline_log_score, "{:.4f}"),
                        ]
                        for score in report.transfer
                    ],
                )
            case CompoundingCard.SUMMARY:
                return self.summary(report)
            case CompoundingCard.FOUNDATIONS:
                return self._table(
                    ["Category", "Foundations used"],
                    [
                        [f"`{category}`", ", ".join(f"`{slug}`" for slug in found)]
                        for category, found in sorted(report.foundations.items())
                    ],
                )

    def robustness(self, reports: List[CompoundingReport]) -> str:
        """Print the summaries of the other specifications.

        Args:
            reports (List[CompoundingReport]): The other analyses.

        Returns:
            str: One titled summary per analysis.
        """
        parts = [
            f"**Controls `{report.query.specification.value}`, foundations `{report.query.source.value}`, lag "
            f"{report.query.lag}.**\n\n{self.summary(report)}"
            for report in reports
        ]
        return "\n\n".join(parts)

    def splice(self, text: str, name: str, block: str) -> str:
        """Put a generated block between its markers.

        Args:
            text (str): The document.
            name (str): The block name.
            block (str): The block.

        Returns:
            str: The document with the block replaced, unchanged when the markers are missing.
        """
        start, end = self.START.format(name=name), self.END.format(name=name)
        if start not in text or end not in text:
            self.logger.warning("The markers of the %s block are missing: the document is left as is.", name)
            return text
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        return f"{head}{start}\n{block}\n{end}{tail}"

    def names(self) -> List[str]:
        """Get the names of every block.

        Returns:
            List[str]: The scope, the run stamp, one block per card, then the robustness block.
        """
        return [self.SCOPE, self.RUN, *(card.value for card in CompoundingCard), self.ROBUSTNESS]
