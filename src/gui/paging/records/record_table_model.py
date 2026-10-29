from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import BaseModel
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, pyqtSignal

# First Party Imports.
from gui.paging.page.page_cache import PageCache
from gui.paging.records.record_layout import RecordLayout
from gui.storage_bridge.storage_loop import StorageLoop
from models.storage.records.record_query import RecordQuery
from storage.exception import StorageError

type ModelIndex = Union[QModelIndex, QPersistentModelIndex]
type CellValue = Optional[Union[str, int]]


class RecordTableModel(QAbstractTableModel):
    """A table of stored research records read page by page: filtered, ordered and counted by the database.

    Attributes:
        PAGE_SIZE (ClassVar[int]): The number of rows read at a time.
        MAX_PAGES (ClassVar[int]): The largest number of pages kept in memory.
        loaded (pyqtSignal): Emitted with the number of matching records each time it is counted.
        failed (pyqtSignal): Emitted with the reason when a page cannot be read.
        loop (StorageLoop): The storage thread of the GUI.
        layout (RecordLayout): The columns of the table and how its records are read.
        query (RecordQuery): The companies, the text and the order of the table.
        total (int): The number of rows: the records matching.
        cache (PageCache[BaseModel]): The pages kept in memory.
        generation (int): A number changing with the query and at each refresh: the pages read before are
            ignored.
        logger (Logger): The model logger.

    Notes:
        The table holds `total` rows but keeps `MAX_PAGES` pages of them at most, the visible ones: a missing row is
        read (with its page) when the view shows it, `data` returning nothing meanwhile (as the paged item tables
        do). The row accessors run for each painted cell: they do not log, the page reads do.
    """

    PAGE_SIZE: ClassVar[int] = 200
    MAX_PAGES: ClassVar[int] = 8

    loaded = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, loop: StorageLoop, layout: RecordLayout, logger: Optional[Logger] = None) -> None:
        """Initialize an empty table, read when its query is set.

        Args:
            loop (StorageLoop): The storage thread of the GUI.
            layout (RecordLayout): The columns of the table and how its records are read.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.loop = loop
        self.layout = layout
        self.query = RecordQuery(limit=self.PAGE_SIZE)
        self.total = 0
        self.cache = PageCache[BaseModel](self.PAGE_SIZE, self.MAX_PAGES, self.logger)
        self.generation = 0
        self.logger.debug("Record table created: %d columns.", len(layout.headers))

    ############################
    # Internal Helpers Methods #
    ############################

    def _resize(self, total: int) -> None:
        """Change the number of rows, telling the views.

        Args:
            total (int): The number of matching records.
        """
        self.logger.debug("Record table resized from %d to %d rows.", self.total, total)
        if total > self.total:
            self.beginInsertRows(QModelIndex(), self.total, total - 1)
            self.total = total
            self.endInsertRows()
        elif total < self.total:
            self.beginRemoveRows(QModelIndex(), total, self.total - 1)
            self.total = total
            self.endRemoveRows()

    def _on_page(self, page: Tuple[List[BaseModel], Optional[int]], generation: int, number: int) -> None:
        """Keep a page just read, and show its rows (GUI thread).

        Args:
            page (Tuple[List[BaseModel], Optional[int]]): The records, then their count when it was asked.
            generation (int): The generation of the request: an outdated page is ignored.
            number (int): The page number.
        """
        records, total = page
        self.logger.debug("Record page %d read: %d rows (generation %d).", number, len(records), generation)
        if generation != self.generation:
            return
        if total is not None:
            self._resize(total)
        self.cache.store(number, records)
        first = number * self.PAGE_SIZE
        last = min(first + len(records), self.total) - 1
        if last >= first:
            self.dataChanged.emit(self.index(first, 0), self.index(last, len(self.layout.headers) - 1))
        if total is not None:
            self.loaded.emit(self.total)

    def _on_error(self, error: StorageError, generation: int, number: int) -> None:
        """Report a page which cannot be read (GUI thread).

        Args:
            error (StorageError): The error.
            generation (int): The generation of the request.
            number (int): The page number.
        """
        if generation != self.generation:
            return
        self.cache.pending.discard(number)
        self.logger.warning("Record page %d cannot be read: %s", number, error)
        self.failed.emit(str(error))

    def _request(self, number: int, counted: bool) -> None:
        """Read a page in the storage thread.

        Args:
            number (int): The page number.
            counted (bool): Whether the matching records are counted too (the first page).
        """
        self.logger.debug("Reading record page %d (counted: %s, generation %d).", number, counted, self.generation)
        generation = self.generation
        query = self.query.model_copy(
            update={"offset": number * self.PAGE_SIZE, "limit": self.PAGE_SIZE, "with_total": counted}
        )
        reader = self.layout.reader
        self.cache.pending.add(number)
        self.loop.submit(
            lambda storage: reader(storage, query),
            lambda page: self._on_page(page, generation, number),
            lambda error: self._on_error(error, generation, number),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_query(self, query: RecordQuery) -> None:
        """Show other records, or in another order: the table is read again from its start.

        Args:
            query (RecordQuery): The companies, the text and the order (its bounds are managed by the table).
        """
        self.logger.info("Record table query changed: %s.", query.model_dump(mode="json", exclude_defaults=True))
        self.generation += 1
        self.query = query
        self.beginResetModel()
        self.cache.clear()
        self.total = 0
        self.endResetModel()
        self._request(0, counted=True)

    def refresh(self) -> None:
        """Read the table again (records were written), keeping the rows shown until their page is read."""
        self.logger.debug("Record table refreshed: %d pages kept until read again.", len(self.cache.pages))
        self.generation += 1
        self.cache.invalidate()
        self._request(0, counted=True)

    def record(self, number: int) -> Optional[BaseModel]:
        """Get a record, reading its page when it is not kept or stale.

        Args:
            number (int): The row number.

        Returns:
            Optional[BaseModel]: The record, `None` while its page is read.
        """
        if not 0 <= number < self.total:
            return None
        if self.cache.needs(number):
            self._request(self.cache.page_of(number), counted=False)
        return self.cache.get(number)

    def record_at(self, index: ModelIndex) -> Optional[BaseModel]:
        """Get the record of a table index.

        Args:
            index (ModelIndex): The table index.

        Returns:
            Optional[BaseModel]: The record, `None` for an invalid index or while its page is read.
        """
        return self.record(index.row()) if index.isValid() else None

    def link_at(self, index: ModelIndex) -> Optional[str]:
        """Get the page the record of a table index is opened at.

        Args:
            index (ModelIndex): The table index.

        Returns:
            Optional[str]: The page, `None` when the record has none or is being read.
        """
        record = self.record_at(index)
        return self.layout.link(record) if record is not None else None

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of rows (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, rows only exist at the top level.

        Returns:
            int: The number of matching records.
        """
        return 0 if parent is not None and parent.isValid() else self.total

    def columnCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of columns (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index.

        Returns:
            int: The number of columns of the layout.
        """
        return 0 if parent is not None and parent.isValid() else len(self.layout.headers)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> CellValue:
        """Get the text, the alignment or the tooltip of a cell (Qt override).

        Args:
            index (ModelIndex): The cell.
            role (int): What is asked.

        Returns:
            CellValue: The value, `None` while the row is read or for another role.
        """
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in self.layout.numeric:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        record = self.record_at(index)
        if record is None:
            return "…" if role == Qt.ItemDataRole.DisplayRole and index.column() == 0 else None
        cells = self.layout.cells(record)
        text = cells[index.column()] if index.column() < len(cells) else ""
        if role == Qt.ItemDataRole.ToolTipRole:
            link = self.layout.link(record)
            return f"{text}\n{link}" if link else (text or None)
        return text

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> CellValue:
        """Get the title or the tooltip of a column (Qt override).

        Args:
            section (int): The column, or the row for the vertical header.
            orientation (Qt.Orientation): Which header.
            role (int): What is asked.

        Returns:
            CellValue: The value, `None` for the vertical header or another role.
        """
        if orientation != Qt.Orientation.Horizontal or not 0 <= section < len(self.layout.headers):
            return None
        title, tooltip = self.layout.headers[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return title
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Order the records by a column, in the database (Qt override): the other columns are not sortable.

        Args:
            column (int): The column.
            order (Qt.SortOrder): The order.
        """
        sort = self.layout.sorts.get(column)
        if sort is None:
            self.logger.debug("Record column %d cannot be sorted.", column)
            return
        descending = order == Qt.SortOrder.DescendingOrder
        if (sort, descending) == (self.query.sort, self.query.descending):
            return
        self.set_query(self.query.model_copy(update={"sort": sort, "descending": descending}))
