from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.correspondence.llm.concept_answer import ConceptAnswer


class ConceptBatch(BaseModel):
    """The language model answer for the services of a category (its structured output).

    Attributes:
        concepts (List[ConceptAnswer]): The concepts the services are filed under.
    """

    model_config = ConfigDict(extra="forbid")

    concepts: List[ConceptAnswer] = Field(default_factory=list, description="The concepts of the services.")
