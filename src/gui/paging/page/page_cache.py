from __future__ import annotations

# Standard Library Imports.
from collections import OrderedDict
from logging import Logger, getLogger
from typing import List, Optional, Set


class PageCache[R]:
    """The pages of rows of a table kept in memory: the most recently used ones, at most `max_pages`.

    Attributes:
        page_size (int): The number of rows per page.
        max_pages (int): The largest number of pages kept.
        pages (OrderedDict[int, List[R]]): The kept pages by number, the least recently used first.
        fresh (Set[int]): The kept pages read since the last refresh (the others are shown until read again).
        pending (Set[int]): The pages being read.
        logger (Logger): The cache logger.

    Notes:
        The row lookups (`get`, `needs`, `page_of`) run for each painted cell: they do not log.
    """

    def __init__(self, page_size: int, max_pages: int, logger: Optional[Logger] = None) -> None:
        """Initialize an empty cache.

        Args:
            page_size (int): The number of rows per page.
            max_pages (int): The largest number of pages kept.
            logger (Optional[Logger]): The cache logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.page_size = page_size
        self.max_pages = max_pages
        self.pages: OrderedDict[int, List[R]] = OrderedDict()
        self.fresh: Set[int] = set()
        self.pending: Set[int] = set()
        self.logger.debug("Page cache created: pages of %d rows, at most %d pages.", page_size, max_pages)

    ############################
    # Publicly Exposed Methods #
    ############################

    def page_of(self, row: int) -> int:
        """Get the page of a row.

        Args:
            row (int): The row number.

        Returns:
            int: The page number.
        """
        return row // self.page_size

    def get(self, row: int) -> Optional[R]:
        """Get a kept row, marking its page as recently used.

        Args:
            row (int): The row number.

        Returns:
            Optional[R]: The row, `None` when its page is not kept.
        """
        number = self.page_of(row)
        page = self.pages.get(number)
        if page is None:
            return None
        self.pages.move_to_end(number)
        offset = row - number * self.page_size
        return page[offset] if offset < len(page) else None

    def needs(self, row: int) -> bool:
        """Tell whether the page of a row must be read: not kept, or kept from before the last refresh.

        Args:
            row (int): The row number.

        Returns:
            bool: Whether the page is neither fresh nor being read.
        """
        number = self.page_of(row)
        return number not in self.fresh and number not in self.pending

    def store(self, number: int, rows: List[R]) -> None:
        """Keep a page just read, forgetting the least recently used pages beyond `max_pages`.

        Args:
            number (int): The page number.
            rows (List[R]): Its rows.
        """
        self.pages[number] = rows
        self.pages.move_to_end(number)
        self.fresh.add(number)
        self.pending.discard(number)
        while len(self.pages) > self.max_pages:
            evicted, _ = self.pages.popitem(last=False)
            self.fresh.discard(evicted)
        self.logger.debug("Page %d kept: %d rows, %d pages in memory.", number, len(rows), len(self.pages))

    def invalidate(self) -> None:
        """Mark every kept page as stale: shown until read again."""
        self.logger.debug("The %d kept pages are stale until read again.", len(self.pages))
        self.fresh.clear()
        self.pending.clear()

    def clear(self) -> None:
        """Forget every page."""
        self.logger.debug("The %d kept pages are forgotten.", len(self.pages))
        self.pages.clear()
        self.invalidate()

    @property
    def row_count(self) -> int:
        """Count the rows kept in memory.

        Returns:
            int: The number of kept rows.
        """
        return sum(len(page) for page in self.pages.values())
