from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class PromptSet(BaseModel):
    """The system prompts of the language model tasks of the taxonomy (`conf/taxonomy/prompts.yaml`).

    Attributes:
        label_translation (str): The prompt translating and linking the source labels.
        item_classification (str): The prompt categorizing the unclassified items.
        service_correspondence (str): The prompt grouping the equivalent services of the providers into concepts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label_translation: str = Field(min_length=1, description="The prompt translating the source labels.")
    item_classification: str = Field(min_length=1, description="The prompt categorizing the unclassified items.")
    service_correspondence: str = Field(min_length=1, description="The prompt grouping the equivalent services.")

    @field_validator("label_translation", "item_classification", "service_correspondence", mode="before")
    def validate_prompt(cls, value: JsonValue) -> JsonValue:
        """Trim a raw prompt.

        Args:
            value (JsonValue): The raw prompt.

        Returns:
            JsonValue: The prompt without surrounding blank lines.
        """
        return value.strip() if isinstance(value, str) else value
