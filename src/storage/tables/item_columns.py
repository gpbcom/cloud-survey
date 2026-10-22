from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import List, Optional

# Third Party Imports.
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import ITEM_REVISION


class ItemColumns:
    """The columns shared by the crawled items (products and software): identity, match keys, content and dates.

    Attributes:
        id (Mapped[int]): The storage identifier, kept by the item for its whole history (even when its page moves).
        provider (Mapped[str]): The cloud provider.
        match_hash (Mapped[bytes]): The hash of the most reliable match key of the item (see `DatedItem.match_keys`).
        name_hash (Mapped[bytes]): The hash of the least reliable match key (its name).
        name (Mapped[str]): The item name.
        description (Mapped[str]): The item description.
        url (Mapped[Optional[str]]): The item page.
        added_at, added_from, added_caveat, updated_at, updated_from, updated_caveat, deleted_at: The history dates.
        fingerprint (Mapped[bytes]): The hash of the content fields of the item (see `DatedItem.fingerprint_hash`).
        first_crawl_id (Mapped[Optional[int]]): The crawl which found the item first, `NULL` for an item created by
            hand.
        revision (Mapped[int]): The value of the `item_revision` sequence when the row was last written.
        service_categories (Mapped[List[str]]): The taxonomy categories of the item (see `CategorizedItem`).
        service_domains (Mapped[List[str]]): The taxonomy domains of the item.
        source_label_ids (Mapped[List[int]]): The identifiers of its source labels.
        categories_source (Mapped[Optional[str]]): What gave the item its categories (see `CategorySource`).
        categories_fingerprint (Mapped[Optional[bytes]]): The content fingerprint the language model categorized,
            its categories being kept while the content does not change.

    Notes:
        The unified categorization columns are searched with `&&` (GIN indexes of each items table).
    """

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    match_hash: Mapped[bytes] = mapped_column(LargeBinary)
    name_hash: Mapped[bytes] = mapped_column(LargeBinary)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    added_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    added_from: Mapped[Optional[str]] = mapped_column(String(20))
    added_caveat: Mapped[Optional[str]] = mapped_column(String(40))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_from: Mapped[Optional[str]] = mapped_column(String(20))
    updated_caveat: Mapped[Optional[str]] = mapped_column(String(40))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    first_crawl_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey(f"{StorageTable.CRAWLS}.id"))
    revision: Mapped[int] = mapped_column(BigInteger, server_default=ITEM_REVISION.next_value())
    service_categories: Mapped[List[str]] = mapped_column(ARRAY(String(60)), server_default=text("'{}'"))
    service_domains: Mapped[List[str]] = mapped_column(ARRAY(String(60)), server_default=text("'{}'"))
    source_label_ids: Mapped[List[int]] = mapped_column(ARRAY(BigInteger), server_default=text("'{}'"))
    categories_source: Mapped[Optional[str]] = mapped_column(String(10))
    categories_fingerprint: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
