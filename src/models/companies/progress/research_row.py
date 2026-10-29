from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.companies.enums import CompanyFactKind, CompanyFeed


class ResearchRow(BaseModel):
    """A fact of a patents or papers crawl, as the Patents & Papers tab lists it while it streams.

    Attributes:
        feed (CompanyFeed): The source.
        kind (CompanyFactKind): What the fact is.
        company (Optional[str]): The company, `None` for a patent page (it names only its publication).
        identifier (str): The publication number, the OpenAlex work or author, or the search window.
        title (str): The title, the researcher's name or the assignee searched.
        day (Optional[date]): The priority date, the publication day or the start of the window.
        detail (str): What else matters (the window's counts, the citations, the h-index).
        url (Optional[str]): The page read.
    """

    model_config = ConfigDict(frozen=True)

    feed: CompanyFeed = Field(description="The source.")
    kind: CompanyFactKind = Field(description="What the fact is.")
    company: Optional[str] = Field(default=None, description="The company.")
    identifier: str = Field(default="", description="The publication, work, author or window.")
    title: str = Field(default="", description="The title or name.")
    day: Optional[date] = Field(default=None, description="The date.")
    detail: str = Field(default="", description="What else matters.")
    url: Optional[str] = Field(default=None, description="The page read.")
