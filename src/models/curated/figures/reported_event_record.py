from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import RecordOrigin


class ReportedEventRecord(BaseModel):
    """A dated figure researched by hand (a private company's funding round or run rate), as stored.

    Attributes:
        company (str): The company key.
        position (int): Its rank among the company's events (same-day rounds stay apart).
        body (Dict[str, JsonValue]): The event, as its researched model writes it.
        note (Optional[str]): What the research noted about it (beyond the event's own note).
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The company key.")
    position: int = Field(ge=0, description="Its rank among the company's events.")
    body: Dict[str, JsonValue] = Field(description="The event, as its researched model writes it.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
