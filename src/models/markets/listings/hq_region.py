from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class HqRegion(BaseModel):
    """A region the listed companies are grouped by, from the country of their headquarters (US, UK, EU, China…).

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: lower-case words joined by hyphens.
        COUNTRY (ClassVar[Pattern[str]]): The format of a country: ISO 3166-1 alpha-2, upper case.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): Its key, e.g. `eu`.
        label (str): Its name, e.g. `European Union`.
        countries (List[str]): The countries of the headquarters it groups.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key.")
    label: str = Field(min_length=1, description="Its name.")
    countries: List[str] = Field(min_length=1, description="The countries of the headquarters it groups.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "region key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("region key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: a text of 1 to 80 characters, single-spaced.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 80 characters.
        """
        return cls.CHECK.text(value, "region name", 80)

    @field_validator("countries", mode="before")
    def validate_countries(cls, value: JsonValue) -> JsonValue:
        """Validate the raw countries: upper-case ISO codes, each once.

        Args:
            value (JsonValue): The raw countries.

        Returns:
            JsonValue: The countries, upper-cased, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketValueError: If a country is not a two-letter code.
        """
        countries: List[JsonValue] = []
        for item in cls.CHECK.items(value, "region countries", "two-letter country codes"):
            code = item.strip().upper() if isinstance(item, str) else ""
            if not cls.COUNTRY.match(code):
                raise InvalidMarketValueError("region country", str(item), "a two-letter country code")
            if code not in countries:
                countries.append(code)
        return countries
