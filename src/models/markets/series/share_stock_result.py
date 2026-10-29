from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.enums import CorrelationCounterpart, Granularity
from models.markets.exception import InvalidMarketListError
from models.markets.field_check import MarketFieldCheck
from models.markets.series.coverage_entry import CoverageEntry
from models.markets.series.lag_correlation import LagCorrelation


class ShareStockResult(BaseModel):
    """Whether a company's market share and another series (its stock by default) move together, and which leads.

    Attributes:
        TEXTS (ClassVar[Dict[str, int]]): The longest text of each text field.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company of the chronology.
        segment (str): The segment of the shares.
        area (str): The area of the shares.
        device (str): The devices of the shares.
        listing (Optional[str]): The listing of the returns (the company's primary one), `None` when it has none or
            the counterpart is not its stock.
        counterpart (CorrelationCounterpart): What the share changes are correlated with.
        counterpart_label (Optional[str]): The name of that series, e.g. `NASDAQ:GOOGL` or `DRAM concentration`.
        granularity (Granularity): The period of the analysis: the month, or the quarter of the analyst releases.
        share_coverage (Optional[CoverageEntry]): The points of the share series.
        stock_coverage (Optional[CoverageEntry]): The points of the counterpart series (the returns of a stock).
        lags (List[LagCorrelation]): The correlation of the share changes with the counterpart's changes, by lag.
        share_leads_p (Optional[float]): The Granger p-value of "the share changes predict the counterpart's".
        stock_leads_p (Optional[float]): The Granger p-value of "the counterpart's changes predict the share's".
        granger_lags (int): The periods of past used by the Granger tests.
        refusal (Optional[str]): Why nothing was computed (too few points, no listing), `None` when computed.
    """

    TEXTS: ClassVar[Dict[str, int]] = {
        "company": 40,
        "segment": 40,
        "area": 12,
        "device": 8,
        "listing": 30,
        "counterpart_label": 120,
        "refusal": 600,
    }
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(min_length=1, description="The company.")
    segment: str = Field(min_length=1, description="The segment of the shares.")
    area: str = Field(min_length=1, description="The area of the shares.")
    device: str = Field(min_length=1, description="The devices of the shares.")
    listing: Optional[str] = Field(default=None, description="The listing of the returns.")
    counterpart: CorrelationCounterpart = Field(
        default=CorrelationCounterpart.STOCK, description="What the share changes are correlated with."
    )
    counterpart_label: Optional[str] = Field(default=None, description="The name of that series.")
    granularity: Granularity = Field(default=Granularity.MONTH, description="The period of the analysis.")
    share_coverage: Optional[CoverageEntry] = Field(default=None, description="The points of the share series.")
    stock_coverage: Optional[CoverageEntry] = Field(default=None, description="The points of the return series.")
    lags: List[LagCorrelation] = Field(default_factory=list, description="The correlation by lag.")
    share_leads_p: Optional[float] = Field(default=None, ge=0, le=1, description="Share changes lead returns.")
    stock_leads_p: Optional[float] = Field(default=None, ge=0, le=1, description="Returns lead share changes.")
    granger_lags: int = Field(default=3, ge=1, le=12, description="The periods of past of the Granger tests.")
    refusal: Optional[str] = Field(default=None, description="Why nothing was computed.")

    @field_validator("company", "segment", "area", "device", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw company, segment, area or device: a text within its length.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"correlation {name}", cls.TEXTS[name], collapse=False)

    @field_validator("listing", "counterpart_label", "refusal", mode="before")
    def validate_optional_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw listing, counterpart label or refusal: a text within its length, `None` when missing.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text of the right length.
        """
        name = str(info.field_name)
        return cls.CHECK.text(value, f"correlation {name}", cls.TEXTS[name], optional=True)

    @field_validator("granularity", mode="before")
    def validate_granularity(cls, value: JsonValue) -> JsonValue:
        """Validate the raw period of the analysis: a `Granularity` value.

        Args:
            value (JsonValue): The raw period.

        Returns:
            JsonValue: The period.

        Raises:
            InvalidMarketChoiceError: If it is not a known granularity.
        """
        return cls.CHECK.choice(value, "correlation period", [granularity.value for granularity in Granularity])

    @field_validator("counterpart", mode="before")
    def validate_counterpart(cls, value: JsonValue) -> JsonValue:
        """Validate the raw counterpart: a `CorrelationCounterpart` value.

        Args:
            value (JsonValue): The raw counterpart.

        Returns:
            JsonValue: The counterpart.

        Raises:
            InvalidMarketChoiceError: If it is not a known counterpart.
        """
        return cls.CHECK.choice(value, "correlation counterpart", [kind.value for kind in CorrelationCounterpart])

    @field_validator("share_coverage", "stock_coverage", mode="before")
    def validate_coverage(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw coverage: a coverage (or its fields), or none.

        Args:
            value (JsonValue): The raw coverage.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The coverage (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is neither missing, a coverage nor a mapping.
        """
        if value is None or isinstance(value, (dict, CoverageEntry)):
            return value
        raise InvalidMarketListError(f"correlation {info.field_name}", "a coverage entry")

    @field_validator("lags", mode="before")
    def validate_lags(cls, value: JsonValue) -> JsonValue:
        """Validate the raw lags: a list of correlations (or of their fields).

        Args:
            value (JsonValue): The raw lags.

        Returns:
            JsonValue: The lags (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is not a list of correlations.
        """
        lags = cls.CHECK.items(value, "correlation lags", "lag correlations")
        if not all(isinstance(lag, (dict, LagCorrelation)) for lag in lags):
            raise InvalidMarketListError("correlation lags", "a list of lag correlations")
        return lags

    @field_validator("share_leads_p", "stock_leads_p", mode="before")
    def validate_probability(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw Granger p-value: a number from 0 to 1, or none.

        Args:
            value (JsonValue): The raw p-value.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The p-value.

        Raises:
            InvalidMarketNumberError: If it is neither missing nor a number from 0 to 1.
        """
        return cls.CHECK.number(value, f"Granger {info.field_name}", low=0, high=1, optional=True)

    @field_validator("granger_lags", mode="before")
    def validate_granger_lags(cls, value: JsonValue) -> JsonValue:
        """Validate the raw Granger past: a whole number from 1 to 12.

        Args:
            value (JsonValue): The raw count.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number from 1 to 12.
        """
        return cls.CHECK.number(value, "Granger lags", low=1, high=12, integer=True)
