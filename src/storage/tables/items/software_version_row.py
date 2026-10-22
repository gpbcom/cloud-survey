from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.version_columns import VersionColumns


class SoftwareVersionRow(VersionColumns, Base):
    """A version of a software of a marketplace: its content each time a crawl changed it (see `VersionColumns`).

    Attributes:
        ITEM_TABLE (ClassVar[str]): The table of the software.
    """

    __tablename__ = StorageTable.SOFTWARE_VERSIONS

    ITEM_TABLE: ClassVar[str] = StorageTable.SOFTWARE
