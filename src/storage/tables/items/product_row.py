from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.item_columns import ItemColumns


class ProductRow(ItemColumns, Base):
    """A product of the catalogue of a cloud provider.

    Attributes:
        pricing_policy (Mapped[JsonValue]): The pricing policies of the product, as JSON.
        catalogue_categories (Mapped[List[str]]): The categories the catalogue of the provider files the product
            under (searched with `&&`, for the filters of the GUI).
        categories (Mapped[List[str]]): Who the product is meant for: developer tool, end-user software or both
            (searched with `@>`, for the audience filters and charts).

    Notes:
        The rows are found by provider and match key hash
        (the history of a crawl), and by provider and revision (the
        readers of the catalogue). The table leaves room in its
        pages so that the updates stay in place.
    """

    __tablename__ = StorageTable.PRODUCTS
    __table_args__ = (
        Index("ix_products_provider_match_hash", "provider", "match_hash"),
        Index("ix_products_provider_name_hash", "provider", "name_hash"),
        Index("ix_products_provider_revision", "provider", "revision"),
        Index("ix_products_catalogue_categories", "catalogue_categories", postgresql_using="gin"),
        Index("ix_products_categories", "categories", postgresql_using="gin"),
        Index("ix_products_service_categories", "service_categories", postgresql_using="gin"),
        Index("ix_products_service_domains", "service_domains", postgresql_using="gin"),
        Index("ix_products_source_label_ids", "source_label_ids", postgresql_using="gin"),
        Index("ix_products_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        {"postgresql_with": {"fillfactor": 85}},
    )

    pricing_policy: Mapped[JsonValue] = mapped_column(JSONB, nullable=False)
    catalogue_categories: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    categories: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
