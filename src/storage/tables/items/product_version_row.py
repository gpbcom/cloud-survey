from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.version_columns import VersionColumns


class ProductVersionRow(VersionColumns, Base):
    """A version of a product of a catalogue: its content each time a crawl changed it (see `VersionColumns`).

    Attributes:
        ITEM_TABLE (ClassVar[str]): The table of the products.
    """

    __tablename__ = StorageTable.PRODUCT_VERSIONS

    ITEM_TABLE: ClassVar[str] = StorageTable.PRODUCTS
