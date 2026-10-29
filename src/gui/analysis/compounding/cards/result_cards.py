from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

# First Party Imports.
from gui.analysis.compounding.cards.card_format import CardFormat
from gui.analysis.compounding.cards.report_table import ReportTable
from gui.analysis.compounding.charts.coefficient_chart import CoefficientChart, CoefficientRow
from gui.analysis.compounding.charts.heaps_chart import HeapsChart, HeapsSeries
from gui.analysis.compounding.charts.placebo_chart import PlaceboChart
from gui.analysis.markets.charts.time_series_chart import TimeSeriesChart
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.compounding.compounding_report import CompoundingReport
from models.compounding.enums import CompoundingColumn, CompoundingControl
from models.compounding.help.compounding_help import CompoundingHelp
from models.compounding.results.fits.estimate import Estimate
from models.compounding.results.fits.regression_fit import RegressionFit
from models.markets.charts.chart_line import ChartLine


class ResultCards:
    """The cards of the Service compounding results, one per model, with its chart and table.

    Attributes:
        CURVE_COLORS (ClassVar[Dict[str, str]]): The colour of each fitted growth curve.
        theme (Theme): The application theme.
        help (CompoundingHelp): The explanations shown in the tooltips.
        format (CardFormat): The writer of the figures.
        report (Optional[CompoundingReport]): The analysis shown, `None` before the first run.
        heaps_chart (HeapsChart): Heaps' law of every provider.
        heaps_table (ReportTable): The slopes.
        growth_box (CompactCombo): The provider whose growth curves are drawn.
        growth_chart (TimeSeriesChart): Its catalogue size and fitted curves.
        growth_table (ReportTable): The linear rates and the AIC of every curve.
        entry_chart (CoefficientChart): The density coefficients.
        entry_table (ReportTable): The density fits.
        hazard_chart (CoefficientChart): The foundation and experience coefficients.
        hazard_table (ReportTable): The hazard fits.
        placebo_box (CompactCombo): The fit whose placebo test is drawn.
        placebo_chart (PlaceboChart): Its random coefficients and the real one.
        lags_chart (CoefficientChart): The foundation coefficient at every lag.
        transfer_chart (CoefficientChart): The area under the ROC curve of the AWS model on each provider.
        transfer_table (ReportTable): The transfer scores.
        summary_table (ReportTable): What every model says about each provider.
        heaps_body (QWidget): The card of Heaps' law.
        growth_body (QWidget): The card of the growth curves.
        entry_body (QWidget): The card of the density model.
        hazard_body (QWidget): The card of the foundation hazard.
        placebo_body (QWidget): The card of the placebo test.
        transfer_body (QWidget): The card of the transfer.
        logger (Logger): The cards logger.
    """

    CURVE_COLORS: ClassVar[Dict[str, str]] = {
        "exponential": "#e3a008",
        "logistic": "#3fb950",
        "bass": "#a371f7",
        "market": "#f85149",
    }

    def __init__(self, theme: Theme, help_texts: CompoundingHelp, logger: Optional[Logger] = None) -> None:
        """Build the cards, empty.

        Args:
            theme (Theme): The application theme.
            help_texts (CompoundingHelp): The explanations shown in the tooltips.
            logger (Optional[Logger]): The cards logger.
        """
        self.theme = theme
        self.help = help_texts
        self.logger = logger if logger else getLogger(__name__)
        self.format = CardFormat(theme, self.logger)
        self.report: Optional[CompoundingReport] = None
        self.heaps_chart = HeapsChart(theme, self.logger)
        self.heaps_table = ReportTable(self.logger)
        self.growth_box = CompactCombo(18, self.logger)
        self.growth_chart = TimeSeriesChart(theme, self.logger)
        self.growth_table = ReportTable(self.logger)
        self.entry_chart = CoefficientChart(theme, logger=self.logger)
        self.entry_table = ReportTable(self.logger)
        self.hazard_chart = CoefficientChart(theme, logger=self.logger)
        self.hazard_table = ReportTable(self.logger)
        self.placebo_box = CompactCombo(18, self.logger)
        self.placebo_chart = PlaceboChart(theme, self.logger)
        self.lags_chart = CoefficientChart(theme, logger=self.logger)
        self.transfer_chart = CoefficientChart(theme, zero=False, logger=self.logger)
        self.transfer_table = ReportTable(self.logger)
        self.summary_table = ReportTable(self.logger)
        derivative = QCheckBox(help_texts.title("controls", CompoundingControl.DERIVATIVE.value))
        derivative.setToolTip(help_texts.text("controls", CompoundingControl.DERIVATIVE.value))
        derivative.toggled.connect(self.growth_chart.set_derivative)
        self.heaps_body = self._stack([self.heaps_chart, self.heaps_table])
        self.growth_body = self._stack([self.growth_box, derivative, self.growth_chart, self.growth_table])
        self.entry_body = self._stack([self.entry_chart, self.entry_table])
        self.hazard_body = self._stack([self.hazard_chart, self.hazard_table])
        self.placebo_body = self._stack([self.placebo_box, self.placebo_chart])
        self.transfer_body = self._stack([self.transfer_chart, self.transfer_table])
        self.growth_box.currentIndexChanged.connect(self._draw_growth)
        self.placebo_box.currentIndexChanged.connect(self._draw_placebo)
        self.clear("Run the analysis to see the results.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _stack(self, widgets: Sequence[QWidget]) -> QWidget:
        """Stack widgets in a card body.

        Args:
            widgets (Sequence[QWidget]): The widgets, top first.

        Returns:
            QWidget: The card body.
        """
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            layout.addWidget(widget)
        return body

    def _column(self, column: CompoundingColumn) -> str:
        """Get a column title.

        Args:
            column (CompoundingColumn): The column.

        Returns:
            str: Its title.
        """
        return self.help.title("columns", column.value)

    def _tip(self, column: CompoundingColumn) -> str:
        """Get a column explanation.

        Args:
            column (CompoundingColumn): The column.

        Returns:
            str: Its explanation.
        """
        return self.help.text("columns", column.value)

    def _row(self, label: str, estimate: Optional[Estimate], color: str, tooltip: str) -> Optional[CoefficientRow]:
        """Turn a coefficient into a chart row.

        Args:
            label (str): The row name.
            estimate (Optional[Estimate]): The coefficient.
            color (str): The colour of the row.
            tooltip (str): What hovering the row explains.

        Returns:
            Optional[CoefficientRow]: The row, `None` when not fitted.
        """
        if estimate is None:
            return None
        return (label, estimate.value, estimate.low, estimate.high, color, tooltip)

    def _fit_rows(self, fits: List[RegressionFit], names: Sequence[str]) -> List[CoefficientRow]:
        """Turn the coefficients of logit fits into chart rows.

        Args:
            fits (List[RegressionFit]): The fits.
            names (Sequence[str]): The coefficients drawn.

        Returns:
            List[CoefficientRow]: A row per fit and coefficient fitted.
        """
        rows: List[CoefficientRow] = []
        for fit in fits:
            if not fit.converged:
                continue
            for name in names:
                tooltip = f"{self.format.provider(fit.provider)}: {fit.events} entries in {fit.rows} rows."
                row = self._row(
                    f"{self.format.provider(fit.provider)} · {name}",
                    fit.estimate(name),
                    self.format.color(fit.provider),
                    tooltip,
                )
                if row is not None:
                    rows.append(row)
        return rows

    def _fit_table(self, table: ReportTable, fits: List[RegressionFit], names: Sequence[CompoundingColumn]) -> None:
        """Write the logit fits in a table.

        Args:
            table (ReportTable): The table.
            fits (List[RegressionFit]): The fits.
            names (Sequence[CompoundingColumn]): The coefficient columns.
        """
        columns = [CompoundingColumn.PROVIDER, CompoundingColumn.EVENTS, *names]
        table.fill(
            [self._column(column) for column in columns] + ["Rows", "Converged"],
            [self._tip(column) for column in columns]
            + ["The provider-category-years at risk.", "Whether the fit converged."],
            [
                [
                    self.format.provider(fit.provider),
                    str(fit.events),
                    *(self.format.estimate(fit.estimate(column.value)) for column in names),
                    str(fit.rows),
                    "yes" if fit.converged else "no",
                ]
                for fit in fits
            ],
        )

    def _draw_growth(self) -> None:
        """Draw the catalogue size and the growth curves of the provider picked."""
        if self.report is None or self.growth_box.currentIndex() < 0:
            return
        fit = self.report.growth[self.growth_box.currentIndex()]
        observed = [(row.year, float(row.size)) for row in self.report.provider_years if row.provider is fit.provider]
        lines = [
            ChartLine(
                key="observed",
                label=f"{self.format.provider(fit.provider)} catalogue",
                color=self.format.color(fit.provider),
                points=[(self.format.day(year), size) for year, size in observed if size > 0],
                note="products",
            )
        ]
        for curve in fit.curves:
            if curve.aic is None:
                continue
            lines.append(
                ChartLine(
                    key=curve.kind.value,
                    label=f"{self.help.title('curves', curve.kind.value)} (AIC {curve.aic:.1f})",
                    color=self.CURVE_COLORS[curve.kind.value],
                    dashed=True,
                    points=[(self.format.day(year), size) for year, size in curve.points if size > 0],
                    note=self.help.text("curves", curve.kind.value),
                )
            )
        self.growth_chart.set_data(lines, [], "", False, True, f"compounding/growth/{fit.provider.value}")

    def _draw_placebo(self) -> None:
        """Draw the placebo test picked."""
        if self.report is None or self.placebo_box.currentIndex() < 0:
            return
        test = self.report.placebo[self.placebo_box.currentIndex()]
        self.placebo_chart.set_test(test.draws, test.real, test.p_value, key=f"compounding/placebo/{test.provider}")

    def _show_tables(self, report: CompoundingReport) -> None:
        """Write the Heaps, growth, transfer and summary tables.

        Args:
            report (CompoundingReport): The analysis.
        """
        self.heaps_table.fill(
            [self._column(CompoundingColumn.PROVIDER), self._column(CompoundingColumn.HEAPS), "R²", "Years"],
            [
                self._tip(CompoundingColumn.PROVIDER),
                self._tip(CompoundingColumn.HEAPS),
                "Share of the variance explained.",
                "Years drawn.",
            ],
            [
                [
                    self.format.provider(fit.provider),
                    self.format.estimate(fit.slope),
                    self.format.number(fit.r2, "{:.2f}"),
                    str(len(fit.points)),
                ]
                for fit in report.heaps
            ],
        )
        curve_names = ["exponential", "logistic", "bass", "market"]
        self.growth_table.fill(
            [
                self._column(CompoundingColumn.PROVIDER),
                self._column(CompoundingColumn.GROWTH),
                self._column(CompoundingColumn.SHARE),
                self._column(CompoundingColumn.MARKET),
                "R²",
                "Years",
                self._column(CompoundingColumn.BEST_CURVE),
            ]
            + [f"AIC {self.help.title('curves', name)}" for name in curve_names],
            [
                self._tip(CompoundingColumn.PROVIDER),
                self._tip(CompoundingColumn.GROWTH),
                self._tip(CompoundingColumn.SHARE),
                self._tip(CompoundingColumn.MARKET),
                "Share of the variance of the launches explained.",
                "Years of the linear rate.",
                self._tip(CompoundingColumn.BEST_CURVE),
            ]
            + [self.help.text("curves", name) for name in curve_names],
            [
                [
                    self.format.provider(fit.provider),
                    self.format.estimate(fit.estimate("size")),
                    self.format.estimate(fit.estimate("share")),
                    self.format.estimate(fit.estimate("market")),
                    self.format.number(fit.r2, "{:.2f}"),
                    str(fit.years),
                    self.help.title("curves", fit.best.value) if fit.best else "-",
                ]
                + [
                    self.format.number(
                        next((curve.aic for curve in fit.curves if curve.kind.value == name), None), "{:.1f}"
                    )
                    for name in curve_names
                ]
                for fit in report.growth
            ],
        )
        self.transfer_table.fill(
            [
                self._column(CompoundingColumn.PROVIDER),
                self._column(CompoundingColumn.EVENTS),
                "Rows",
                "AUC",
                "Baseline AUC",
                self._column(CompoundingColumn.TRANSFER),
                "Log score",
                "Baseline log score",
            ],
            [
                self._tip(CompoundingColumn.PROVIDER),
                self._tip(CompoundingColumn.EVENTS),
                "Rows predicted.",
                "Area under the ROC curve of the AWS model (0.5 is chance).",
                "The same without the foundation terms.",
                self._tip(CompoundingColumn.TRANSFER),
                "Mean log-likelihood per row (higher is better).",
                "The same without the foundation terms.",
            ],
            [
                [
                    self.format.provider(score.provider),
                    str(score.events),
                    str(score.rows),
                    self.format.number(score.auc, "{:.3f}"),
                    self.format.number(score.baseline_auc, "{:.3f}"),
                    self.format.number(score.gain(), "{:+.3f}"),
                    self.format.number(score.log_score, "{:.4f}"),
                    self.format.number(score.baseline_log_score, "{:.4f}"),
                ]
                for score in report.transfer
            ],
        )
        columns = [
            CompoundingColumn.PROVIDER,
            CompoundingColumn.EVENTS,
            CompoundingColumn.HEAPS,
            CompoundingColumn.GROWTH,
            CompoundingColumn.BEST_CURVE,
            CompoundingColumn.DENSITY,
            CompoundingColumn.FOUNDATIONS,
            CompoundingColumn.EXPERIENCE,
            CompoundingColumn.SIZE,
            CompoundingColumn.SHARE,
            CompoundingColumn.MARKET,
            CompoundingColumn.PLACEBO,
            CompoundingColumn.TRANSFER,
            CompoundingColumn.VERDICT,
        ]
        self.summary_table.fill(
            [self._column(column) for column in columns],
            [self._tip(column) for column in columns],
            [
                [
                    self.format.provider(row.provider) + (" (excluded)" if row.excluded else ""),
                    str(row.events),
                    self.format.estimate(row.heaps),
                    self.format.estimate(row.growth),
                    self.help.title("curves", row.best_curve.value) if row.best_curve else "-",
                    self.format.estimate(row.density),
                    self.format.estimate(row.foundations),
                    self.format.estimate(row.experience),
                    self.format.estimate(row.size),
                    self.format.estimate(row.share),
                    self.format.estimate(row.market),
                    self.format.number(row.placebo, "{:.3f}"),
                    self.format.number(row.transfer, "{:+.3f}"),
                    self.help.title("verdicts", row.verdict.value),
                ]
                for row in report.summary
            ],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def clear(self, message: str) -> None:
        """Empty every chart.

        Args:
            message (str): What they say.
        """
        self.heaps_chart.set_series([], message)
        self.growth_chart.set_message(message)
        for chart in (self.entry_chart, self.hazard_chart, self.lags_chart, self.transfer_chart):
            chart.set_rows([], message)
        self.placebo_chart.set_test([], None, None, message)

    def show(self, report: CompoundingReport) -> None:
        """Draw the results of an analysis.

        Args:
            report (CompoundingReport): The analysis.
        """
        self.report = report
        series: List[HeapsSeries] = [
            (fit.provider, fit.points, fit.slope.value if fit.slope else None, fit.intercept) for fit in report.heaps
        ]
        self.heaps_chart.set_series(series, "No catalogue to draw.", "compounding/heaps")
        self.growth_box.blockSignals(True)
        self.growth_box.clear()
        for fit in report.growth:
            self.growth_box.addItem(self.format.provider(fit.provider), fit.provider.value)
        self.growth_box.blockSignals(False)
        self._draw_growth()
        self.entry_chart.set_rows(
            self._fit_rows(report.entry, ["density"]), "No density fit: too few entries.", "compounding/entry"
        )
        self.hazard_chart.set_rows(
            self._fit_rows(report.hazard, ["foundations", "experience"]),
            "No hazard fit: too few entries.",
            "compounding/hazard",
        )
        lag_rows: List[CoefficientRow] = []
        for lag_fit in report.lags:
            row = (
                self._row(
                    f"{self.format.provider(lag_fit.provider)} · {lag_fit.lag} y",
                    lag_fit.estimate("foundations"),
                    self.format.color(lag_fit.provider),
                    f"{lag_fit.events} entries.",
                )
                if lag_fit.converged
                else None
            )
            if row is not None:
                lag_rows.append(row)
        self.lags_chart.set_rows(lag_rows, "No lag fit: too few entries.", "compounding/lags")
        transfer_rows: List[CoefficientRow] = []
        for score in report.transfer:
            tooltip = f"{score.events} entries in {score.rows} rows. 0.5 is chance."
            if score.auc is not None:
                transfer_rows.append(
                    (
                        f"{self.format.provider(score.provider)} · AWS model",
                        score.auc,
                        None,
                        None,
                        self.format.color(score.provider),
                        tooltip,
                    )
                )
            if score.baseline_auc is not None:
                transfer_rows.append(
                    (
                        f"{self.format.provider(score.provider)} · without foundations",
                        score.baseline_auc,
                        None,
                        None,
                        self.theme.TEXT_MUTED,
                        tooltip,
                    )
                )
        self.transfer_chart.set_rows(transfer_rows, "No transfer: the AWS hazard did not fit.", "compounding/transfer")
        self.placebo_box.blockSignals(True)
        self.placebo_box.clear()
        for test in report.placebo:
            self.placebo_box.addItem(self.format.provider(test.provider), str(test.provider))
        self.placebo_box.blockSignals(False)
        if report.placebo:
            self._draw_placebo()
        else:
            self.placebo_chart.set_test([], None, None, "No placebo test: no foundation hazard fitted.")
        self._fit_table(
            self.entry_table,
            report.entry,
            [CompoundingColumn.DENSITY, CompoundingColumn.SIZE, CompoundingColumn.MARKET, CompoundingColumn.SHARE],
        )
        self._fit_table(
            self.hazard_table,
            report.hazard,
            [
                CompoundingColumn.FOUNDATIONS,
                CompoundingColumn.EXPERIENCE,
                CompoundingColumn.SIZE,
                CompoundingColumn.MARKET,
                CompoundingColumn.SHARE,
            ],
        )
        self._show_tables(report)
        self.logger.info("Compounding results drawn: %d summary rows.", len(report.summary))
