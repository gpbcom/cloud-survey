from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, Dict, Optional, Union

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class ItemVersion(BaseModel):
    """A stored version of a catalogue product or a marketplace software: its content as a crawl found it.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        crawl_id (int): The crawl which found the version.
        recorded_at (AwareDatetime): When the crawl found the version (the start of the crawl).
        crawl_status (Optional[str]): The outcome of the crawl (see `CrawlStatus`), `None` when the crawl is unknown.
        content (Dict[str, JsonValue]): The item without its dates and its categories, as JSON.

    Notes:
        A version is written when an item is new or its content changed, at most once per crawl.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    crawl_id: int = Field(ge=1, description="The crawl which found the version.")
    recorded_at: AwareDatetime = Field(description="When the crawl found the version.")
    crawl_status: Optional[str] = Field(default=None, description="The outcome of the crawl.")
    content: Dict[str, JsonValue] = Field(default_factory=dict, description="The item content, as JSON.")

    @field_validator("crawl_id", mode="before")
    def validate_crawl_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw crawl identifier: a whole number of at least 1.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The identifier.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 1.
        """
        return cls.CHECK.number(value, "version crawl", low=1, integer=True)

    @field_validator("recorded_at", mode="before")
    def validate_recorded_at(cls, value: Union[JsonValue, datetime]) -> Union[JsonValue, datetime]:
        """Validate the raw recording date: a date-time, or an ISO text trimmed.

        Args:
            value (Union[JsonValue, datetime]): The raw date.

        Returns:
            Union[JsonValue, datetime]: The date (its time zone is checked by pydantic afterwards).
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("crawl_status", mode="before")
    def validate_crawl_status(cls, value: JsonValue) -> JsonValue:
        """Validate the raw crawl status: a text of 1 to 20 characters, or nothing.

        Args:
            value (JsonValue): The raw status.

        Returns:
            JsonValue: The status, `None` when missing or blank.

        Raises:
            InvalidMarketTextError: If it is not a text of that length.
        """
        return cls.CHECK.text(value, "version crawl status", 20, optional=True)

    @field_validator("content", mode="before")
    def validate_content(cls, value: JsonValue) -> JsonValue:
        """Validate the raw content: a JSON object, nothing standing for an empty one.

        Args:
            value (JsonValue): The raw content.

        Returns:
            JsonValue: The content (its type is checked by pydantic afterwards).
        """
        return {} if value is None else value
