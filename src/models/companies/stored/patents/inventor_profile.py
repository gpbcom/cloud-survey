from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class InventorProfile(BaseModel):
    """An inventor profile derived from the stored patents.

    Attributes:
        name_key (str): The folded name identifying the inventor (two spellings are two profiles).
        name (str): The name as printed.
        publications (int): The publications naming the inventor.
        families (int): Their patent families.
        first_priority (Optional[date]): The earliest priority date.
        last_priority (Optional[date]): The latest priority date.
        companies (List[str]): The companies whose patents name the inventor.
        top_cpc (Optional[str]): The main CPC classes.
        co_inventors (int): The other inventors named with them.
        citations_received (int): The citations their publications received.
    """

    model_config = ConfigDict(frozen=True)

    name_key: str = Field(min_length=1, description="The folded name.")
    name: str = Field(min_length=1, description="The name as printed.")
    publications: int = Field(default=0, ge=0, description="The publications.")
    families: int = Field(default=0, ge=0, description="The patent families.")
    first_priority: Optional[date] = Field(default=None, description="The earliest priority date.")
    last_priority: Optional[date] = Field(default=None, description="The latest priority date.")
    companies: List[str] = Field(default_factory=list, description="The companies.")
    top_cpc: Optional[str] = Field(default=None, description="The main CPC classes.")
    co_inventors: int = Field(default=0, ge=0, description="The co-inventors.")
    citations_received: int = Field(default=0, ge=0, description="The citations received.")

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: a list, or the comma-separated text of the database.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies, in their order.
        """
        if isinstance(value, str):
            companies: List[JsonValue] = []
            companies.extend(part.strip() for part in value.split(",") if part.strip())
            return companies
        if value is None:
            return []
        return value
