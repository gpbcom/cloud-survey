from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Dict, Optional, Pattern, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import Granularity
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class ManualShare(BaseModel):
    """A market share of the source dossier, typed in the catalogue: the shares no crawled source gives (pre-2009).

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a segment or company key: lower-case words joined by hyphens.
        PERIOD (ClassVar[Pattern[str]]): The format of a period: `YYYY`, `YYYYQn` or `YYYY-MM`.
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        segment (str): The segment, e.g. `mainframes`.
        area (str): The area, e.g. `US` or `ww`.
        period (str): The period, `1961`, `2026Q2` or `2026-09`.
        label (str): The company as the source names it, e.g. `IBM PC`.
        company (Optional[str]): The company of the chronology, `None` for an aggregate.
        value (float): The share, in percent.
        source (str): The source of the dossier, e.g. `Fisher-McKie-Mancke via Cato 1985`.
        tag (str): The dossier's reliability tag: `A` academic, `I` analyst, `B` blog…

    Notes:
        They are stored with the source `manual` and drawn as dots. A segment's own source wins where both give a
        company's share for the same period.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    PERIOD: ClassVar[Pattern[str]] = re.compile(r"^(\d{4})(?:Q([1-4])|-(0[1-9]|1[0-2]))?$")
    TEXTS: ClassVar[Dict[str, int]] = {"label": 80, "source": 120, "tag": 8}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    segment: str = Field(description="The segment.")
    area: str = Field(min_length=2, max_length=12, description="The area.")
    period: str = Field(description="The period, YYYY, YYYYQn or YYYY-MM.")
    label: str = Field(min_length=1, max_length=80, description="The company, as named.")
    company: Optional[str] = Field(default=None, description="The company of the chronology.")
    value: float = Field(ge=0, le=100, description="The share, in percent.")
    source: str = Field(min_length=1, max_length=120, description="The source of the dossier.")
    tag: str = Field(min_length=1, max_length=8, description="The reliability tag.")

    @field_validator("segment", "company", mode="before")
    def validate_key(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw segment or company: lower-case words joined by hyphens (the company may be missing).

        Args:
            value (JsonValue): The raw key.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        name = str(info.field_name)
        key = cls.CHECK.text(value, f"manual share {name}", 40, optional=name == "company")
        if key is not None and not cls.KEY.match(key):
            raise InvalidMarketValueError(f"manual share {name}", key, "lower-case words joined by hyphens")
        return key

    @field_validator("area", mode="before")
    def validate_area(cls, value: JsonValue) -> JsonValue:
        """Validate the raw area: a text of 2 to 12 characters.

        Args:
            value (JsonValue): The raw area.

        Returns:
            JsonValue: The area, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of 2 to 12 characters.
        """
        return cls.CHECK.text(value, "manual share area", 12, minimum=2)

    @field_validator("period", mode="before")
    def validate_period(cls, value: JsonValue) -> JsonValue:
        """Validate the raw period: `YYYY`, `YYYYQn` or `YYYY-MM` (a year may be a number).

        Args:
            value (JsonValue): The raw period.

        Returns:
            JsonValue: The period, as text.

        Raises:
            InvalidMarketTextError: If it is not a text nor a year.
            InvalidMarketValueError: If it is not written `YYYY`, `YYYYQn` or `YYYY-MM`.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        period = (cls.CHECK.text(value, "manual share period", 7) or "").upper()
        if not cls.PERIOD.match(period):
            raise InvalidMarketValueError("manual share period", period, "YYYY, YYYYQn or YYYY-MM")
        return period

    @field_validator("label", "source", "tag", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: single-spaced, within its length.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"manual share {name}", cls.TEXTS[name])

    @field_validator("value", mode="before")
    def validate_value(cls, value: JsonValue) -> JsonValue:
        """Validate the raw share: a number from 0 to 100.

        Args:
            value (JsonValue): The raw share.

        Returns:
            JsonValue: The share.

        Raises:
            InvalidMarketNumberError: If it is not a number from 0 to 100.
        """
        return cls.CHECK.number(value, "manual share value", low=0, high=100)

    ############################
    # Publicly Exposed Methods #
    ############################

    def start(self) -> Tuple[date, Granularity]:
        """Get the first day of the period and its kind.

        Returns:
            Tuple[date, Granularity]: `1961` is a year from 1961-01-01, `2026Q2` a quarter from 2026-04-01, `2026-09` a
                month from 2026-09-01.
        """
        found = self.PERIOD.match(self.period)
        year = int(found.group(1)) if found else 1900
        if found and found.group(2):
            return date(year, 3 * int(found.group(2)) - 2, 1), Granularity.QUARTER
        if found and found.group(3):
            return date(year, int(found.group(3)), 1), Granularity.MONTH
        return date(year, 1, 1), Granularity.YEAR
