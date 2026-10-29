from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.storage.records.enums import RecordSort


class RecordQuery(BaseModel):
    """A page of stored research records to read: the companies, a text, the order and the page bounds.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key.
        companies (List[str]): Only the records of these companies, every company when empty.
        text (Optional[str]): Text contained in the title, the name or the identifier, case-insensitive.
        sort (Optional[RecordSort]): The column sorted by, the dataset's own order when `None` or not one of its
            columns.
        descending (bool): Whether the order is descending.
        offset (int): The records skipped before the page.
        limit (int): The largest number of records of the page.
        with_total (bool): Whether the records matching are counted (the first page only, it costs a count).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    model_config = ConfigDict(frozen=True)

    companies: List[str] = Field(default_factory=list, description="Only these companies.")
    text: Optional[str] = Field(default=None, max_length=200, description="Text contained.")
    sort: Optional[RecordSort] = Field(default=None, description="The column sorted by.")
    descending: bool = Field(default=True, description="Whether the order is descending.")
    offset: int = Field(default=0, ge=0, description="The records skipped.")
    limit: int = Field(default=200, ge=1, le=5000, description="The largest number of records.")
    with_total: bool = Field(default=True, description="Whether the records matching are counted.")

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: kebab-case keys, each once, in their order.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The keys, each once.
        """
        if isinstance(value, list):
            keys: List[JsonValue] = [*dict.fromkeys(str(item).strip().lower() for item in value)]
            return [key for key in keys if isinstance(key, str) and cls.KEY.match(key)]
        return value

    @field_validator("text", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate the raw text: trimmed, none when blank.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, `None` when blank.
        """
        if isinstance(value, str):
            text = " ".join(value.split())
            return text or None
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def page(self, offset: int, limit: Optional[int] = None) -> RecordQuery:
        """Get the same query for another page, without the count.

        Args:
            offset (int): The records skipped.
            limit (Optional[int]): The largest number of records, the same by default.

        Returns:
            RecordQuery: The query of the page.
        """
        return self.model_copy(update={"offset": offset, "limit": limit or self.limit, "with_total": False})
