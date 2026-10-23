from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import ValuationKind
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class ValuationPoint(BaseModel):
    """A sourced valuation of a company on a date: an IPO, an acquisition, a market cap or a private round.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key: lower-case words joined by hyphens.
        DATE (ClassVar[Pattern[str]]): The format of a date: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company of the chronology.
        date (str): When, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        kind (ValuationKind): What the figure is.
        value_bn (float): The value, in billions of US dollars (the low end of a published range).
        high_bn (Optional[float]): The high end of a published range, if any.
        label (str): What happened, e.g. `To Compaq`.
        source (str): The source of the dossier, e.g. `DEC 8-K`.
        tag (str): The dossier's reliability tag: `P` primary, `J` journalistic, `B` blog or aggregator…

    Notes:
        These points stand for the companies without a
        price history (delisted, acquired or private) and for the
        dossier's market caps. They are drawn as dots, never
        correlated: they are too sparse.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    DATE: ClassVar[Pattern[str]] = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
    TEXTS: ClassVar[Dict[str, int]] = {"label": 120, "source": 120, "tag": 8}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company.")
    date: str = Field(description="When.")
    kind: ValuationKind = Field(description="What the figure is.")
    value_bn: float = Field(gt=0, description="The value, in billions of US dollars.")
    high_bn: Optional[float] = Field(default=None, gt=0, description="The high end of a range.")
    label: str = Field(min_length=1, max_length=120, description="What happened.")
    source: str = Field(min_length=1, max_length=120, description="The source of the dossier.")
    tag: str = Field(min_length=1, max_length=8, description="The reliability tag.")

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a key of the chronology.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The company key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "company key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("company key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("date", mode="before")
    def validate_date(cls, value: JsonValue) -> JsonValue:
        """Validate the raw date: `YYYY`, `YYYY-MM` or `YYYY-MM-DD` (a year may be a number).

        Args:
            value (JsonValue): The raw date.

        Returns:
            JsonValue: The date, as text.

        Raises:
            InvalidMarketTextError: If it is not a text nor a year.
            InvalidMarketValueError: If it is not a valid partial date.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        date = cls.CHECK.text(value, "valuation date", 10) or ""
        if not cls.DATE.match(date):
            raise InvalidMarketValueError("valuation date", date, "YYYY, YYYY-MM or YYYY-MM-DD")
        return date

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: JsonValue) -> JsonValue:
        """Validate the raw kind: a `ValuationKind` value.

        Args:
            value (JsonValue): The raw kind.

        Returns:
            JsonValue: The kind.

        Raises:
            InvalidMarketChoiceError: If it is not a known kind of valuation.
        """
        return cls.CHECK.choice(value, "valuation kind", [kind.value for kind in ValuationKind])

    @field_validator("value_bn", "high_bn", mode="before")
    def validate_value(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw value: a number above zero, in billions (the high end may be missing).

        Args:
            value (JsonValue): The raw value.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The value.

        Raises:
            InvalidMarketNumberError: If it is not a number above zero.
        """
        optional = info.field_name == "high_bn"
        return cls.CHECK.number(value, "valuation in USD bn", low=0.0, strict_low=True, optional=optional)

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
        return cls.CHECK.text(value, f"valuation {name}", cls.TEXTS[name])
