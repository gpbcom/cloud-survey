from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# First Party Imports.
from models.cloud.dated_item import DatedItem


class ItemCollector[T: DatedItem]:
    """Collect the items of a crawl in memory, an item streamed again replacing its previous version.

    Attributes:
        collected (Dict[str, T]): The items, by first match key,
            in the order they were first crawled.
        logger (Logger): The collector logger.

    Notes:
        `add` runs for each crawled item:
        it does not log, `items` does.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize an empty collector.

        Args:
            logger (Optional[Logger]): The collector logger.
        """
        self.collected: Dict[str, T] = {}
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Item collector ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def add(self, item: T) -> None:
        """Collect a crawled item.

        Args:
            item (T): The item.
        """
        self.collected[item.match_keys()[0]] = item

    def items(self) -> List[T]:
        """Get the collected items.

        Returns:
            List[T]: The items, in the order they were first crawled.
        """
        self.logger.debug("%d distinct items collected.", len(self.collected))
        return list(self.collected.values())
