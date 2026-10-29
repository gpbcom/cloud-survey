from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.curated.enums import CuratedFile


class CuratedState(BaseModel):
    """The state of a file of the curated bundle in a database: its revision and its last seed.

    Attributes:
        dataset (CuratedFile): The bundle file.
        revision (int): Incremented by every write of its rows (the catalogues are read again when it changes).
        seed_hash (Optional[str]): The hash of the bundle file last applied, `None` before the first seed.
        seeded_at (Optional[datetime]): When it was applied.
    """

    model_config = ConfigDict(frozen=True)

    dataset: CuratedFile = Field(description="The bundle file.")
    revision: int = Field(default=0, ge=0, description="Incremented by every write of its rows.")
    seed_hash: Optional[str] = Field(default=None, description="The hash of the bundle file last applied.")
    seeded_at: Optional[datetime] = Field(default=None, description="When it was applied.")
