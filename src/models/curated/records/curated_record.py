from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import CuratedDataset, RecordOrigin


class CuratedRecord(BaseModel):
    """One entry of a section of the chronology or of the markets catalogue, as stored.

    Attributes:
        dataset (CuratedDataset): The section.
        key (str): What identifies the entry in its section (its natural key, e.g. a company key).
        position (int): Its rank in the section (the catalogues keep their order).
        body (JsonValue): The entry, as its catalogue model writes it.
        note (Optional[str]): What the research noted about it.
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it (a reseed never overwrites it).
    """

    model_config = ConfigDict(frozen=True)

    dataset: CuratedDataset = Field(description="The section.")
    key: str = Field(min_length=1, max_length=300, description="The natural key of the entry.")
    position: int = Field(ge=0, description="Its rank in the section.")
    body: JsonValue = Field(description="The entry, as its catalogue model writes it.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
