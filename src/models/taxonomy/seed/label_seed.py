from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.taxonomy.seed.seed_label import SeedLabel


class LabelSeed(BaseModel):
    """The label seed file of the project: the translations and categories of known source labels.

    Attributes:
        labels (List[SeedLabel]): The seeded labels.

    Notes:
        English labels need no entry: they keep their text as English name and the rules link them. The seed covers
        the Chinese and Russian labels, the synonyms to merge and the noise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: List[SeedLabel] = Field(default_factory=list, description="The seeded labels.")
