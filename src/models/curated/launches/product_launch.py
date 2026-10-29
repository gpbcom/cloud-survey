from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue

# First Party Imports.
from models.curated.enums import RecordOrigin


class ProductLaunch(BaseModel):
    """The curated launch of a catalogue product, as stored: its date and source, or why it has none.

    Attributes:
        crawler (str): The cloud crawler whose catalogue names the product.
        name (str): The product name, as the catalogue writes it.
        position (int): Its rank among the launches.
        body (Dict[str, JsonValue]): The launch, as its curated model writes it (date, source or reason).
        note (Optional[str]): What the research noted about it.
        origin (RecordOrigin): Where it comes from.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    crawler: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The cloud crawler.")
    name: str = Field(min_length=1, max_length=300, description="The product name.")
    position: int = Field(ge=0, description="Its rank among the launches.")
    body: Dict[str, JsonValue] = Field(description="The launch, as its curated model writes it.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
