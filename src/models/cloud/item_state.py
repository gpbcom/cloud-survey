from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import DateCaveat, DateSource


class ItemState(BaseModel):
    """What the history of a crawled item needs from its previous version: its dates and its content fingerprint.

    Attributes:
        added_at (Optional[datetime]): When the item was added, `None` when unknown.
        added_from (Optional[DateSource]): Where `added_at` comes from.
        added_caveat (Optional[DateCaveat]): Why `added_at` may be inaccurate.
        updated_at (Optional[datetime]): When the item was last updated, `None` when unknown.
        updated_from (Optional[DateSource]): Where `updated_at` comes from.
        updated_caveat (Optional[DateCaveat]): Why `updated_at` may be inaccurate.
        deleted_at (Optional[datetime]): When the item disappeared from the website, `None` while it is listed.
        fingerprint (bytes): The hash of the content fields of the item (see `DatedItem.fingerprint_hash`).
    """

    model_config = ConfigDict(frozen=True)

    added_at: Optional[datetime] = Field(default=None, description="When the item was added.")
    added_from: Optional[DateSource] = Field(default=None, description="Where the added date comes from.")
    added_caveat: Optional[DateCaveat] = Field(default=None, description="Why the added date may be inaccurate.")
    updated_at: Optional[datetime] = Field(default=None, description="When the item was last updated.")
    updated_from: Optional[DateSource] = Field(default=None, description="Where the updated date comes from.")
    updated_caveat: Optional[DateCaveat] = Field(default=None, description="Why the updated date may be inaccurate.")
    deleted_at: Optional[datetime] = Field(default=None, description="When the item disappeared from the website.")
    fingerprint: bytes = Field(description="The hash of the content fields of the item.")

    @property
    def is_deleted(self) -> bool:
        """Tell whether the item had disappeared from the website.

        Returns:
            bool: Whether it has a deletion date.
        """
        return self.deleted_at is not None
