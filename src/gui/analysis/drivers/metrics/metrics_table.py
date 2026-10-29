from __future__ import annotations

# Standard Library Imports.
import csv
from collections import Counter
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import QModelIndex, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.analysis.drivers.metrics.metrics_model import MetricsModel
from gui.selection.pickers.provider_picker import ProviderPicker
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, MetricValueColumn
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue

type Choice = Tuple[str, str, str]


class MetricsTable(QWidget):
    """Every stored provider metric, with its source: filters, a sortable table, a CSV export.

    Attributes:
        TABLE_HEIGHT (ClassVar[int]): The height of the table, in pixels (it scrolls beyond).
        URL_WIDTH (ClassVar[int]): The widest the address column gets before it is elided, in pixels.
        CSV_HEADER (ClassVar[Tuple[str, ...]]): The columns of the CSV export (keys and display names both).
        theme (Theme): The application theme.
        catalog (MetricCatalog): The definitions of the metrics (names, units, descriptions).
        values (List[ProviderMetricValue]): Every measure loaded, the filters left aside.
        provider_picker (ProviderPicker): Keeps the measures of some providers only.
        metric_box (CompactCombo): Keeps one metric only.
        source_box (CompactCombo): Keeps one source only.
        search (QLineEdit): Keeps the measures whose provider, quarter, metric, source or address holds a text.
        count_label (QLabel): The number of measures shown.
        export_button (QPushButton): Saves the measures shown as CSV.
        message (QLabel): The last error (an export that failed, a read that failed), hidden otherwise.
        model (MetricsModel): The rows shown.
        view (QTableView): The table.
        logger (Logger): The table logger.

    Notes:
        The values are read by the Rise drivers panel (after each run and on refresh) and given to `load`. The
        filters are applied in memory: a few tens of thousands of measures at most.
    """

    TABLE_HEIGHT: ClassVar[int] = 380
    URL_WIDTH: ClassVar[int] = 360
    CSV_HEADER: ClassVar[Tuple[str, ...]] = (
        "provider",
        "provider_name",
        "period",
        "metric",
        "metric_name",
        "value",
        "unit",
        "source",
        "fetched_at",
        "source_url",
    )

    def __init__(
        self, theme: Theme, catalog: MetricCatalog, help_: DriverHelp, logger: Optional[Logger] = None
    ) -> None:
        """Build an empty table.

        Args:
            theme (Theme): The application theme.
            catalog (MetricCatalog): The definitions of the metrics.
            help_ (DriverHelp): The explanations of the columns.
            logger (Optional[Logger]): The table logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.theme, self.catalog = theme, catalog
        self.values: List[ProviderMetricValue] = []
        self.provider_picker = ProviderPicker(theme, list(CloudProvider), self.logger)
        self.provider_picker.setToolTip("Show only the measures of some providers (several at once)")
        self.metric_box = CompactCombo(logger=self.logger)
        self.metric_box.setToolTip("Show only the measures of one metric (the number of measures in brackets)")
        self.source_box = CompactCombo(logger=self.logger)
        self.source_box.setToolTip(
            "Show only the measures of one source: derived from the crawls, read from a publication, or typed in"
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter the measures…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Show only the measures whose provider, quarter, metric, source or address holds this")
        self.count_label = QLabel("0 values")
        self.count_label.setObjectName("muted")
        self.count_label.setToolTip("The number of measures shown, out of every measure stored")
        self.export_button = QPushButton("Export CSV")
        self.export_button.setToolTip("Save the measures shown, filtered and sorted as in the table, as CSV")
        self.export_button.setEnabled(False)
        self.message = QLabel()
        self.message.setObjectName("warning")
        self.message.setWordWrap(True)
        self.message.hide()
        self.model = MetricsModel(theme, catalog, help_, self, self.logger)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setSortingEnabled(True)
        self.view.verticalHeader().setVisible(False)  # type: ignore[union-attr]
        header = self.view.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
        self.view.setFixedHeight(self.TABLE_HEIGHT)
        self.view.setToolTip("Double-click a row to open the page or document its measure was read from")
        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self.provider_picker)
        filters.addWidget(self.metric_box)
        filters.addWidget(self.source_box)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.count_label)
        filters.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(filters)
        layout.addWidget(self.message)
        layout.addWidget(self.view)
        self._fill_box(self.metric_box, "All metrics", [])
        self._fill_box(self.source_box, "All sources", [])
        self.provider_picker.changed.connect(self._apply)
        self.metric_box.currentIndexChanged.connect(self._apply)
        self.source_box.currentIndexChanged.connect(self._apply)
        self.search.textChanged.connect(self._apply)
        self.export_button.clicked.connect(lambda: self.export())
        self.view.doubleClicked.connect(self._open)
        self.logger.debug("Provider metrics table built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _fill_box(self, box: CompactCombo, everything: str, choices: Sequence[Choice]) -> None:
        """Offer choices in a filter, keeping the one picked when it is still offered, without telling.

        Args:
            box (CompactCombo): The filter.
            everything (str): The first entry, which filters nothing.
            choices (Sequence[Choice]): The entries: value, text and tooltip.
        """
        picked = box.currentData()
        box.blockSignals(True)
        box.clear()
        box.addItem(everything, "")
        for value, text, tooltip in choices:
            box.addItem(text, value)
            if tooltip:
                box.setItemData(box.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
        position = box.findData(picked) if picked else 0
        box.setCurrentIndex(max(position, 0))
        box.blockSignals(False)
        self.logger.debug("Filter %r offers %d choices.", everything, len(choices))

    def _refresh_choices(self) -> None:
        """Offer in the filters the providers, metrics and sources of the measures loaded, with their counts."""
        providers = Counter(value.provider for value in self.values)
        metrics = Counter(value.metric for value in self.values)
        sources = Counter(value.source for value in self.values)
        self.provider_picker.show_only(providers.keys() if providers else list(CloudProvider))
        self.provider_picker.set_counts(dict(providers))
        ordered = [definition.metric for definition in self.catalog.definitions if definition.metric in metrics]
        ordered += sorted((metric for metric in metrics if metric not in ordered), key=lambda metric: metric.value)
        metric_choices: List[Choice] = []
        for metric in ordered:
            definition = self.catalog.get(metric)
            metric_choices.append(
                (
                    metric.value,
                    f"{self.catalog.label(metric)} ({metrics[metric]:,})",
                    definition.description if definition is not None else "",
                )
            )
        self._fill_box(self.metric_box, "All metrics", metric_choices)
        source_choices: List[Choice] = [
            (source.value, f"{source.value} ({sources[source]:,})", "") for source in MetricSource if source in sources
        ]
        self._fill_box(self.source_box, "All sources", source_choices)

    def _matches(self, value: ProviderMetricValue, text: str) -> bool:
        """Tell whether a measure holds a text (case ignored).

        Args:
            value (ProviderMetricValue): The measure.
            text (str): The text, case-folded.

        Returns:
            bool: Whether its provider, quarter, metric (name or key), source or address holds it.
        """
        fields = (
            self.theme.provider_label(value.provider),
            value.provider.value,
            value.period,
            self.catalog.label(value.metric),
            value.metric.value,
            value.source.value,
            value.source_url or "",
        )
        return any(text in field.casefold() for field in fields)

    def _apply(self) -> None:
        """Show the measures the filters keep, in the order of the last sort."""
        providers = self.provider_picker.picked()
        kept_providers = set(providers) if providers is not None else None
        metric = str(self.metric_box.currentData() or "")
        source = str(self.source_box.currentData() or "")
        text = self.search.text().strip().casefold()
        shown = [
            value
            for value in self.values
            if (kept_providers is None or value.provider in kept_providers)
            and (not metric or value.metric.value == metric)
            and (not source or value.source.value == source)
            and (not text or self._matches(value, text))
        ]
        self.model.set_values(shown)
        total = len(self.values)
        self.count_label.setText(
            f"{len(shown):,} values" if len(shown) == total else f"{len(shown):,} of {total:,} values"
        )
        self.export_button.setEnabled(bool(shown))
        self.view.resizeColumnsToContents()
        url_column = MetricsModel.COLUMNS.index(MetricValueColumn.URL)
        self.view.setColumnWidth(url_column, min(self.view.columnWidth(url_column), self.URL_WIDTH))
        self.logger.debug("Provider metrics table shows %d of %d measures.", len(shown), total)

    def _open(self, index: QModelIndex) -> None:
        """Open the page or document of a row in the browser.

        Args:
            index (QModelIndex): The cell double-clicked.
        """
        value = self.model.value(index.row())
        address = value.source_url if value is not None and value.source_url else ""
        if not address.startswith("http"):
            self.logger.info("No page to open for row %d of the provider metrics.", index.row())
            return
        if not QDesktopServices.openUrl(QUrl(address)):
            self.logger.warning("The page %s cannot be opened.", address)
            return
        self.logger.debug("Page %s opened.", address)

    def _write_csv(self, path: Path) -> int:
        """Write the measures shown as CSV, in their order.

        Args:
            path (Path): The file.

        Returns:
            int: The number of measures written.
        """
        rows = self.model.values
        self.logger.debug("Writing %d provider metrics to %s.", len(rows), path)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(self.CSV_HEADER)
            for value in rows:
                definition = self.catalog.get(value.metric)
                writer.writerow(
                    [
                        value.provider.value,
                        self.theme.provider_label(value.provider),
                        value.period,
                        value.metric.value,
                        self.catalog.label(value.metric),
                        repr(value.value),
                        definition.unit if definition is not None else "",
                        value.source.value,
                        value.fetched_at.isoformat() if value.fetched_at is not None else "",
                        value.source_url or "",
                    ]
                )
        self.logger.info("%d provider metrics exported to %s.", len(rows), path)
        return len(rows)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self, values: List[ProviderMetricValue]) -> None:
        """Show other measures, keeping the filters picked when they still apply.

        Args:
            values (List[ProviderMetricValue]): Every stored measure.
        """
        self.values = list(values)
        self.message.hide()
        self._refresh_choices()
        self._apply()
        if not values:
            self.logger.warning("No provider metric stored: the provider metrics table is empty.")
        self.logger.info("Provider metrics table loaded: %d measures.", len(values))

    def show_error(self, text: str) -> None:
        """Show an error above the table (e.g. the measures cannot be read).

        Args:
            text (str): The error.
        """
        self.message.setText(text)
        self.message.show()
        self.logger.warning("Provider metrics table error shown: %s", text)

    def export(self, path: Optional[Path] = None) -> Optional[Path]:
        """Save the measures shown as CSV.

        Args:
            path (Optional[Path]): The file, asked for when `None`.

        Returns:
            Optional[Path]: The file written, `None` when no measure is shown, the dialog is cancelled or the file
                cannot be written.
        """
        if not self.model.values:
            self.logger.warning("No provider metric shown to export.")
            return None
        if path is None:
            name, _ = QFileDialog.getSaveFileName(
                self, "Export the provider metrics", "provider-metrics.csv", "CSV (*.csv)"
            )
            if not name:
                self.logger.warning("Export of the provider metrics cancelled.")
                return None
            path = Path(name)
        try:
            self._write_csv(path)
        except OSError as e:
            self.logger.error("The provider metrics cannot be exported to %s: %s", path, e.strerror)
            self.show_error(f"The provider metrics cannot be exported to {path}: {e.strerror}")
            return None
        self.message.hide()
        return path
