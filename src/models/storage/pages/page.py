from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.storage.pages.stored_item import StoredItem


class Page[T: DatedItem](BaseModel):
    """A page of stored items.

    Attributes:
        items (List[StoredItem[T]]): The items of the page, in the query order.
        offset (int): The number of items skipped before the page.
        limit (int): The largest number of items of the page.
        total (Optional[int]): The number of items matching the filters, `None` when not counted.
    """

    items: List[StoredItem[T]] = Field(default_factory=list, description="The items of the page.")
    offset: int = Field(default=0, ge=0, description="The number of items skipped before the page.")
    limit: int = Field(ge=1, description="The largest number of items of the page.")
    total: Optional[int] = Field(default=None, ge=0, description="The number of items matching the filters.")

    @property
    def has_more(self) -> bool:
        """Tell whether items follow the page.

        Returns:
            bool: Whether the page is full and, when counted, items remain after it.
        """
        if self.total is not None:
            return self.offset + len(self.items) < self.total
        return len(self.items) == self.limit
