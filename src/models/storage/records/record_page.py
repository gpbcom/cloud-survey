from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, Field


class RecordPage[R: BaseModel](BaseModel):
    """A page of stored research records.

    Attributes:
        items (List[R]): The records of the page, in the query order.
        offset (int): The records skipped before the page.
        limit (int): The largest number of records of the page.
        total (Optional[int]): The records matching the query, `None` when not counted.
    """

    items: List[R] = Field(default_factory=list, description="The records of the page.")
    offset: int = Field(default=0, ge=0, description="The records skipped before the page.")
    limit: int = Field(ge=1, description="The largest number of records of the page.")
    total: Optional[int] = Field(default=None, ge=0, description="The records matching the query.")

    @property
    def has_more(self) -> bool:
        """Tell whether records follow the page.

        Returns:
            bool: Whether the page is full and, when counted, records remain after it.
        """
        if self.total is not None:
            return self.offset + len(self.items) < self.total
        return len(self.items) == self.limit
