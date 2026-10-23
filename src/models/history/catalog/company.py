from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.history.exception import InvalidHistoryKeyError


class Company(BaseModel):
    """A company of the computing chronology: a leader, or a party to a notable event.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: lower-case words joined by hyphens.
        COLOR (ClassVar[Pattern[str]]): The format of a colour: `#rrggbb`.
        COUNTRY (ClassVar[Pattern[str]]): The format of a country: ISO 3166-1 alpha-2, upper case.
        key (str): Its key, e.g. `ibm`.
        label (str): Its name, e.g. `IBM`.
        color (str): The colour of its bands, `#rrggbb`.
        provider (Optional[CloudProvider]): The cloud provider it runs, if any (its bands then take the provider's
            colour, as everywhere else in the explorer).
        country (Optional[str]): The country of its headquarters, ISO 3166-1 alpha-2 (its stock region).
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    COLOR: ClassVar[Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")
    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key.")
    label: str = Field(min_length=1, description="Its name.")
    color: str = Field(description="The colour of its bands.")
    provider: Optional[CloudProvider] = Field(default=None, description="The cloud provider it runs, if any.")
    country: Optional[str] = Field(default=None, description="The country of its headquarters.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidHistoryKeyError: If it is not lower-case words joined by hyphens.
        """
        if not isinstance(value, str):
            return value
        key = value.strip()
        if not cls.KEY.match(key):
            raise InvalidHistoryKeyError("company key", value, "lower-case words joined by hyphens")
        return key

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw name: trimmed.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name.
        """
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("color", mode="before")
    def validate_color(cls, value: JsonValue) -> JsonValue:
        """Validate the raw colour: `#rrggbb`, lower-cased.

        Args:
            value (JsonValue): The raw colour.

        Returns:
            JsonValue: The colour.

        Raises:
            InvalidHistoryKeyError: If it is not written `#rrggbb`.
        """
        if not isinstance(value, str):
            return value
        color = value.strip().lower()
        if not cls.COLOR.match(color):
            raise InvalidHistoryKeyError("company colour", value, "#rrggbb")
        return color

    @field_validator("country", mode="before")
    def validate_country(cls, value: JsonValue) -> JsonValue:
        """Validate the raw country: an ISO 3166-1 alpha-2 code, upper-cased.

        Args:
            value (JsonValue): The raw country.

        Returns:
            JsonValue: The country.

        Raises:
            InvalidHistoryKeyError: If it is not a two-letter code.
        """
        if not isinstance(value, str):
            return value
        country = value.strip().upper()
        if not cls.COUNTRY.match(country):
            raise InvalidHistoryKeyError("company country", value, "a two-letter country code")
        return country
