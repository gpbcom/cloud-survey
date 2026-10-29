from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class PaperAuthorRow(Base):
    """An author of a paper, with the institutions the paper gives for them.

    Attributes:
        openalex_id (Mapped[str]): The OpenAlex work.
        position (Mapped[int]): The author's rank, from 0.
        author_id (Mapped[Optional[str]]): The OpenAlex author.
        name (Mapped[str]): The author's name.
        orcid (Mapped[Optional[str]]): The author's ORCID.
        institutions (Mapped[str]): The OpenAlex institutions of the author in the paper, comma-separated.
        company_affiliated (Mapped[bool]): Whether one of them belongs to the company searched.
    """

    __tablename__ = StorageTable.PAPER_AUTHORS
    __table_args__ = (Index("ix_paper_authors_author_id", "author_id"),)

    openalex_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(300))
    orcid: Mapped[Optional[str]] = mapped_column(String(60))
    institutions: Mapped[str] = mapped_column(Text)
    company_affiliated: Mapped[bool] = mapped_column(Boolean)
