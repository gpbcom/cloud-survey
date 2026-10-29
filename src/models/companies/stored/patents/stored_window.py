from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.companies.enums import PatentWindowStatus


class StoredWindow(BaseModel):
    """A stored patents search window: how far a company's assignee search has gone.

    Attributes:
        company (str): The company searched.
        query (str): The assignee searched.
        after (date): The first priority date of the window.
        before (date): The day after its last priority date.
        country (Optional[str]): The patent office searched, `None` for every office.
        expected (int): The publications Google counts.
        fetched (int): The publications read.
        status (PatentWindowStatus): Its state.
        searched_at (Optional[datetime]): When it was searched last.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(min_length=1, description="The company searched.")
    query: str = Field(min_length=1, description="The assignee searched.")
    after: date = Field(description="The first priority date of the window.")
    before: date = Field(description="The day after its last priority date.")
    country: Optional[str] = Field(default=None, description="The patent office searched.")
    expected: int = Field(default=0, ge=0, description="The publications Google counts.")
    fetched: int = Field(default=0, ge=0, description="The publications read.")
    status: PatentWindowStatus = Field(description="Its state.")
    searched_at: Optional[datetime] = Field(default=None, description="When it was searched last.")
