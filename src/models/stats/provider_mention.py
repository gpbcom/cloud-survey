from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, Field


class ProviderMention(BaseModel):
    """A provider named by a market report without a market share.

    Attributes:
        name (str): The provider name, as written in the report.
        rank (Optional[int]): The market rank given by the report, e.g. 4 for "fourth-placed", `None` when not given.
    """

    name: str = Field(min_length=1, max_length=100, description="The provider name.")
    rank: Optional[int] = Field(default=None, ge=1, description="The market rank given by the report.")
