from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PatentCitationRow(Base):
    """A citation read on a publication page: another publication it cites, or that cites it.

    Attributes:
        publication_number (Mapped[str]): The publication whose page states it.
        other (Mapped[str]): The other publication.
        kind (Mapped[str]): Which way it goes: `cites`, `cited-by`, `family-cites`, `family-cited-by`.
        examiner (Mapped[bool]): Whether the examiner added it.
        other_priority_date (Mapped[Optional[date]]): The priority date of the other publication.
        other_publication_date (Mapped[Optional[date]]): The publication date of the other publication.
        other_assignee (Mapped[Optional[str]]): The assignee of the other publication.
        other_title (Mapped[Optional[str]]): The title of the other publication.
    """

    __tablename__ = StorageTable.PATENT_CITATIONS
    __table_args__ = (Index("ix_patent_citations_other", "other"),)

    publication_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    other: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    examiner: Mapped[bool] = mapped_column(Boolean)
    other_priority_date: Mapped[Optional[date]] = mapped_column(Date)
    other_publication_date: Mapped[Optional[date]] = mapped_column(Date)
    other_assignee: Mapped[Optional[str]] = mapped_column(String(300))
    other_title: Mapped[Optional[str]] = mapped_column(Text)
