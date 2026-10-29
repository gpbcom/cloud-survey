from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class CrawlScope(BaseModel):
    """What a markets crawl reads: every area and listing of the catalogue, or a part of them, since a month.

    Attributes:
        MONTH (ClassVar[Pattern[str]]): The format of a month: `YYYY-MM`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        areas (List[str]): Only these areas (StatCounter), every one when empty.
        listings (List[str]): Only these listings (Google Finance), every one when empty.
        companies (List[str]): Only these companies (the companies crawl), every one when empty.
        since (Optional[str]): Only the months from this one, `YYYY-MM` (StatCounter, FRED), the whole history when
            `None`. A later run reading the last months only is how the stored series are kept up to date.
    """

    MONTH: ClassVar[Pattern[str]] = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    areas: List[str] = Field(default_factory=list, description="Only these areas.")
    listings: List[str] = Field(default_factory=list, description="Only these listings.")
    companies: List[str] = Field(default_factory=list, description="Only these companies.")
    since: Optional[str] = Field(default=None, description="Only the months from this one, YYYY-MM.")

    @field_validator("areas", "listings", "companies", mode="before")
    def validate_keys(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw keys: a comma-separated text is split, each key trimmed and kept once.

        Args:
            value (JsonValue): The raw keys, a list or a comma-separated text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The keys, each once in their order.

        Raises:
            InvalidMarketListError: If it is neither a text nor a list.
            InvalidMarketTextError: If a key is not a text of at most 30 characters.
        """
        parts: List[JsonValue] = [*value.split(",")] if isinstance(value, str) else []
        items = parts if isinstance(value, str) else value
        keys = [
            cls.CHECK.text(item, f"crawl scope {info.field_name} key", 30, optional=True)
            for item in cls.CHECK.items(items, f"crawl scope {info.field_name}", "keys")
        ]
        unique: List[JsonValue] = [*dict.fromkeys(key for key in keys if key)]
        return unique

    @field_validator("since", mode="before")
    def validate_since(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first month: `YYYY-MM`, `None` when blank.

        Args:
            value (JsonValue): The raw month.

        Returns:
            JsonValue: The month.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
            InvalidMarketValueError: If it is not written `YYYY-MM`.
        """
        month = cls.CHECK.text(value, "first month", 7, optional=True)
        if month is not None and not cls.MONTH.match(month):
            raise InvalidMarketValueError("first month", month, "YYYY-MM")
        return month
