from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.correspondence.rows.bucket_service import BucketService
from models.correspondence.rows.concept_row import ConceptRow


class CorrespondenceBucket(BaseModel):
    """The services of a taxonomy category waiting to be matched, with the concepts already found in it.

    Attributes:
        slug (str): The taxonomy category.
        pending (List[BucketService]): The services to match, by provider then identifier.
        concepts (List[ConceptRow]): The concepts of the category, with their services.
    """

    model_config = ConfigDict(frozen=True)

    slug: str = Field(min_length=1, description="The taxonomy category.")
    pending: List[BucketService] = Field(default_factory=list, description="The services to match.")
    concepts: List[ConceptRow] = Field(default_factory=list, description="The concepts of the category.")
