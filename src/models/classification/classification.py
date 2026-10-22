from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import SoftwareCategory


class Classification(BaseModel):
    """What the classifier tells about a product or a software.

    Attributes:
        audiences (List[SoftwareCategory]): Who it is meant for, at least one.
        categories (List[str]): Its taxonomy categories, in taxonomy order, empty when only its domains are known.
        domains (List[str]): Its taxonomy domains, in taxonomy order, at least one.
    """

    model_config = ConfigDict(frozen=True)

    audiences: List[SoftwareCategory] = Field(min_length=1, description="Who it is meant for.")
    categories: List[str] = Field(default_factory=list, description="Its taxonomy categories.")
    domains: List[str] = Field(min_length=1, description="Its taxonomy domains.")
