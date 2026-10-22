from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.correspondence.enums import ConceptSource, MemberRole


class ConceptMember(BaseModel):
    """A catalogue service filed under a service concept.

    Attributes:
        product_id (int): The storage identifier of the product.
        provider (CloudProvider): Its cloud provider.
        name (str): Its name.
        description (str): Its description (shortened), for the tooltips.
        url (Optional[str]): Its page.
        role (MemberRole): Whether it does what the concept stands for, or part of it.
        confidence (int): How sure the language model is, from 0 to 100 (100 when a person set it).
        source (ConceptSource): Who filed it under the concept.
        deleted (bool): Whether the service disappeared from its catalogue.
    """

    model_config = ConfigDict(frozen=True)

    product_id: int = Field(ge=1, description="The storage identifier of the product.")
    provider: CloudProvider = Field(description="Its cloud provider.")
    name: str = Field(min_length=1, description="Its name.")
    description: str = Field(default="", description="Its description, shortened.")
    url: Optional[str] = Field(default=None, description="Its page.")
    role: MemberRole = Field(default=MemberRole.EQUIVALENT, description="How it matches the concept.")
    confidence: int = Field(default=100, ge=0, le=100, description="How sure the language model is.")
    source: ConceptSource = Field(default=ConceptSource.LLM, description="Who filed it under the concept.")
    deleted: bool = Field(default=False, description="Whether it disappeared from its catalogue.")

    @field_validator("name", "description", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The cleaned text (its type is checked by pydantic afterwards), empty when missing.
        """
        if value is None:
            return ""
        return " ".join(value.split()) if isinstance(value, str) else value
