from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.cloud.prices.exception import (
    InvalidBreakdownError,
    InvalidComputedAtError,
    InvalidCurrencyError,
    InvalidMonthlyTotalError,
    InvalidOptionsError,
    InvalidProfileError,
    InvalidProviderError,
    InvalidRegionError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class PriceQuote(BaseModel):
    """The monthly cost of a usage profile at a provider, in a region: a cached result of the workload costing.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        profile (str): The usage profile.
        provider (CloudProvider): The cloud provider.
        region (str): The region priced.
        options (str): The options of the costing (free tiers, commitment), as a key.
        currency (str): The currency of the total.
        monthly_total (Optional[Decimal]): The monthly cost, `None` when an item has no candidate.
        breakdown (List[Dict[str, JsonValue]]): The cost of each item: the price chosen, the quantity, the cost.
        computed_at (Optional[datetime]): When it was computed, set when it is written.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str = Field(description="The usage profile.")
    provider: CloudProvider = Field(description="The cloud provider.")
    region: str = Field(description="The region priced.")
    options: str = Field(default="default", description="The options, as a key.")
    currency: str = Field(description="The currency of the total.")
    monthly_total: Optional[Decimal] = Field(default=None, description="The monthly cost.")
    breakdown: List[Dict[str, JsonValue]] = Field(default_factory=list, description="The cost of each item.")
    computed_at: Optional[datetime] = Field(default=None, description="When it was computed.")

    @field_validator("profile", mode="before")
    def validate_profile(cls, value: RawValue) -> RawValue:
        """Validate the raw quote profile: a text of 1 to 120 characters.

        Args:
            value (RawValue): The raw quote profile.

        Returns:
            RawValue: The checked quote profile.

        Raises:
            InvalidProfileError: If it is not a text of 1 to 120 characters.
        """
        try:
            return cls.CHECK.text(value, 120)
        except PriceCheckError as e:
            raise InvalidProfileError(e.value, e.expected) from e

    @field_validator("provider", mode="before")
    def validate_provider(cls, value: RawValue) -> RawValue:
        """Validate the raw cloud provider: a `CloudProvider` value.

        Args:
            value (RawValue): The raw cloud provider.

        Returns:
            RawValue: The checked cloud provider.

        Raises:
            InvalidProviderError: If it is not a `CloudProvider` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in CloudProvider])
        except PriceCheckError as e:
            raise InvalidProviderError(e.value, e.expected) from e

    @field_validator("region", mode="before")
    def validate_region(cls, value: RawValue) -> RawValue:
        """Validate the raw region: a text of 1 to 80 characters.

        Args:
            value (RawValue): The raw region.

        Returns:
            RawValue: The checked region.

        Raises:
            InvalidRegionError: If it is not a text of 1 to 80 characters.
        """
        try:
            return cls.CHECK.text(value, 80)
        except PriceCheckError as e:
            raise InvalidRegionError(e.value, e.expected) from e

    @field_validator("options", mode="before")
    def validate_options(cls, value: RawValue) -> RawValue:
        """Validate the raw costing options: a text of 1 to 120 characters.

        Args:
            value (RawValue): The raw costing options.

        Returns:
            RawValue: The checked costing options.

        Raises:
            InvalidOptionsError: If it is not a text of 1 to 120 characters.
        """
        try:
            return cls.CHECK.text(value, 120)
        except PriceCheckError as e:
            raise InvalidOptionsError(e.value, e.expected) from e

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: RawValue) -> RawValue:
        """Validate the raw currency: an ISO 4217 currency code.

        Args:
            value (RawValue): The raw currency.

        Returns:
            RawValue: The checked currency.

        Raises:
            InvalidCurrencyError: If it is not an ISO 4217 currency code.
        """
        try:
            return cls.CHECK.currency(value, optional=False)
        except PriceCheckError as e:
            raise InvalidCurrencyError(e.value, e.expected) from e

    @field_validator("monthly_total", mode="before")
    def validate_monthly_total(cls, value: RawValue) -> RawValue:
        """Validate the raw monthly total: a number from 0, or nothing.

        Args:
            value (RawValue): The raw monthly total.

        Returns:
            RawValue: The checked monthly total.

        Raises:
            InvalidMonthlyTotalError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidMonthlyTotalError(e.value, e.expected) from e

    @field_validator("computed_at", mode="before")
    def validate_computed_at(cls, value: RawValue) -> RawValue:
        """Validate the raw computation time: a date and time with its time zone, or nothing.

        Args:
            value (RawValue): The raw computation time.

        Returns:
            RawValue: The checked computation time.

        Raises:
            InvalidComputedAtError: If it is not a date and time with its time zone, or nothing.
        """
        try:
            return cls.CHECK.moment(value)
        except PriceCheckError as e:
            raise InvalidComputedAtError(e.value, e.expected) from e

    @field_validator("breakdown", mode="before")
    def validate_breakdown(cls, value: RawValue) -> RawValue:
        """Validate the raw cost breakdown: a list of objects, one per item of the profile.

        Args:
            value (RawValue): The raw breakdown.

        Returns:
            RawValue: The checked breakdown.

        Raises:
            InvalidBreakdownError: If it is not a list of objects with text keys.
        """
        try:
            lines: List[JsonValue] = [cls.CHECK.mapping(line) for line in cls.CHECK.items(value)]
        except PriceCheckError as e:
            raise InvalidBreakdownError(e.value, e.expected) from e
        return lines
