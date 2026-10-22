from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import SoftwareCategory
from models.taxonomy.seed.seed_category import SeedCategory


class SeedDomain(BaseModel):
    """A domain of the taxonomy seed file, with its categories.

    Attributes:
        slug (str): The identifier of the domain.
        en (str): The English name.
        ru (str): The Russian name.
        zh (str): The Chinese name.
        description (str): What the domain holds, in one English line.
        audiences (List[SoftwareCategory]): Who its items are meant for.
        hidden (bool): Whether the domain is hidden from the pickers.
        categories (List[SeedCategory]): Its categories, in display order, at least one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(min_length=1, description="The identifier of the domain.")
    en: str = Field(min_length=1, description="The English name.")
    ru: str = Field(min_length=1, description="The Russian name.")
    zh: str = Field(min_length=1, description="The Chinese name.")
    description: str = Field(min_length=1, description="What the domain holds.")
    audiences: List[SoftwareCategory] = Field(default_factory=list, description="Who its items are meant for.")
    hidden: bool = Field(default=False, description="Whether the domain is hidden from the pickers.")
    categories: List[SeedCategory] = Field(min_length=1, description="Its categories, in display order.")
