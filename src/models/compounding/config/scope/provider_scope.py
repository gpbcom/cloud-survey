from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.exception import InvalidCompoundingValueError
from models.markets.field_check import MarketFieldCheck


class ProviderScope(BaseModel):
    """A public-cloud provider analysed, with the year its public cloud started.

    Attributes:
        URL (ClassVar[Pattern[str]]): The format of a source.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        provider (CloudProvider): The catalogue provider.
        start (Optional[int]): The first year of its public cloud, `None` to start at its first dated product.
        source (Optional[str]): The document giving the start year.

    Notes:
        A product dated before the start is counted as held at the start, not as a launch.
    """

    URL: ClassVar[Pattern[str]] = re.compile(r"^https?://\S+$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The catalogue provider.")
    start: Optional[int] = Field(default=None, description="The first year of its public cloud.")
    source: Optional[str] = Field(default=None, description="The document giving the start year.")

    @field_validator("start", mode="before")
    def validate_start(cls, value: JsonValue) -> JsonValue:
        """Validate the raw start year: a year between 1990 and 2100, or nothing.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year.

        Raises:
            InvalidMarketNumberError: If it is not a whole year in range.
        """
        return cls.CHECK.number(value, "start year", low=1990, high=2100, optional=True, integer=True)

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a web address, or nothing.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompoundingValueError: If it is not a web address.
        """
        source = cls.CHECK.text(value, "start source", 500, optional=True)
        if source is not None and not cls.URL.match(source):
            raise InvalidCompoundingValueError("start source", source, "a web address")
        return source
