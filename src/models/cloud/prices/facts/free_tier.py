from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from typing import ClassVar, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider, FreeTierKind, PriceSourceKind, PriceUnit
from models.cloud.prices.exception import (
    InvalidConditionsError,
    InvalidCurrencyError,
    InvalidDurationDaysError,
    InvalidFreeKeyError,
    InvalidKindError,
    InvalidPeriodError,
    InvalidProviderError,
    InvalidQuantityError,
    InvalidRegionScopeError,
    InvalidServiceError,
    InvalidSourceKindError,
    InvalidSourceUrlError,
    InvalidUnitError,
    InvalidUnitRawError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class FreeTier(BaseModel):
    """A free offer of a cloud provider: an always-free allowance, a trial or a credit.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        provider (CloudProvider): The cloud provider.
        free_key (str): The key of the offer, stable from crawl to crawl.
        service (str): The service it applies to, `account` for an account-wide credit.
        kind (FreeTierKind): What kind of offer it is.
        quantity (Optional[Decimal]): How much is free (in `unit`), `None` for an unlimited or uncounted offer.
        unit (Optional[PriceUnit]): The unit of the quantity.
        unit_raw (Optional[str]): The unit as the source writes it.
        currency (Optional[str]): The currency of a credit.
        period (Optional[str]): Per what the quantity renews (`month`), `None` once only.
        duration_days (Optional[int]): How long the offer lasts from the account creation, `None` without end.
        region_scope (str): Where it applies, `global` everywhere.
        conditions (Optional[str]): Its conditions (new accounts only, one instance...).
        source_url (str): The page it was read from.
        source_kind (PriceSourceKind): What kind of source it is.

    Notes:
        The free tier of a priced dimension is also a price of 0 for its first units (`ServicePrice.tier_start`): a
        free offer is the account-level view, as the provider advertises it.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The cloud provider.")
    free_key: str = Field(description="The key of the offer.")
    service: str = Field(description="The service.")
    kind: FreeTierKind = Field(description="The kind of offer.")
    quantity: Optional[Decimal] = Field(default=None, description="How much is free.")
    unit: Optional[PriceUnit] = Field(default=None, description="The unit of the quantity.")
    unit_raw: Optional[str] = Field(default=None, description="The unit as written.")
    currency: Optional[str] = Field(default=None, description="The currency of a credit.")
    period: Optional[str] = Field(default=None, description="Per what it renews.")
    duration_days: Optional[int] = Field(default=None, description="How long it lasts.")
    region_scope: str = Field(default="global", description="Where it applies.")
    conditions: Optional[str] = Field(default=None, description="Its conditions.")
    source_url: str = Field(description="The source.")
    source_kind: PriceSourceKind = Field(description="The kind of source.")

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

    @field_validator("free_key", mode="before")
    def validate_free_key(cls, value: RawValue) -> RawValue:
        """Validate the raw free offer key: a text of 1 to 400 characters.

        Args:
            value (RawValue): The raw free offer key.

        Returns:
            RawValue: The checked free offer key.

        Raises:
            InvalidFreeKeyError: If it is not a text of 1 to 400 characters.
        """
        try:
            return cls.CHECK.text(value, 400, collapse=False)
        except PriceCheckError as e:
            raise InvalidFreeKeyError(e.value, e.expected) from e

    @field_validator("service", mode="before")
    def validate_service(cls, value: RawValue) -> RawValue:
        """Validate the raw service: a text of 1 to 300 characters.

        Args:
            value (RawValue): The raw service.

        Returns:
            RawValue: The checked service.

        Raises:
            InvalidServiceError: If it is not a text of 1 to 300 characters.
        """
        try:
            return cls.CHECK.text(value, 300)
        except PriceCheckError as e:
            raise InvalidServiceError(e.value, e.expected) from e

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: RawValue) -> RawValue:
        """Validate the raw free offer kind: a `FreeTierKind` value.

        Args:
            value (RawValue): The raw free offer kind.

        Returns:
            RawValue: The checked free offer kind.

        Raises:
            InvalidKindError: If it is not a `FreeTierKind` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in FreeTierKind])
        except PriceCheckError as e:
            raise InvalidKindError(e.value, e.expected) from e

    @field_validator("quantity", mode="before")
    def validate_quantity(cls, value: RawValue) -> RawValue:
        """Validate the raw quantity: a number from 0, or nothing.

        Args:
            value (RawValue): The raw quantity.

        Returns:
            RawValue: The checked quantity.

        Raises:
            InvalidQuantityError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidQuantityError(e.value, e.expected) from e

    @field_validator("unit", mode="before")
    def validate_unit(cls, value: RawValue) -> RawValue:
        """Validate the raw unit: a `PriceUnit` value, or nothing.

        Args:
            value (RawValue): The raw unit.

        Returns:
            RawValue: The checked unit.

        Raises:
            InvalidUnitError: If it is not a `PriceUnit` value, or nothing.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceUnit], optional=True)
        except PriceCheckError as e:
            raise InvalidUnitError(e.value, e.expected) from e

    @field_validator("unit_raw", mode="before")
    def validate_unit_raw(cls, value: RawValue) -> RawValue:
        """Validate the unit as written: a text of 1 to 120 characters, or nothing.

        Args:
            value (RawValue): The unit as written, raw.

        Returns:
            RawValue: The checked unit as written.

        Raises:
            InvalidUnitRawError: If it is not a text of 1 to 120 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 120, optional=True)
        except PriceCheckError as e:
            raise InvalidUnitRawError(e.value, e.expected) from e

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: RawValue) -> RawValue:
        """Validate the raw currency: an ISO 4217 currency code, or nothing.

        Args:
            value (RawValue): The raw currency.

        Returns:
            RawValue: The checked currency.

        Raises:
            InvalidCurrencyError: If it is not an ISO 4217 currency code, or nothing.
        """
        try:
            return cls.CHECK.currency(value)
        except PriceCheckError as e:
            raise InvalidCurrencyError(e.value, e.expected) from e

    @field_validator("period", mode="before")
    def validate_period(cls, value: RawValue) -> RawValue:
        """Validate the raw renewal period: a text of 1 to 20 characters, or nothing.

        Args:
            value (RawValue): The raw renewal period.

        Returns:
            RawValue: The checked renewal period.

        Raises:
            InvalidPeriodError: If it is not a text of 1 to 20 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 20, optional=True)
        except PriceCheckError as e:
            raise InvalidPeriodError(e.value, e.expected) from e

    @field_validator("duration_days", mode="before")
    def validate_duration_days(cls, value: RawValue) -> RawValue:
        """Validate the raw duration: a whole number above 0, or nothing.

        Args:
            value (RawValue): The raw duration.

        Returns:
            RawValue: The checked duration.

        Raises:
            InvalidDurationDaysError: If it is not a whole number above 0, or nothing.
        """
        try:
            return cls.CHECK.whole(value, positive=True, optional=True)
        except PriceCheckError as e:
            raise InvalidDurationDaysError(e.value, e.expected) from e

    @field_validator("region_scope", mode="before")
    def validate_region_scope(cls, value: RawValue) -> RawValue:
        """Validate the raw region scope: a text of 1 to 80 characters.

        Args:
            value (RawValue): The raw region scope.

        Returns:
            RawValue: The checked region scope.

        Raises:
            InvalidRegionScopeError: If it is not a text of 1 to 80 characters.
        """
        try:
            return cls.CHECK.text(value, 80)
        except PriceCheckError as e:
            raise InvalidRegionScopeError(e.value, e.expected) from e

    @field_validator("conditions", mode="before")
    def validate_conditions(cls, value: RawValue) -> RawValue:
        """Validate the raw conditions: a text of 1 to 1000 characters, or nothing.

        Args:
            value (RawValue): The raw conditions.

        Returns:
            RawValue: The checked conditions.

        Raises:
            InvalidConditionsError: If it is not a text of 1 to 1000 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 1000, optional=True)
        except PriceCheckError as e:
            raise InvalidConditionsError(e.value, e.expected) from e

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: RawValue) -> RawValue:
        """Validate the raw source URL: an http or https URL.

        Args:
            value (RawValue): The raw source URL.

        Returns:
            RawValue: The checked source URL.

        Raises:
            InvalidSourceUrlError: If it is not an http or https URL.
        """
        try:
            return cls.CHECK.url(value)
        except PriceCheckError as e:
            raise InvalidSourceUrlError(e.value, e.expected) from e

    @field_validator("source_kind", mode="before")
    def validate_source_kind(cls, value: RawValue) -> RawValue:
        """Validate the raw source kind: a `PriceSourceKind` value.

        Args:
            value (RawValue): The raw source kind.

        Returns:
            RawValue: The checked source kind.

        Raises:
            InvalidSourceKindError: If it is not a `PriceSourceKind` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceSourceKind])
        except PriceCheckError as e:
            raise InvalidSourceKindError(e.value, e.expected) from e
