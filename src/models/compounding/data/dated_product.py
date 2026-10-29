from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider


class DatedProduct(BaseModel):
    """A dated catalogue product of a provider analysed, with its cloud computing categories.

    Attributes:
        provider (CloudProvider): The provider.
        year (int): The year it was launched (or the year its date stands for when it is held).
        held (bool): Whether its date only means "on or before" (a feed start, a website record, a first crawl), so
            that it is counted as held at the start of the window rather than as a launch.
        categories (List[str]): Its categories kept (cloud computing domains only).
        deleted (Optional[int]): The year it left the catalogue, `None` while it is offered.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider.")
    year: int = Field(ge=1950, le=2100, description="The year it was launched.")
    held: bool = Field(default=False, description="Whether its date only means on or before.")
    categories: List[str] = Field(default_factory=list, description="Its categories kept.")
    deleted: Optional[int] = Field(default=None, ge=1950, le=2100, description="The year it left the catalogue.")
