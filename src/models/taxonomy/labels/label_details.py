from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.taxonomy.enums import LabelStatus, Language, NameSource


class LabelDetails(BaseModel):
    """A source label as the Categories manager shows it: its translation, links, merge and where it is used.

    Attributes:
        id (int): The label identifier.
        text (str): Its text as the providers write it.
        language (Language): The language of its text.
        name_en (Optional[str]): Its English name, `None` while it is not translated.
        name_source (Optional[NameSource]): Where the English name comes from.
        status (LabelStatus): Its translation status.
        status_source (Optional[NameSource]): Where the status comes from.
        canonical_id (Optional[int]): The label it was merged into, if any.
        links (List[str]): The taxonomy nodes it tells (its own links, the excluded ones left out).
        excluded (List[str]): The taxonomy nodes a person removed from it.
        providers (List[str]): The datasets it was seen in, as `<kind>:<provider>`.
        items (int): The number of stored items (products and software) carrying it.
    """

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1, description="The label identifier.")
    text: str = Field(min_length=1, description="Its text as the providers write it.")
    language: Language = Field(default=Language.ENGLISH, description="The language of its text.")
    name_en: Optional[str] = Field(default=None, description="Its English name.")
    name_source: Optional[NameSource] = Field(default=None, description="Where the English name comes from.")
    status: LabelStatus = Field(default=LabelStatus.PENDING, description="Its translation status.")
    status_source: Optional[NameSource] = Field(default=None, description="Where the status comes from.")
    canonical_id: Optional[int] = Field(default=None, description="The label it was merged into.")
    links: List[str] = Field(default_factory=list, description="The taxonomy nodes it tells.")
    excluded: List[str] = Field(default_factory=list, description="The taxonomy nodes removed from it.")
    providers: List[str] = Field(default_factory=list, description="The datasets it was seen in.")
    items: int = Field(default=0, ge=0, description="The number of stored items carrying it.")

    @field_validator("links", "excluded", "providers", mode="before")
    def validate_lists(cls, value: JsonValue) -> JsonValue:
        """Validate a raw list: missing read as empty, sorted, each value once.

        Args:
            value (JsonValue): The raw values.

        Returns:
            JsonValue: The sorted values without duplicates (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            cleaned: List[JsonValue] = [*sorted({item for item in value if isinstance(item, str) and item})]
            return cleaned
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
