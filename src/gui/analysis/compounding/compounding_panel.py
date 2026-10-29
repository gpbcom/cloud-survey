from __future__ import annotations

# Standard Library Imports.
import asyncio
import csv
from functools import partial
from logging import Logger, getLogger
from pathlib import Path
from typing import List, Optional, Tuple

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from analytics.compounding.compounding_analysis import CompoundingAnalysis
from analytics.compounding.config_loader import CompoundingConfigLoader
from analytics.compounding.data.compounding_loader import CompoundingLoader
from analytics.compounding.exception import CompoundingError
from analytics.compounding.help_loader import CompoundingHelpLoader

# First Party Imports.
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from gui.analysis.compounding.cards.card_format import CardFormat
from gui.analysis.compounding.cards.input_cards import InputCards
from gui.analysis.compounding.cards.report_table import ReportTable
from gui.analysis.compounding.cards.result_cards import ResultCards
from gui.analysis.compounding.controls.compounding_controls import CompoundingControls
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.enums import CompoundingCard, CompoundingColumn
from models.compounding.help.compounding_help import CompoundingHelp
from models.history.chronology import Chronology
from storage.exception import StorageError
from storage.storage import Storage

type CompoundingCardBody = Tuple[CompoundingCard, QWidget, bool]


class CompoundingPanel(QWidget):
    """The "Service compounding" analysis: does mastering some cloud services help a provider build the next ones.

    Attributes:
        crawl_requested (pyqtSignal): Emitted with `history` (the Synergy market history) or `all` (every source).
        theme (Theme): The application theme.
        loop (StorageLoop): Runs the database reads off the GUI thread.
        help (CompoundingHelp): The explanations shown in the tooltips.
        config (Optional[CompoundingConfig]): The scope of the analysis, `None` when it cannot be read.
        chronology (Chronology): The companies of the chronology (the providers of the market shares).
        format (CardFormat): The writer of the figures.
        controls (CompoundingControls): The pickers and buttons.
        summary (QLabel): What the last run did.
        caveats (QLabel): The caveats of the last run.
        coverage_table (ReportTable): What the database holds for each provider.
        inputs (InputCards): The cards of the inputs.
        results (ResultCards): The cards of the results.
        generation (int): The number of the latest run (a late answer of an earlier run is dropped).
        report (Optional[CompoundingReport]): The latest analysis shown.
        stale (bool): Whether a dataset was written since the latest run.
        logger (Logger): The panel logger.

    Notes:
        - The models are described in `docs/analysis/service-capability-compounding.md` and their results in
          `docs/analysis/service-capability-compounding-results.md`, which `render-compounding-doc` writes from the
          same report as this section.
        - The database is read on the storage thread, the models fitted in a worker thread: the GUI stays responsive.
    """

    crawl_requested = pyqtSignal(str)

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        chronology: Optional[Chronology] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the panel.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): Runs the database reads off the GUI thread.
            chronology (Optional[Chronology]): The chronology, `data/curated/chronology.json` by default.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.logger = logger if logger else getLogger(__name__)
        self.format = CardFormat(theme, self.logger)
        problems: List[str] = []
        try:
            self.help = CompoundingHelpLoader(self.logger).load()
        except CompoundingError as e:
            self.logger.warning("The compounding help cannot be read: %s", e)
            self.help, problems = CompoundingHelp(), [*problems, str(e)]
        try:
            self.config: Optional[CompoundingConfig] = CompoundingConfigLoader(self.logger).load()
        except CompoundingError as e:
            self.logger.warning("The compounding configuration cannot be read: %s", e)
            self.config, problems = None, [*problems, str(e)]
        try:
            self.chronology = chronology or BundleCatalogs(logger=self.logger).chronology()
        except CuratedError as e:
            self.logger.warning("The chronology cannot be read: %s", e)
            self.chronology, problems = Chronology(as_of="unknown"), [*problems, str(e)]
        offered = [*self.config.kept(), *(entry.provider for entry in self.config.excluded)] if self.config else []
        self.controls = CompoundingControls(theme, offered, self.help, self.logger)
        self.summary = QLabel("Run the analysis, after crawling the cloud market history once.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        self.caveats = QLabel(" ".join(problems))
        self.caveats.setObjectName("muted")
        self.caveats.setWordWrap(True)
        self.coverage_table = ReportTable(self.logger)
        self.inputs = InputCards(theme, self.help, self.config, self.logger)
        self.results = ResultCards(theme, self.help, self.logger)
        self.generation = 0
        self.report: Optional[CompoundingReport] = None
        self.stale = True
        self.controls.run_requested.connect(self.run)
        self.controls.export_requested.connect(self.export)
        self.controls.crawl_requested.connect(self.crawl_requested)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.controls)
        layout.addWidget(self.summary)
        layout.addWidget(self.coverage_table)
        layout.addWidget(self.caveats)
        self.logger.debug("Compounding panel built.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _compute(self, config: CompoundingConfig, query: CompoundingQuery, storage: Storage) -> CompoundingReport:
        """Read the data and fit the models (on the storage thread, the fit in a worker thread).

        Args:
            config (CompoundingConfig): The scope of the analysis.
            query (CompoundingQuery): What is fitted.
            storage (Storage): The open storage.

        Returns:
            CompoundingReport: The analysis.

        Raises:
            StorageError: If the database cannot be read.
        """
        data = await CompoundingLoader(config, self.chronology, self.logger).load(storage)
        return await asyncio.to_thread(CompoundingAnalysis(config, self.logger).run, query, data)

    def _show_coverage(self, report: CompoundingReport) -> None:
        """Write what the database holds for each provider.

        Args:
            report (CompoundingReport): The analysis.
        """
        columns = [
            CompoundingColumn.PROVIDER,
            CompoundingColumn.PRODUCTS,
            CompoundingColumn.HELD,
            CompoundingColumn.WINDOW,
            CompoundingColumn.EVENTS,
            CompoundingColumn.SHARE_YEARS,
        ]
        self.coverage_table.fill(
            [self.help.title("columns", column.value) for column in columns],
            [self.help.text("columns", column.value) for column in columns],
            [
                [
                    self.format.provider(row.provider) + (" (excluded)" if row.excluded else ""),
                    str(row.products),
                    str(row.held),
                    f"{row.first}-{row.last}",
                    str(row.events),
                    str(row.share_years),
                ]
                for row in report.coverage
            ],
        )

    def _show_caveats(self, report: CompoundingReport) -> None:
        """Write the caveats of an analysis.

        Args:
            report (CompoundingReport): The analysis.
        """
        lines = [
            f"{self.help.title('warnings', warning.kind.value)}"
            f"{' (' + self.format.provider(warning.provider) + ')' if warning.provider else ''}: {warning.detail}"
            for warning in report.warnings
        ]
        self.caveats.setText("<br>".join(lines))
        self.caveats.setToolTip("<br>".join(f"<b>{entry.title}</b>: {entry.text}" for entry in self.help.warnings))

    def _on_outcome(self, generation: int, report: CompoundingReport) -> None:
        """Show an analysis, unless a later run was started.

        Args:
            generation (int): The number of the run.
            report (CompoundingReport): The analysis.
        """
        if sip.isdeleted(self) or generation != self.generation:
            self.logger.debug("Compounding run %d dropped (last run %d).", generation, self.generation)
            return
        self.report = report
        self.stale = False
        self.controls.set_busy(False)
        self._show_coverage(report)
        self._show_caveats(report)
        self.inputs.show(report)
        self.results.show(report)
        fitted = sum(1 for fit in report.hazard if fit.converged)
        self.summary.setText(
            f"{len(report.coverage)} providers, {fitted} foundation hazards fitted, "
            f"{len(report.placebo)} placebo tests, {len(report.transfer)} transfers from AWS."
        )
        self.logger.info("Compounding analysis shown: %d providers.", len(report.coverage))

    def _on_error(self, error: StorageError) -> None:
        """Report a storage error.

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self):
            self.logger.warning("Compounding panel closed before its error was shown: %s", error)
            return
        self.logger.error("The compounding analysis failed: %s", error)
        self.controls.set_busy(False)
        self.summary.setText("The analysis failed.")
        self.caveats.setText(str(error))

    def _write_csv(self, path: Path, report: CompoundingReport) -> None:
        """Write the summary table as CSV.

        Args:
            path (Path): The file.
            report (CompoundingReport): The analysis.
        """
        table = self.results.summary_table
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(table.headers())
            writer.writerows(table.cells())
        self.logger.info("%d summary rows exported to %s.", len(report.summary), path)

    ############################
    # Publicly Exposed Methods #
    ############################

    def cards(self) -> List[CompoundingCardBody]:
        """Get the body of every card, in display order.

        Returns:
            List[CompoundingCardBody]: The card, its body and whether it can be widened in its own window.
        """
        inputs, results = self.inputs, self.results
        return [
            (CompoundingCard.CONTROLS, self, False),
            (CompoundingCard.LAUNCHES, inputs.launches_body, True),
            (CompoundingCard.MARKET, inputs.market_body, True),
            (CompoundingCard.SHARES, inputs.shares_body, True),
            (CompoundingCard.HEAPS, results.heaps_body, True),
            (CompoundingCard.GROWTH, results.growth_body, True),
            (CompoundingCard.ENTRY, results.entry_body, True),
            (CompoundingCard.HAZARD, results.hazard_body, True),
            (CompoundingCard.PLACEBO, results.placebo_body, True),
            (CompoundingCard.LAGS, results.lags_chart, True),
            (CompoundingCard.TRANSFER, results.transfer_body, True),
            (CompoundingCard.SUMMARY, results.summary_table, True),
            (CompoundingCard.FOUNDATIONS, inputs.foundations_body, True),
        ]

    def run(self) -> None:
        """Run the analysis picked."""
        if self.config is None:
            self.logger.warning("No compounding analysis without its configuration.")
            self.summary.setText("The compounding configuration cannot be read: fix conf/analysis/compounding.yaml.")
            return
        query = self.controls.query()
        self.generation += 1
        self.controls.set_busy(True)
        self.summary.setText("Reading the catalogues and the market, then fitting the models...")
        self.logger.debug("Running the compounding analysis (generation %d).", self.generation)
        self.loop.submit(
            partial(self._compute, self.config, query), partial(self._on_outcome, self.generation), self._on_error
        )

    def refresh(self) -> None:
        """Mark the analysis stale (a dataset was written): the next run reads the data again."""
        self.stale = True
        if self.report is not None:
            self.summary.setText("New data was crawled: run the analysis again to include it.")
        self.logger.debug("Compounding analysis marked stale.")

    def export(self, path: Optional[Path] = None) -> Optional[Path]:
        """Save the summary table of the latest analysis as CSV.

        Args:
            path (Optional[Path]): The file, asked for when `None`.

        Returns:
            Optional[Path]: The file written, `None` without an analysis or when the dialog is cancelled.
        """
        if self.report is None:
            self.logger.warning("No compounding analysis to export yet.")
            return None
        if path is None:
            name, _ = QFileDialog.getSaveFileName(self, "Export the summary", "service-compounding.csv", "CSV (*.csv)")
            if not name:
                self.logger.warning("Export of the compounding summary cancelled.")
                return None
            path = Path(name)
        try:
            self._write_csv(path, self.report)
        except OSError as e:
            self.logger.error("The compounding summary cannot be exported to %s: %s", path, e.strerror)
            self.caveats.setText(f"The summary cannot be exported to {path}: {e.strerror}")
            return None
        return path
