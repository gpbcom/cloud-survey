from __future__ import annotations

# Third Party Imports.
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentInventorRow(Base):
    """An inventor of a publication, in the filing order.

    Attributes:
        publication_number (Mapped[str]): The publication.
        position (Mapped[int]): The inventor's rank, from 0.
        name (Mapped[str]): The inventor's name.
        name_key (Mapped[str]): The name folded for the profiles (case, accents and punctuation removed).
    """

    __tablename__ = StorageTable.PATENT_INVENTORS
    __table_args__ = (Index("ix_patent_inventors_name_key", "name_key"),)

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200))
