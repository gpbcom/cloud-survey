from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.taxonomy.enums import Language


class LabelCount(BaseModel):
    """The number of stored items carrying a source label (or one of its aliases), for the label pickers.

    Attributes:
        id (int): The identifier of the label representing its group (its canonical label, else the first one).
        name (str): Its English name, else its text while it is not translated.
        text (str): Its text as the providers write it.
        language (Language): The language of its text.
        count (int): The number of items carrying the label or one of its aliases.
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1, description="The identifier of the label representing its group.")
    name: str = Field(min_length=1, description="Its English name, else its text.")
    text: str = Field(min_length=1, description="Its text as the providers write it.")
    language: Language = Field(default=Language.ENGLISH, description="The language of its text.")
    count: int = Field(ge=0, description="The number of items carrying the label.")

    @field_validator("name", "text", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: spaces collapsed and trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The cleaned text (its type is checked by pydantic afterwards).
        """
        return " ".join(value.split()) if isinstance(value, str) else value
