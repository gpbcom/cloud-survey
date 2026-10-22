from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Dict, List, Optional, Union

# Third Party Imports.
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, pyqtSignal

# First Party Imports.
from gui.paging.identified_row import IdentifiedRow
from gui.paging.page.page_cache import PageCache
from gui.storage_bridge.storage_loop import StorageLoop
from models.cloud.dated_item import DatedItem
from models.storage.enums import ItemSort
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.stored_item import StoredItem
from storage.exception import StorageError
from storage.storage import Storage

ModelIndex = Union[QModelIndex, QPersistentModelIndex]


class PagedTableModel[T: DatedItem, R: IdentifiedRow](QAbstractTableModel):
    """A table of stored items read page by page from the storage: filtered, ordered and counted by the server.

    Attributes:
        PAGE_SIZE (ClassVar[int]): The number of rows read at a time.
        MAX_PAGES (ClassVar[int]): The largest number of pages kept in memory.
        SORTS (ClassVar[Dict[int, ItemSort]]): The order of each sortable column (the other columns are not
            sortable).
        loaded (pyqtSignal): Emitted with the number of matching items each time it is counted.
        failed (pyqtSignal): Emitted with the reason when a page cannot be read.
        loop (StorageLoop): The storage thread of the GUI.
        lister (Callable[[Storage, ItemQuery], Awaitable[Page[T]]]): Reads a page of items from the storage.
        builder (Callable[[StoredItem[T]], R]): Builds the row of a stored item.
        query (ItemQuery): The filters and order of the table.
        total (int): The number of rows: the items matching the filters.
        cache (PageCache[R]): The pages kept in memory.
        generation (int): A number changing with the query and at each refresh: the pages read before are
            ignored.
        logger (Logger): The model logger.

    Notes:
        The table holds `total` rows but keeps `MAX_PAGES` pages of them at most, the visible ones: a missing row is
        read (with its page) when the view shows it, `data` returning nothing meanwhile. A refresh (the items were
        written) keeps the rows shown until their page is read again, so the table does not flicker during a crawl.
        The row accessors (`row`, `row_at`, `rowCount`, and the `data` of the tables) run for each painted cell:
        they do not log, the page reads do.
    """

    PAGE_SIZE: ClassVar[int] = 200
    MAX_PAGES: ClassVar[int] = 8
    SORTS: ClassVar[Dict[int, ItemSort]] = {}

    loaded = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        loop: StorageLoop,
        lister: Callable[[Storage, ItemQuery], Awaitable[Page[T]]],
        builder: Callable[[StoredItem[T]], R],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize an empty table, read when its query is set.

        Args:
            loop (StorageLoop): The storage thread of the GUI.
            lister (Callable[[Storage, ItemQuery], Awaitable[Page[T]]]): Reads a page of items from the storage.
            builder (Callable[[StoredItem[T]], R]): Builds the row of a stored item.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.loop = loop
        self.lister = lister
        self.builder = builder
        self.query = ItemQuery(limit=self.PAGE_SIZE)
        self.total = 0
        self.logger = logger if logger else getLogger(__name__)
        self.cache = PageCache[R](self.PAGE_SIZE, self.MAX_PAGES, self.logger)
        self.generation = 0
        self.logger.debug(
            "Paged table created: pages of %d rows, at most %d pages kept.", self.PAGE_SIZE, self.MAX_PAGES
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _resize(self, total: int) -> None:
        """Change the number of rows, telling the views.

        Args:
            total (int): The number of matching items.
        """
        self.logger.debug("Table resized from %d to %d rows.", self.total, total)
        if total > self.total:
            self.beginInsertRows(QModelIndex(), self.total, total - 1)
            self.total = total
            self.endInsertRows()
        elif total < self.total:
            self.beginRemoveRows(QModelIndex(), total, self.total - 1)
            self.total = total
            self.endRemoveRows()

    def _on_page(self, page: Page[T], generation: int, number: int) -> None:
        """Keep a page just read, and show its rows (GUI thread).

        Args:
            page (Page[T]): The page.
            generation (int): The generation of the request: an outdated page is ignored.
            number (int): The page number.
        """
        self.logger.debug(
            "Page %d read: %d rows (generation %d, current %d).", number, len(page.items), generation, self.generation
        )
        if generation != self.generation:
            return
        if page.total is not None:
            self._resize(page.total)
        self.cache.store(number, [self.builder(stored) for stored in page.items])
        first = number * self.PAGE_SIZE
        last = min(first + len(page.items), self.total) - 1
        if last >= first:
            self.dataChanged.emit(self.index(first, 0), self.index(last, self.columnCount() - 1))
        if page.total is not None:
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
        self.logger.warning("Page %d of the table cannot be read: %s", number, error)
        self.failed.emit(str(error))

    def _request(self, number: int, counted: bool) -> None:
        """Read a page in the storage thread.

        Args:
            number (int): The page number.
            counted (bool): Whether the matching items are counted too (the first page).
        """
        self.logger.debug("Reading page %d (counted: %s, generation %d).", number, counted, self.generation)
        generation = self.generation
        query = self.query.model_copy(
            update={"offset": number * self.PAGE_SIZE, "limit": self.PAGE_SIZE, "with_total": counted}
        )
        self.cache.pending.add(number)
        self.loop.submit(
            lambda storage: self.lister(storage, query),
            lambda page: self._on_page(page, generation, number),
            lambda error: self._on_error(error, generation, number),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_query(self, query: ItemQuery) -> None:
        """Show the items matching other filters, or in another order: the table is read again from its start.

        Args:
            query (ItemQuery): The filters and order (its bounds are managed by the table).
        """
        self.logger.info("Table query changed: %s.", query.model_dump(mode="json", exclude_defaults=True))
        self.generation += 1
        self.query = query
        self.beginResetModel()
        self.cache.clear()
        self.total = 0
        self.endResetModel()
        self._request(0, counted=True)

    def refresh(self) -> None:
        """Read the table again (its items were written), keeping the rows shown until their page is read."""
        self.logger.debug("Table refreshed: %d pages kept until read again.", len(self.cache.pages))
        self.generation += 1
        self.cache.invalidate()
        self._request(0, counted=True)

    def row(self, number: int) -> Optional[R]:
        """Get a row, reading its page when it is not kept or stale.

        Args:
            number (int): The row number.

        Returns:
            Optional[R]: The row, `None` while its page is read.
        """
        if not 0 <= number < self.total:
            return None
        if self.cache.needs(number):
            self._request(self.cache.page_of(number), counted=False)
        return self.cache.get(number)

    def row_at(self, index: ModelIndex) -> Optional[R]:
        """Get the row of a table index.

        Args:
            index (ModelIndex): The table index.

        Returns:
            Optional[R]: The row, `None` for an invalid index or while its page is read.
        """
        return self.row(index.row()) if index.isValid() else None

    def loaded_id(self, number: int) -> Optional[int]:
        """Get the storage identifier of a row when its page is kept, without reading it.

        Args:
            number (int): The row number.

        Returns:
            Optional[int]: The identifier, `None` when the row is not kept.
        """
        row = self.cache.get(number) if 0 <= number < self.total else None
        return row.id if row is not None else None

    def rows(self) -> List[R]:
        """Get the rows kept in memory.

        Returns:
            List[R]: The kept rows, by page.
        """
        return [row for page in self.cache.pages.values() for row in page]

    def rowCount(self, parent: Optional[ModelIndex] = None) -> int:
        """Get the number of rows (Qt override).

        Args:
            parent (Optional[ModelIndex]): The parent index, rows only exist at the top level.

        Returns:
            int: The number of matching items.
        """
        return 0 if parent is not None and parent.isValid() else self.total

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Order the items by a column, on the server (Qt override): the other columns are not sortable.

        Args:
            column (int): The column.
            order (Qt.SortOrder): The order.
        """
        sort = self.SORTS.get(column)
        if sort is None:
            self.logger.debug("Column %d cannot be sorted.", column)
            return
        descending = order == Qt.SortOrder.DescendingOrder
        if (sort, descending) == (self.query.sort, self.query.descending):
            return
        self.set_query(self.query.model_copy(update={"sort": sort, "descending": descending}))
