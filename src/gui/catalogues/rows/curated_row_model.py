from __future__ import annotations

# Standard Library Imports.
import json
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Union

# Third Party Imports.
from pydantic import JsonValue
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PyQt6.QtGui import QColor, QFont

# First Party Imports.
from gui.theme import Theme
from models.curated.enums import IdentifierStatus

ModelIndex = Union[QModelIndex, QPersistentModelIndex]
CellData = Optional[Union[str, QColor, QFont]]
type CuratedRowValues = Dict[str, JsonValue]


class CuratedRowModel(QAbstractTableModel):
    """The rows of a section of a curated catalogue, filtered: one line per entry.

    Attributes:
        KEY, POSITION, CONTENT, STATUS, ORIGIN, NOTE (ClassVar[int]): The columns.
        HEADERS (ClassVar[List[str]]): The column headers.
        KEYS (ClassVar[List[str]]): The fields naming a row, in the order shown.
        PREVIEW (ClassVar[int]): The characters of the content shown in its cell (the tooltip shows it whole).
        theme (Theme): The application theme.
        rows (List[CuratedRowValues]): Every row of the section, as stored (JSON).
        shown (List[int]): The indexes of the rows matching the filter.
        logger (Logger): The model logger.

    Notes:
        A row is shown as stored (its JSON dump): the content is its `body` (the entry as its catalogue writes it),
        or the identifier and its evidence. The rows a person changed are bold, the candidates of a resolver italic,
        the rejected ones muted.
    """

    KEY: ClassVar[int] = 0
    POSITION: ClassVar[int] = 1
    CONTENT: ClassVar[int] = 2
    STATUS: ClassVar[int] = 3
    ORIGIN: ClassVar[int] = 4
    NOTE: ClassVar[int] = 5
    HEADERS: ClassVar[List[str]] = ["Key", "Rank", "Content", "Status", "Origin", "Note"]
    KEYS: ClassVar[List[str]] = ["company", "crawler", "kind", "fiscal_year", "key", "name", "value"]
    PREVIEW: ClassVar[int] = 160

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty model.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.rows: List[CuratedRowValues] = []
        self.shown: List[int] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _key(self, row: CuratedRowValues) -> str:
        """Get the text naming a row.

        Args:
            row (CuratedRowValues): The row.

        Returns:
            str: Its key fields, joined.
        """
        return " · ".join(str(row[name]) for name in self.KEYS if row.get(name) is not None)

    def _content(self, row: CuratedRowValues, indent: Optional[int] = None) -> str:
        """Get the content of a row.

        Args:
            row (CuratedRowValues): The row.
            indent (Optional[int]): The indentation of the JSON, `None` for one line.

        Returns:
            str: Its body as JSON, or the evidence of an identifier.
        """
        if "body" in row:
            return json.dumps(row["body"], ensure_ascii=False, indent=indent)
        return str(row.get("evidence_url") or "")

    def _text(self, row: CuratedRowValues, column: int) -> str:
        """Get the text of a cell.

        Args:
            row (CuratedRowValues): The row.
            column (int): The column.

        Returns:
            str: The cell text.
        """
        match column:
            case self.KEY:
                return self._key(row)
            case self.POSITION:
                return str(row.get("position", ""))
            case self.CONTENT:
                content = self._content(row)
                return content if len(content) <= self.PREVIEW else content[: self.PREVIEW] + "…"
            case self.STATUS:
                return str(row.get("status") or row.get("check_status") or "")
            case self.ORIGIN:
                return f"{row.get('origin') or 'seed'}{', edited' if row.get('edited') else ''}"
            case _:
                return str(row.get("note") or "").split("\n", 1)[0]

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_rows(self, rows: Sequence[CuratedRowValues], text: str = "") -> None:
        """Show the rows of a section matching a filter.

        Args:
            rows (Sequence[CuratedRowValues]): Every row of the section.
            text (str): Only the rows whose key, content or note contains this text, case-insensitive.
        """
        wanted = text.strip().casefold()
        self.beginResetModel()
        self.rows = list(rows)
        self.shown = [
            index
            for index, row in enumerate(self.rows)
            if not wanted
            or wanted in self._key(row).casefold()
            or wanted in self._content(row).casefold()
            or wanted in str(row.get("note") or "").casefold()
        ]
        self.endResetModel()
        self.logger.debug("%d of %d curated rows shown.", len(self.shown), len(self.rows))

    def describe(self, row: CuratedRowValues) -> str:
        """Name a row, for a confirmation or a status line.

        Args:
            row (CuratedRowValues): The row.

        Returns:
            str: Its key fields, joined.
        """
        return self._key(row)

    def index_of(self, row: int) -> Optional[int]:
        """Get the index in the section of a shown row.

        Args:
            row (int): The shown row.

        Returns:
            Optional[int]: Its index among every row of the section, `None` outside of the rows.
        """
        return self.shown[row] if 0 <= row < len(self.shown) else None

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of shown rows (Qt override).

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
            CellData: The text, the tooltip (the whole content or note, what a figures check found), the bold font of an edited row, the italic
                font of a candidate, the muted colour of a rejected identifier.
        """
        position = self.index_of(index.row()) if index.isValid() else None
        if position is None:
            return None
        row = self.rows[position]
        match role:
            case Qt.ItemDataRole.DisplayRole:
                return self._text(row, index.column())
            case Qt.ItemDataRole.ToolTipRole if index.column() == self.CONTENT:
                return self._content(row, indent=2)
            case Qt.ItemDataRole.ToolTipRole if index.column() == self.NOTE:
                return str(row.get("note") or "")
            case Qt.ItemDataRole.ToolTipRole if index.column() == self.STATUS:
                return str(row.get("check_note") or "")
            case Qt.ItemDataRole.ForegroundRole if row.get("status") == IdentifierStatus.REJECTED.value:
                return QColor(self.theme.TEXT_MUTED)
            case Qt.ItemDataRole.FontRole if row.get("edited") or row.get("status") == IdentifierStatus.CANDIDATE.value:
                font = QFont()
                font.setBold(bool(row.get("edited")))
                font.setItalic(row.get("status") == IdentifierStatus.CANDIDATE.value)
                return font
            case _:
                return None
