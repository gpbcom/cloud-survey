from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base


class ResearcherProfileRow(Base):
    """The OpenAlex profile of a researcher who wrote a paper as a member of a company.

    Attributes:
        author_id (Mapped[str]): The OpenAlex author.
        company (Mapped[str]): The company they wrote for.
        name (Mapped[str]): Their name.
        orcid (Mapped[Optional[str]]): Their ORCID.
        works_count (Mapped[int]): The works OpenAlex counts for them.
        cited_by_count (Mapped[int]): The citations their works received.
        h_index (Mapped[Optional[int]]): Their h-index.
        institution (Mapped[Optional[str]]): The institution they were last seen at.
        current_affiliation (Mapped[bool]): Whether one of their last known institutions belongs to the company.
        affiliation_years (Mapped[int]): The years their profile lists at one of the company's institutions.
        confirmed (Mapped[bool]): Whether they are confirmed as a member of the company (set after each papers
            search, see `OpenAlexSettings`): only the confirmed researchers are shown and counted.
        source_url (Mapped[Optional[str]]): The request it was read from.
        fetched_at (Mapped[datetime]): When it was written.
    """

    __tablename__ = StorageTable.RESEARCHER_PROFILES
    __table_args__ = (Index("ix_researcher_profiles_company", "company"),)

    author_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    company: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    orcid: Mapped[Optional[str]] = mapped_column(String(60))
    works_count: Mapped[int] = mapped_column(Integer)
    cited_by_count: Mapped[int] = mapped_column(Integer)
    h_index: Mapped[Optional[int]] = mapped_column(Integer)
    institution: Mapped[Optional[str]] = mapped_column(String(300))
    current_affiliation: Mapped[bool] = mapped_column(Boolean, server_default=false())
    affiliation_years: Mapped[int] = mapped_column(Integer, server_default="0")
    confirmed: Mapped[bool] = mapped_column(Boolean, server_default=true())
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
