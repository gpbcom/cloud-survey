from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import FigureCheck, RecordOrigin


class ReportedYearRecord(BaseModel):
    """A fiscal year researched by hand, as stored.

    Attributes:
        company (str): The company key.
        fiscal_year (int): The fiscal year.
        position (int): Its rank among the company's years.
        body (Dict[str, JsonValue]): The year, as its researched model writes it (its figures and source).
        note (Optional[str]): What the research noted about it (beyond the year's own note).
        check_status (FigureCheck): What a parser of the cited document found.
        checked_at (Optional[datetime]): When a parser read the document last.
        check_note (Optional[str]): What the check found (the figures the document does not state).
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The company key.")
    fiscal_year: int = Field(ge=1900, le=2200, description="The fiscal year.")
    position: int = Field(ge=0, description="Its rank among the company's years.")
    body: Dict[str, JsonValue] = Field(description="The year, as its researched model writes it.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    check_status: FigureCheck = Field(default=FigureCheck.UNCHECKED, description="What a parser found.")
    checked_at: Optional[datetime] = Field(default=None, description="When a parser read the document last.")
    check_note: Optional[str] = Field(default=None, max_length=500, description="What the check found.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
