from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class StoredPatent(BaseModel):
    """A stored patent publication, as the Patents & Papers tab lists it.

    Attributes:
        publication_number (str): The publication.
        companies (List[str]): The companies whose assignee search found it.
        country (str): The office of the publication.
        title (Optional[str]): Its title.
        assignee (Optional[str]): Its first assignee.
        priority_date (Optional[date]): The date of its first filing.
        publication_date (Optional[date]): The date it was published.
        grant_date (Optional[date]): The date it was granted.
        family_id (Optional[str]): Its DOCDB family.
        claims (Optional[int]): The number of its claims (from its page).
        page_read (bool): Whether its page (citations, family, classes) was read.
        source_url (Optional[str]): Its Google Patents page.
    """

    model_config = ConfigDict(frozen=True)

    publication_number: str = Field(min_length=1, description="The publication.")
    companies: List[str] = Field(default_factory=list, description="The companies whose search found it.")
    country: str = Field(default="", description="The office of the publication.")
    title: Optional[str] = Field(default=None, description="Its title.")
    assignee: Optional[str] = Field(default=None, description="Its first assignee.")
    priority_date: Optional[date] = Field(default=None, description="The date of its first filing.")
    publication_date: Optional[date] = Field(default=None, description="The date it was published.")
    grant_date: Optional[date] = Field(default=None, description="The date it was granted.")
    family_id: Optional[str] = Field(default=None, description="Its DOCDB family.")
    claims: Optional[int] = Field(default=None, ge=0, description="The number of its claims.")
    page_read: bool = Field(default=False, description="Whether its page was read.")
    source_url: Optional[str] = Field(default=None, description="Its Google Patents page.")

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: a list, or a comma-separated text as the database aggregates them.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies, sorted, each once.
        """
        if isinstance(value, str):
            companies: List[JsonValue] = []
            companies.extend(sorted({part.strip() for part in value.split(",") if part.strip()}))
            return companies
        if value is None:
            return []
        return value
