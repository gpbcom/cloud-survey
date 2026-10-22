from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.taxonomy.llm.label_translation import LabelTranslation


class TranslationBatch(BaseModel):
    """The language model answer for a batch of source labels (its structured output).

    Attributes:
        labels (List[LabelTranslation]): One answer per label sent.
    """

    model_config = ConfigDict(extra="forbid")

    labels: List[LabelTranslation] = Field(default_factory=list, description="One answer per label sent.")
