from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.cloud.enums import DateSource
from models.cloud.item_state import ItemState


class ItemHistory[T: DatedItem]:
    """Dates the items of a new crawl (products or software) from the items of the previous one.

    Attributes:
        DELETION_RATIO (ClassVar[float]): The smallest share of the previous listed items a crawl must find for the
            missing items to be deleted.
        label (str): What is dated, for the logs (e.g. `aws catalogue`).
        logger (Logger): The history logger.

    Notes:
        The items are recognized by their match keys (their page, then their name). The website dates set by the
        crawler always win, with their caveats. Otherwise:
        - A new item is added at the crawl date, unless there is no previous crawl to compare with (its date stays
          unknown).
        - An item whose content changed, or which is listed again after its deletion, is updated at the crawl date.
        - A previous item missing from the crawl is deleted at the crawl date and kept in the file. When the crawl
          found less than `DELETION_RATIO` of the previous listed items, it is presumably partial: the missing items
          are kept unchanged.
        `date` and `_match` run for each crawled item: they do not log, `merge` and `deletes` do.
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
        self.logger.debug("History of the %s ready.", label)

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
        self.logger.debug("Indexing %d previous %s items.", len(items), self.label)
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

    ############################
    # Publicly Exposed Methods #
    ############################

    def date(self, item: T, previous: Optional[ItemState], crawled_at: datetime, baseline: bool) -> T:   # noqa: E501
        """Date a crawled item from the state of its previous version.

        Args:
            item (T): The crawled item, with the website dates if any.
            previous (Optional[ItemState]): The dates and content hash of
                its previous version, `None` when it is new.
            crawled_at (datetime): When it was crawled.
            baseline (bool): Whether a previous crawl exists to compare with.

        Returns:
            T: The item with its dates.
        """
        added_at, added_from, added_caveat = (
            (item.added_at, DateSource.WEBSITE, item.added_caveat) if item.added_at else (None, None, None)   # noqa: E501
        ) 
        updated_at, updated_from, updated_caveat = (
            (item.updated_at, DateSource.WEBSITE, item.updated_caveat) if item.updated_at else (None, None, None)   # noqa: E501
        )
        if previous is None:
            if added_at is None and baseline:
                added_at, added_from = crawled_at, DateSource.CRAWL
        else:
            if added_at is None:
                added_at, added_from, added_caveat = previous.added_at, previous.added_from, previous.added_caveat   # noqa: E501
            changed = previous.is_deleted or previous.fingerprint != item.fingerprint_hash()   # noqa: E501
            if updated_at is None:
                if changed:
                    updated_at, updated_from = crawled_at, DateSource.CRAWL
                else:
                    updated_at, updated_from = previous.updated_at, previous.updated_from   # noqa: E501
                    updated_caveat = previous.updated_caveat   # noqa: E501
        dates = {
            "added_at": added_at,
            "added_from": added_from,
            "added_caveat": added_caveat,
            "updated_at": updated_at,
            "updated_from": updated_from,
            "updated_caveat": updated_caveat,
        }
        return item.model_copy(update={**dates, "deleted_at": None})

    def deletes(self, found: int, listed: int, final: bool) -> bool:
        """Tell whether the items missing from a crawl are deleted: the crawl is over and does not look partial.

        Args:
            found (int): The number of items crawled.
            listed (int): The number of items listed (not deleted) before the crawl.
            final (bool): Whether the crawl is over.

        Returns:
            bool: Whether the missing items are deleted. A finished crawl finding less than `DELETION_RATIO` of the
                listed items is logged as partial.
        """
        deleting = final and found >= listed * self.DELETION_RATIO
        if final and not deleting:
            self.logger.warning(
                "The %s crawl found %d items out of %d listed before: "   # noqa: E501
                "it looks partial, nothing is marked deleted.",
                self.label,
                found,
                listed,
            )
        return deleting

    def merge(
        self, previous: Optional[Sequence[T]], current: Sequence[T], crawled_at: datetime, final: bool = True   # noqa: E501
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
        self.logger.debug(
            "Dating %d %s items from %d previous ones (final: %s).",
            len(current),
            self.label,
            len(previous or []),
            final,
        )
        known = list(previous or [])
        index, used = self._index(known), set[int]()
        merged: List[T] = []
        added = updated = 0
        for item in current:
            position = self._match(item, index, used)
            before = known[position] if position is not None else None
            dated = self.date(item, before.state() if before else None, crawled_at, previous is not None)   # noqa: E501
            added += before is None and previous is not None
            updated += before is not None and dated.updated_at == crawled_at
            merged.append(dated)
        listed = sum(1 for item in known if not item.is_deleted)
        deleting = self.deletes(len(current), listed, final)
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
            "%s history: %d added, %d updated, %d "  # noqa: E501
            "deleted since the previous crawl.",
            self.label,
            added,
            updated,
            deleted,
        )
        return merged
