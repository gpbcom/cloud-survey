from __future__ import annotations

# Standard Library Imports.
import math
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

# First Party Imports.
from gui.theme import Theme
from models.drivers.enums import MetricValueColumn
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.metrics.provider_metric_value import ProviderMetricValue

type SortKey = Tuple[Union[str, float], str, str]
type Index = Union[QModelIndex, QPersistentModelIndex]


class MetricsModel(QAbstractTableModel):
    """The rows of the table of the stored provider metrics: a measure each, sortable by any column.

    Attributes:
        COLUMNS (ClassVar[Tuple[MetricValueColumn, ...]]): The columns, in their order.
        EPOCH (ClassVar[datetime]): The date a measure without a fetch date sorts as.
        theme (Theme): The application theme (the provider names).
        catalog (MetricCatalog): The definitions of the metrics (their names and units).
        help (DriverHelp): The explanations of the columns (their titles and tooltips).
        values (List[ProviderMetricValue]): The measures shown, in their order.
        sorted_by (Optional[Tuple[int, Qt.SortOrder]]): The column and order of the last sort, kept across loads.
        logger (Logger): The model logger.
    """

    COLUMNS: ClassVar[Tuple[MetricValueColumn, ...]] = tuple(MetricValueColumn)
    EPOCH: ClassVar[datetime] = datetime(1970, 1, 1, tzinfo=UTC)

    def __init__(
        self,
        theme: Theme,
        catalog: MetricCatalog,
        help_: DriverHelp,
        parent: Optional[QObject] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build an empty model.

        Args:
            theme (Theme): The application theme.
            catalog (MetricCatalog): The definitions of the metrics.
            help_ (DriverHelp): The explanations of the columns.
            parent (Optional[QObject]): The Qt parent.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__(parent)
        self.logger = logger if logger else getLogger(__name__)
        self.theme, self.catalog, self.help = theme, catalog, help_
        self.values: List[ProviderMetricValue] = []
        self.sorted_by: Optional[Tuple[int, Qt.SortOrder]] = None

    ############################
    # Internal Helpers Methods #
    ############################

    def _number(self, value: float) -> str:
        """Write a measure without its unit.

        Args:
            value (float): The measure.

        Returns:
            str: Whole numbers with thousands separators, others with 4 significant digits (or 1 decimal from 100).
        """
        if not math.isfinite(value):
            return "-"
        if value.is_integer() and abs(value) < 1e15:
            return f"{value:,.0f}"
        return f"{value:,.1f}" if abs(value) >= 100 else f"{value:.4g}"

    def _unit(self, value: ProviderMetricValue) -> str:
        """Get the unit of the metric of a measure.

        Args:
            value (ProviderMetricValue): The measure.

        Returns:
            str: The unit of the catalogue, empty when it has none.
        """
        definition = self.catalog.get(value.metric)
        return definition.unit if definition is not None else ""

    def _sort_key(self, value: ProviderMetricValue, column: MetricValueColumn) -> SortKey:
        """Get what a measure is sorted by in a column, ties broken by provider and quarter.

        Args:
            value (ProviderMetricValue): The measure.
            column (MetricValueColumn): The column.

        Returns:
            SortKey: The key of the column, then the provider value and the quarter.
        """
        key: Union[str, float]
        match column:
            case MetricValueColumn.PROVIDER:
                key = self.theme.provider_label(value.provider).casefold()
            case MetricValueColumn.PERIOD:
                key = value.period
            case MetricValueColumn.METRIC:
                key = self.catalog.label(value.metric).casefold()
            case MetricValueColumn.VALUE:
                key = value.value if math.isfinite(value.value) else -math.inf
            case MetricValueColumn.SOURCE:
                key = value.source.value
            case MetricValueColumn.FETCHED:
                key = (value.fetched_at or self.EPOCH).timestamp()
            case _:
                key = value.source_url or ""
        return key, value.provider.value, value.period

    ############################
    # Publicly Exposed Methods #
    ############################

    def rowCount(self, parent: Optional[Index] = None) -> int:
        """Count the rows (Qt override).

        Args:
            parent (Optional[Index]): The parent index (none: a flat table).

        Returns:
            int: The number of measures shown.
        """
        return 0 if parent is not None and parent.isValid() else len(self.values)

    def columnCount(self, parent: Optional[Index] = None) -> int:
        """Count the columns (Qt override).

        Args:
            parent (Optional[Index]): The parent index (none: a flat table).

        Returns:
            int: The number of columns.
        """
        return 0 if parent is not None and parent.isValid() else len(self.COLUMNS)

    def title(self, column: MetricValueColumn) -> str:
        """Get the header of a column.

        Args:
            column (MetricValueColumn): The column.

        Returns:
            str: Its title from the explanations, its value capitalized when it has none.
        """
        entry = self.help.value_column(column)
        return entry.title if entry is not None else column.value.capitalize()

    def tooltip(self, column: MetricValueColumn) -> str:
        """Get the tooltip of a column header.

        Args:
            column (MetricValueColumn): The column.

        Returns:
            str: What it shows, from the explanations, empty when it has none.
        """
        entry = self.help.value_column(column)
        return f"<b>{entry.title}</b><br>{entry.summary}" if entry is not None else ""

    def text(self, row: int, column: MetricValueColumn) -> str:
        """Write a cell.

        Args:
            row (int): The row.
            column (MetricValueColumn): The column.

        Returns:
            str: The text shown in the cell.
        """
        value = self.values[row]
        match column:
            case MetricValueColumn.PROVIDER:
                return self.theme.provider_label(value.provider)
            case MetricValueColumn.PERIOD:
                return value.period
            case MetricValueColumn.METRIC:
                return self.catalog.label(value.metric)
            case MetricValueColumn.VALUE:
                unit = self._unit(value)
                return f"{self._number(value.value)} {unit}".strip()
            case MetricValueColumn.SOURCE:
                return value.source.value
            case MetricValueColumn.FETCHED:
                return value.fetched_at.date().isoformat() if value.fetched_at is not None else "-"
            case _:
                return value.source_url or ""

    def data(
        self,
        index: Index,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Optional[Union[str, int]]:
        """Get the text, alignment or tooltip of a cell (Qt override).

        Args:
            index (Index): The cell.
            role (int): What is asked.

        Returns:
            Optional[Union[str, int]]: The text, its alignment for the value, the full address or the definition of
                the metric as tooltip, `None` otherwise.
        """
        if not index.isValid() or index.row() >= len(self.values):
            return None
        column = self.COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return self.text(index.row(), column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column is MetricValueColumn.VALUE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            value = self.values[index.row()]
            if column is MetricValueColumn.METRIC:
                definition = self.catalog.get(value.metric)
                return definition.description if definition is not None and definition.description else None
            if column is MetricValueColumn.URL and value.source_url:
                return f"{value.source_url}\nDouble-click to open it."
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[str]:
        """Get the title or tooltip of a column header (Qt override).

        Args:
            section (int): The column.
            orientation (Qt.Orientation): Horizontal for the column headers.
            role (int): What is asked.

        Returns:
            Optional[str]: The title, or the explanation of the column, `None` otherwise.
        """
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(self.COLUMNS):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.title(self.COLUMNS[section])
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip(self.COLUMNS[section]) or None
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort the rows by a column (Qt override, called when a header is clicked).

        Args:
            column (int): The column.
            order (Qt.SortOrder): Ascending or descending.
        """
        if not 0 <= column < len(self.COLUMNS):
            self.logger.debug("Provider metrics left unsorted (column %d).", column)
            return
        self.sorted_by = (column, order)
        self.layoutAboutToBeChanged.emit()
        self.values.sort(
            key=lambda value: self._sort_key(value, self.COLUMNS[column]),
            reverse=order == Qt.SortOrder.DescendingOrder,
        )
        self.layoutChanged.emit()
        self.logger.debug("%d provider metrics sorted by %s.", len(self.values), self.COLUMNS[column].value)

    def set_values(self, values: List[ProviderMetricValue]) -> None:
        """Show other measures, in the order of the last sort.

        Args:
            values (List[ProviderMetricValue]): The measures.
        """
        self.beginResetModel()
        self.values = list(values)
        self.endResetModel()
        if self.sorted_by is not None:
            self.sort(*self.sorted_by)
        self.logger.debug("Provider metrics table holds %d measures.", len(self.values))

    def value(self, row: int) -> Optional[ProviderMetricValue]:
        """Get the measure of a row.

        Args:
            row (int): The row.

        Returns:
            Optional[ProviderMetricValue]: Its measure, `None` out of range.
        """
        return self.values[row] if 0 <= row < len(self.values) else None
