from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.cloud.enums import CloudProvider


class StoredItem[T: DatedItem](BaseModel):
    """A stored item (product or software) with its storage identity.

    Attributes:
        id (int): The storage identifier of the item, kept for its whole history.
        provider (CloudProvider): The cloud provider of the item.
        revision (int): The revision of its last write (see `DatasetStamp.revision`).
        item (T): The item.
    """

    id: int = Field(ge=1, description="The storage identifier of the item.")
    provider: CloudProvider = Field(description="The cloud provider of the item.")
    revision: int = Field(default=0, ge=0, description="The revision of its last write.")
    item: T = Field(description="The item.")
