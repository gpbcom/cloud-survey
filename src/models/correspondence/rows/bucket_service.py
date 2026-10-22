from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider


class BucketService(BaseModel):
    """A catalogue service waiting to be matched within a taxonomy category, as sent to the language model.

    Attributes:
        product_id (int): The storage identifier of the product.
        provider (CloudProvider): Its cloud provider.
        name (str): Its name.
        description (str): Its description, shortened.
        labels (List[str]): The categories its catalogue gives it.
    """

    model_config = ConfigDict(frozen=True)

    product_id: int = Field(ge=1, description="The storage identifier of the product.")
    provider: CloudProvider = Field(description="Its cloud provider.")
    name: str = Field(min_length=1, description="Its name.")
    description: str = Field(default="", description="Its description, shortened.")
    labels: List[str] = Field(default_factory=list, description="The categories its catalogue gives it.")

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
