from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import SoftwareCategory


class SeedCategory(BaseModel):
    """A category of the taxonomy seed file (`conf/taxonomy/taxonomy.yaml`).

    Attributes:
        slug (str): The identifier of the category.
        en (str): The English name.
        ru (str): The Russian name.
        zh (str): The Chinese name.
        description (str): What the category holds, in one English line.
        audiences (List[SoftwareCategory]): Who its items are meant for, those of the domain when empty.
        hidden (bool): Whether the category is hidden from the pickers.
        umbrella (bool): Whether the category is the generic one of its domain, dropped next to a more specific one.

    Notes:
        The slug is checked by the taxonomy node it becomes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(min_length=1, description="The identifier of the category.")
    en: str = Field(min_length=1, description="The English name.")
    ru: str = Field(min_length=1, description="The Russian name.")
    zh: str = Field(min_length=1, description="The Chinese name.")
    description: str = Field(min_length=1, description="What the category holds.")
    audiences: List[SoftwareCategory] = Field(default_factory=list, description="Who its items are meant for.")
    hidden: bool = Field(default=False, description="Whether the category is hidden from the pickers.")
    umbrella: bool = Field(default=False, description="Whether the category is the generic one of its domain.")
