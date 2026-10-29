from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import CompoundingWarningKind


class CompoundingWarning(BaseModel):
    """A caveat of a compounding analysis.

    Attributes:
        kind (CompoundingWarningKind): The caveat.
        provider (Optional[CloudProvider]): The provider concerned, `None` for the whole analysis.
        detail (str): What it is about, in plain words.
    """

    model_config = ConfigDict(frozen=True)

    kind: CompoundingWarningKind = Field(description="The caveat.")
    provider: Optional[CloudProvider] = Field(default=None, description="The provider concerned.")
    detail: str = Field(default="", max_length=400, description="What it is about.")
