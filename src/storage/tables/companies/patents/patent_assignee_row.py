from __future__ import annotations

# Third Party Imports.
from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentAssigneeRow(Base):
    """An assignee of a publication: one it was filed by, or one holding it now.

    Attributes:
        publication_number (Mapped[str]): The publication.
        position (Mapped[int]): The assignee's rank, from 0.
        original (Mapped[bool]): Whether it filed the publication (else it holds it now).
        name (Mapped[str]): The assignee's name.
    """

    __tablename__ = StorageTable.PATENT_ASSIGNEES
    __table_args__ = (Index("ix_patent_assignees_name", "name"),)

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    original: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
