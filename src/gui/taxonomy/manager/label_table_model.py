from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PyQt6.QtGui import QColor, QFont

# First Party Imports.
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.taxonomy.enums import LabelStatus, Language
from models.taxonomy.labels.label_details import LabelDetails

ModelIndex = Union[QModelIndex, QPersistentModelIndex]
CellData = Optional[Union[str, int, QColor, QFont]]


class LabelTableModel(QAbstractTableModel):
    """The source labels of the Categories manager, filtered.

    Attributes:
        ORIGINAL, LANGUAGE, ENGLISH, STATUS, SOURCE, CANONICAL, CATEGORIES, PROVIDERS, ITEMS (ClassVar[int]): The
            columns.
        HEADERS (ClassVar[List[str]]): The column headers.
        theme (Theme): The application theme.
        cache (TaxonomyCache): The names of the taxonomy nodes.
        labels (List[LabelDetails]): Every label read.
        by_id (Dict[int, LabelDetails]): The labels, by identifier.
        shown (List[LabelDetails]): The labels matching the filters, the most used first.
        logger (Logger): The model logger.

    Notes:
        A label merged into another one shows the name of that label in the "Merged into" column. The excluded links
        (removed by a person) are listed with a leading dash.
    """

    ORIGINAL: ClassVar[int] = 0
    LANGUAGE: ClassVar[int] = 1
    ENGLISH: ClassVar[int] = 2
    STATUS: ClassVar[int] = 3
    SOURCE: ClassVar[int] = 4
    CANONICAL: ClassVar[int] = 5
    CATEGORIES: ClassVar[int] = 6
    PROVIDERS: ClassVar[int] = 7
    ITEMS: ClassVar[int] = 8
    HEADERS: ClassVar[List[str]] = [
        "Original",
        "Language",
        "English",
        "Status",
        "Named by",
        "Merged into",
        "Categories",
        "Providers",
        "Items",
    ]

    def __init__(self, theme: Theme, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build an empty model.

        Args:
            theme (Theme): The application theme.
            cache (TaxonomyCache): The names of the taxonomy nodes.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.theme = theme
        self.cache = cache
        self.logger = logger if logger else getLogger(__name__)
        self.labels: List[LabelDetails] = []
        self.by_id: Dict[int, LabelDetails] = {}
        self.shown: List[LabelDetails] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, label: LabelDetails, column: int) -> str:
        """Get the text of a cell.

        Args:
            label (LabelDetails): The label of the row.
            column (int): The column.

        Returns:
            str: The cell text.
        """
        match column:
            case self.ORIGINAL:
                return label.text
            case self.LANGUAGE:
                return TaxonomyCache.LANGUAGE_NAMES.get(label.language.value, label.language.value)
            case self.ENGLISH:
                return label.name_en or ""
            case self.STATUS:
                return label.status.value.capitalize()
            case self.SOURCE:
                return label.name_source.value if label.name_source else ""
            case self.CANONICAL:
                canonical = self.by_id.get(label.canonical_id) if label.canonical_id else None
                return canonical.display_name() if canonical is not None else ""
            case self.CATEGORIES:
                links = [self.cache.name(slug) for slug in label.links]
                return ", ".join([*links, *(f"-{self.cache.name(slug)}" for slug in label.excluded)])
            case self.PROVIDERS:
                return f"{len(label.providers)}" if label.providers else ""
            case _:
                return f"{label.items:,}"

    def _tooltip(self, label: LabelDetails, column: int) -> str:
        """Get the tooltip of a cell.

        Args:
            label (LabelDetails): The label of the row.
            column (int): The column.

        Returns:
            str: The paths of the linked nodes, the datasets the label was seen in, else the text.
        """
        match column:
            case self.CATEGORIES:
                lines = [self.cache.path(slug) for slug in label.links]
                return "\n".join([*lines, *(f"Removed: {self.cache.path(slug)}" for slug in label.excluded)])
            case self.PROVIDERS:
                return "\n".join(label.providers)
            case _:
                return self._text(label, column)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_labels(self, labels: List[LabelDetails]) -> None:
        """Show labels read again, keeping the filters.

        Args:
            labels (List[LabelDetails]): Every stored label.
        """
        self.labels = list(labels)
        self.by_id = {label.id: label for label in labels}
        self.logger.debug("%d labels set in the manager table.", len(labels))

    def set_filter(
        self,
        status: Optional[LabelStatus] = None,
        language: Optional[Language] = None,
        provider: Optional[str] = None,
        text: str = "",
    ) -> None:
        """Show the labels matching filters, the most used first.

        Args:
            status (Optional[LabelStatus]): Only the labels of this status.
            language (Optional[Language]): Only the labels of this language.
            provider (Optional[str]): Only the labels seen in this dataset (`<kind>:<provider>`) or of this provider.
            text (str): Only the labels whose text or English name contains this text, case-insensitive.
        """
        wanted = text.strip().casefold()
        self.beginResetModel()
        self.shown = sorted(
            (
                label
                for label in self.labels
                if (status is None or label.status is status)
                and (language is None or label.language is language)
                and (provider is None or any(seen.endswith(provider) or seen == provider for seen in label.providers))
                and (not wanted or wanted in label.text.casefold() or wanted in (label.name_en or "").casefold())
            ),
            key=lambda label: (-label.items, label.display_name().casefold()),
        )
        self.endResetModel()
        self.logger.debug("%d of %d labels shown.", len(self.shown), len(self.labels))

    def label(self, row: int) -> Optional[LabelDetails]:
        """Get the label of a row.

        Args:
            row (int): The row.

        Returns:
            Optional[LabelDetails]: The label, `None` outside of the rows.
        """
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of shown labels (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, rows only exist at the top level.

        Returns:
            int: The number of rows.
        """
        return 0 if parent is not None and parent.isValid() else len(self.shown)

    def columnCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of columns (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, columns only exist at the top level.

        Returns:
            int: The number of columns.
        """
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Optional[str]:
        """Get a column header (Qt override).

        Args:
            section (int): The column.
            orientation (Qt.Orientation): Only the horizontal headers have a text.
            role (int): Only the display role has a text.

        Returns:
            Optional[str]: The header, `None` otherwise.
        """
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> CellData:
        """Get a cell (Qt override).

        Args:
            index (ModelIndex): The cell.
            role (int): The role.

        Returns:
            CellData: The text, the tooltip, the muted colour of the noise, the italic font of the pending labels.
        """
        label = self.label(index.row()) if index.isValid() else None
        if label is None:
            return None
        match role:
            case Qt.ItemDataRole.DisplayRole:
                return self._text(label, index.column())
            case Qt.ItemDataRole.ToolTipRole:
                return self._tooltip(label, index.column())
            case Qt.ItemDataRole.ForegroundRole if label.status is LabelStatus.NOISE:
                return QColor(self.theme.TEXT_MUTED)
            case Qt.ItemDataRole.FontRole if label.status is LabelStatus.PENDING:
                font = QFont()
                font.setItalic(True)
                return font
            case _:
                return None
