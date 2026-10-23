from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import AreaKind
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class MarketArea(BaseModel):
    """A geographic area the market shares are measured in: the world, a continent, a country or a union.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: 2 to 12 letters, digits or hyphens.
        COUNTRY (ClassVar[Pattern[str]]): The format of a member country: ISO 3166-1 alpha-2, upper case.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): Its key, which is also its StatCounter region code: `ww`, a continent (`eu`, `na`, `as`, `af`,
            `oc`, `sa`) or an upper-case country code (`US`, `GB`). A union has its own key, e.g. `eu27`.
        label (str): Its name, e.g. `United Kingdom`.
        kind (AreaKind): Whether it is the world, a continent, a country or a union.
        members (List[str]): The member countries of a union, none otherwise.

    Notes:
        StatCounter has no figure for a union of countries: the shares of a union (the EU-27) are estimated from the
        shares of its members, weighted by their internet users, and flagged as an estimate wherever they show.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[A-Za-z0-9-]{2,12}$")
    COUNTRY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key, its StatCounter region code.")
    label: str = Field(min_length=1, description="Its name.")
    kind: AreaKind = Field(description="The kind of area.")
    members: List[str] = Field(default_factory=list, description="The member countries of a union.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: 2 to 12 letters, digits or hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not 2 to 12 letters, digits or hyphens.
        """
        key = cls.CHECK.text(value, "area key", 12) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("area key", key, "2 to 12 letters, digits or hyphens")
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
        return cls.CHECK.text(value, "area name", 80)

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: JsonValue) -> JsonValue:
        """Validate the raw kind: an `AreaKind` value.

        Args:
            value (JsonValue): The raw kind.

        Returns:
            JsonValue: The kind.

        Raises:
            InvalidMarketChoiceError: If it is not a known kind of area.
        """
        return cls.CHECK.choice(value, "area kind", [kind.value for kind in AreaKind])

    @field_validator("members", mode="before")
    def validate_members(cls, value: JsonValue) -> JsonValue:
        """Validate the raw member countries: upper-case ISO codes, each once.

        Args:
            value (JsonValue): The raw member countries.

        Returns:
            JsonValue: The members, upper-cased, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketValueError: If a member is not a two-letter country code.
        """
        members: List[JsonValue] = []
        for item in cls.CHECK.items(value, "member countries", "two-letter country codes"):
            code = item.strip().upper() if isinstance(item, str) else ""
            if not cls.COUNTRY.match(code):
                raise InvalidMarketValueError("member country", str(item), "a two-letter country code")
            if code not in members:
                members.append(code)
        return members
