from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.taxonomy.enums import LabelStatus, Language


class SourceLabel(BaseModel):
    """A stored source label (a category of a provider), as the GUI shows it.

    Attributes:
        id (int): The label identifier.
        text (str): Its text as the providers write it.
        language (Language): The language of its text.
        name_en (Optional[str]): Its English name, `None` while it is not translated.
        status (LabelStatus): Its translation status.
        canonical_id (Optional[int]): The label it was merged into, if any.
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1, description="The label identifier.")
    text: str = Field(min_length=1, description="Its text as the providers write it.")
    language: Language = Field(default=Language.ENGLISH, description="The language of its text.")
    name_en: Optional[str] = Field(default=None, description="Its English name.")
    status: LabelStatus = Field(default=LabelStatus.PENDING, description="Its translation status.")
    canonical_id: Optional[int] = Field(default=None, description="The label it was merged into.")

    @field_validator("name_en", mode="before")
    def validate_name_en(cls, value: JsonValue) -> JsonValue:
        """Validate the raw English name: spaces collapsed, a blank name read as missing.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The cleaned name, `None` when blank.
        """
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def display_name(self) -> str:
        """Get the name shown for the label.

        Returns:
            str: Its English name, else its text while it is not translated.
        """
        return self.name_en or self.text
