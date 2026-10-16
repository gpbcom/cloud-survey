from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.cloud.enums import DateSource


class ItemHistory[T: DatedItem]:
    """Dates the items of a new crawl (products or software) from the items of the previous one.

    Attributes:
        DELETION_RATIO (ClassVar[float]): The smallest share of the previous listed items a crawl must find for the
            missing items to be deleted.
        label (str): What is dated, for the logs (e.g. `aws catalogue`).
        logger (Logger): The history logger.

    Notes:
        The items are recognized by their match keys (their page, then their name). The website dates set by the
        crawler always win. Otherwise:
        - A new item is added at the crawl date, unless there is no previous crawl to compare with (its date stays
          unknown).
        - An item whose content changed, or which is listed again after its deletion, is updated at the crawl date.
        - A previous item missing from the crawl is deleted at the crawl date and kept in the file. When the crawl
          found less than `DELETION_RATIO` of the previous listed items, it is presumably partial: the missing items
          are kept unchanged.
    """

    DELETION_RATIO: ClassVar[float] = 0.5

    def __init__(self, label: str, logger: Optional[Logger] = None) -> None:
        """Initialize the history.

        Args:
            label (str): What is dated, for the logs.
            logger (Optional[Logger]): The history logger.
        """
        self.label = label
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _index(self, items: Sequence[T]) -> Dict[str, int]:
        """Index items by their match keys.

        Args:
            items (Sequence[T]): The items.

        Returns:
            Dict[str, int]: The position of the first item having each key.
        """
        index: Dict[str, int] = {}
        for position, item in enumerate(items):
            for key in item.match_keys():
                index.setdefault(key, position)
        return index

    def _match(self, item: T, index: Dict[str, int], used: Set[int]) -> Optional[int]:
        """Find the previous item of an item, each previous item matching once.

        Args:
            item (T): The crawled item.
            index (Dict[str, int]): The position of the previous items, by match key.
            used (Set[int]): The positions of the previous items already matched, updated.

        Returns:
            Optional[int]: The position of its previous item, `None` when it is new.
        """
        for key in item.match_keys():
            position = index.get(key)
            if position is not None and position not in used:
                used.add(position)
                return position
        return None

    def _dated(self, item: T, previous: Optional[T], crawled_at: datetime, baseline: bool) -> T:
        """Date a crawled item.

        Args:
            item (T): The crawled item, with the website dates if any.
            previous (Optional[T]): Its previous version, `None` when it is new.
            crawled_at (datetime): When it was crawled.
            baseline (bool): Whether a previous crawl exists to compare with.

        Returns:
            T: The item with its dates.
        """
        added_at, added_from = (item.added_at, DateSource.WEBSITE) if item.added_at else (None, None)
        updated_at, updated_from = (item.updated_at, DateSource.WEBSITE) if item.updated_at else (None, None)
        if previous is None:
            if added_at is None and baseline:
                added_at, added_from = crawled_at, DateSource.CRAWL
        else:
            if added_at is None:
                added_at, added_from = previous.added_at, previous.added_from
            changed = previous.is_deleted or previous.fingerprint() != item.fingerprint()
            if updated_at is None:
                if changed:
                    updated_at, updated_from = crawled_at, DateSource.CRAWL
                else:
                    updated_at, updated_from = previous.updated_at, previous.updated_from
        dates = {"added_at": added_at, "added_from": added_from, "updated_at": updated_at}
        return item.model_copy(update={**dates, "updated_from": updated_from, "deleted_at": None})

    ############################
    # Publicly Exposed Methods #
    ############################

    def merge(
        self, previous: Optional[Sequence[T]], current: Sequence[T], crawled_at: datetime, final: bool = True
    ) -> List[T]:
        """Date the crawled items, and keep the previous ones missing from the crawl as deleted.

        Args:
            previous (Optional[Sequence[T]]): The items of the previous crawl, deleted ones included, `None` when
                there is none.
            current (Sequence[T]): The crawled items.
            crawled_at (datetime): When they were crawled, timezone-aware.
            final (bool): Whether the crawl is over. While it runs, the previous items not crawled yet are kept
                unchanged, none is deleted.

        Returns:
            List[T]: The crawled items in their order, then the previous items missing from the crawl.
        """
        known = list(previous or [])
        index, used = self._index(known), set[int]()
        merged: List[T] = []
        added = updated = 0
        for item in current:
            position = self._match(item, index, used)
            before = known[position] if position is not None else None
            dated = self._dated(item, before, crawled_at, previous is not None)
            added += before is None and previous is not None
            updated += before is not None and dated.updated_at == crawled_at
            merged.append(dated)
        listed = sum(1 for item in known if not item.is_deleted)
        deleting = final and len(current) >= listed * self.DELETION_RATIO
        if final and not deleting:
            self.logger.warning(
                "The %s crawl found %d items out of %d listed before: it looks partial, nothing is marked deleted.",
                self.label,
                len(current),
                listed,
            )
        deleted = 0
        for position, item in enumerate(known):
            if position in used:
                continue
            if deleting and not item.is_deleted:
                item = item.model_copy(update={"deleted_at": crawled_at})
                deleted += 1
            merged.append(item)
        log = self.logger.info if final else self.logger.debug
        log(
            "%s history: %d added, %d updated, %d deleted since the previous crawl.",
            self.label,
            added,
            updated,
            deleted,
        )
        return merged
