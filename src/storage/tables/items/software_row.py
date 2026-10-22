from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Index, String, Text, literal_column
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.item_columns import ItemColumns


class SoftwareRow(ItemColumns, Base):
    """A software of the marketplace of a cloud provider, with its history dates (see `MarketplaceSoftware`).

    Attributes:
        publisher (Mapped[Optional[str]]): The software publisher.
        delivery (Mapped[str]): How the software is delivered.
        marketplace_categories (Mapped[List[str]]): The categories given by the marketplace.
        marketplace_category_paths (Mapped[JsonValue]): The categories of the marketplace in its own taxonomy, with
            their parents, as JSON (`NULL` when it gives none).
        categories (Mapped[List[str]]): Who the software is meant for.

    Notes:
        On top of the item indexes, the software can be searched by type, publisher, marketplace category (flat
        labels and taxonomy paths, `&&` and `@>`), name (trigrams) and history date, for the filters of the GUI.
    """

    __tablename__ = StorageTable.SOFTWARE
    __table_args__ = (
        Index("ix_software_provider_match_hash", "provider", "match_hash"),
        Index("ix_software_provider_name_hash", "provider", "name_hash"),
        Index("ix_software_provider_revision", "provider", "revision"),
        Index("ix_software_publisher", "publisher"),
        Index("ix_software_marketplace_categories", "marketplace_categories", postgresql_using="gin"),
        Index("ix_software_added_at", "added_at"),
        Index("ix_software_updated_at", "updated_at"),
        Index("ix_software_service_categories", "service_categories", postgresql_using="gin"),
        Index("ix_software_service_domains", "service_domains", postgresql_using="gin"),
        Index("ix_software_source_label_ids", "source_label_ids", postgresql_using="gin"),
        Index("ix_software_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index(
            "ix_software_search_trgm",
            literal_column("((name || ' ') || coalesce(publisher, ''))").label("search"),
            postgresql_using="gin",
            postgresql_ops={"search": "gin_trgm_ops"},
        ),
        Index(
            "ix_software_marketplace_category_paths",
            "marketplace_category_paths",
            postgresql_using="gin",
            postgresql_ops={"marketplace_category_paths": "jsonb_path_ops"},
        ),
        {"postgresql_with": {"fillfactor": 85}},
    )

    publisher: Mapped[Optional[str]] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(String(20))
    marketplace_categories: Mapped[List[str]] = mapped_column(ARRAY(Text))
    marketplace_category_paths: Mapped[JsonValue] = mapped_column(JSONB(none_as_null=True), nullable=True)
    categories: Mapped[List[str]] = mapped_column(ARRAY(String(40)))
