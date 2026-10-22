from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.taxonomy.llm.item_categorization import ItemCategorization


class CategorizationBatch(BaseModel):
    """The language model answer for a batch of items (its structured output).

    Attributes:
        items (List[ItemCategorization]): One answer per item sent.
    """

    model_config = ConfigDict(extra="forbid")

    items: List[ItemCategorization] = Field(default_factory=list, description="One answer per item sent.")
