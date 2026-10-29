from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.compounding.exception import InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class HelpEntry(BaseModel):
    """The explanation of a control, a choice, a column, a warning, a verdict, a curve or a card.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        key (str): What is explained (an enum value).
        title (str): Its short name, shown as a label.
        text (str): What it means and how it is computed, in plain words.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="What is explained.")
    title: str = Field(description="Its short name.")
    text: str = Field(description="What it means.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: a kebab-case enum value.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not kebab-case.
        """
        key = cls.CHECK.text(value, "help key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidCompoundingValueError("help key", key, "a kebab-case value")
        return key

    @field_validator("title", mode="before")
    def validate_title(cls, value: JsonValue) -> JsonValue:
        """Validate the raw title: a text of 1 to 60 characters.

        Args:
            value (JsonValue): The raw title.

        Returns:
            JsonValue: The title.

        Raises:
            InvalidMarketTextError: If it is not a text of that length.
        """
        return cls.CHECK.text(value, "help title", 60)

    @field_validator("text", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate the raw text: a text of 10 to 900 characters.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is not a text of that length.
        """
        return cls.CHECK.text(value, "help text", 900, minimum=10)
