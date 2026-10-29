from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import RecordOrigin


class ReportedCompanyRecord(BaseModel):
    """A company whose figures were researched by hand, as stored: its currency, fiscal year end and scale.

    Attributes:
        company (str): The company key.
        position (int): Its rank among the researched companies.
        body (Dict[str, JsonValue]): Its researched entry, the years and the events left empty (stored apart).
        note (Optional[str]): What the research noted (its gaps: the years no source covers).
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The company key.")
    position: int = Field(ge=0, description="Its rank among the researched companies.")
    body: Dict[str, JsonValue] = Field(description="Its entry, without years and events.")
    note: Optional[str] = Field(default=None, description="What the research noted.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
