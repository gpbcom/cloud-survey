from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import RecordOrigin


class CompanyProfile(BaseModel):
    """A company crawled, as stored: its catalogue entry without its identifiers (stored apart, one per row).

    Attributes:
        company (str): The company key.
        position (int): Its rank in the catalogue.
        body (Dict[str, JsonValue]): Its catalogue entry, the identifier lists left empty.
        note (Optional[str]): What the research noted about it.
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The company key.")
    position: int = Field(ge=0, description="Its rank in the catalogue.")
    body: Dict[str, JsonValue] = Field(description="Its catalogue entry, without identifiers.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
