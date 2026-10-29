from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import CorrelationCounterpart, ShareSource
from models.markets.field_check import MarketFieldCheck


class Counterpart(BaseModel):
    """What a company's share changes are correlated with, as the "Against" list of the correlation card offers it.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        kind (CorrelationCounterpart): The kind of series.
        label (str): Its display name, e.g. `NASDAQ:GOOGL` or `Smartphones · Worldwide · IDC`.
        segment (Optional[str]): The segment of a share or a context series.
        area (Optional[str]): The area of a share series.
        source (Optional[ShareSource]): The source of a share or a context series.
        listing (Optional[str]): The listing of a stock series.
        currency (Optional[str]): The currency of a currency series (ISO 4217).

    Notes:
        A stock series names its listing, a share series its segment, area and source, a currency series its
        currency, a context series its segment (TrendForce): the fields of the other kinds stay empty.
    """

    TEXTS: ClassVar[Dict[str, int]] = {"label": 120, "segment": 40, "area": 12, "listing": 30, "currency": 3}
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: CorrelationCounterpart = Field(description="The kind of series.")
    label: str = Field(min_length=1, max_length=120, description="Its display name.")
    segment: Optional[str] = Field(default=None, description="The segment of a share or a context series.")
    area: Optional[str] = Field(default=None, description="The area of a share series.")
    source: Optional[ShareSource] = Field(default=None, description="The source of a share or a context series.")
    listing: Optional[str] = Field(default=None, description="The listing of a stock series.")
    currency: Optional[str] = Field(default=None, description="The currency of a currency series.")

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: JsonValue) -> JsonValue:
        """Validate the raw kind: a `CorrelationCounterpart` value.

        Args:
            value (JsonValue): The raw kind.

        Returns:
            JsonValue: The kind.

        Raises:
            InvalidMarketChoiceError: If it is not a known kind.
        """
        return cls.CHECK.choice(value, "counterpart kind", [kind.value for kind in CorrelationCounterpart])

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw label: a text of 1 to 120 characters.

        Args:
            value (JsonValue): The raw label.

        Returns:
            JsonValue: The label, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        return cls.CHECK.text(value, "counterpart label", cls.TEXTS["label"])

    @field_validator("segment", "area", "listing", "currency", mode="before")
    def validate_optional_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw segment, area, listing or currency: a text within its length, `None` when missing.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, trimmed.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"counterpart {name}", cls.TEXTS[name], optional=True)

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a `ShareSource` value, `None` when missing.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketChoiceError: If it is neither missing nor a known source.
        """
        return cls.CHECK.choice(value, "counterpart source", [source.value for source in ShareSource], optional=True)
