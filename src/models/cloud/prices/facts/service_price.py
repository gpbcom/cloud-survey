from __future__ import annotations

# Standard Library Imports.
from datetime import date
from decimal import Decimal
from typing import ClassVar, Dict, FrozenSet, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator, model_validator

# First Party Imports.
from models.cloud.enums import CloudProvider, PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.exception import (
    InconsistentPriceError,
    InvalidAttributesError,
    InvalidBillingIncrementSError,
    InvalidCapturedError,
    InvalidCurrencyError,
    InvalidEffectiveFromError,
    InvalidFamilyError,
    InvalidInstanceTypeError,
    InvalidMemoryGibError,
    InvalidMinimumDurationDaysError,
    InvalidMinimumQuantityError,
    InvalidModelError,
    InvalidOsError,
    InvalidPriceError,
    InvalidProviderError,
    InvalidReasonError,
    InvalidRegionError,
    InvalidServiceError,
    InvalidSkuKeyError,
    InvalidSourceKindError,
    InvalidSourceUrlError,
    InvalidStorageGibError,
    InvalidTermError,
    InvalidTierEndError,
    InvalidTierStartError,
    InvalidUnitError,
    InvalidUnitFactorError,
    InvalidUnitRawError,
    InvalidVcpuError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class ServicePrice(BaseModel):
    """A price of a cloud service as its provider publishes it: one priced dimension, in one region, for one tier.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        provider (CloudProvider): The cloud provider.
        sku_key (str): The key of the priced dimension, stable from crawl to crawl (the provider's SKU, with the
            dimension, term and tier it prices).
        service (str): The service, as the source names it.
        family (Optional[str]): The family of the dimension (compute instance, storage, data transfer...).
        region (str): The region it is priced in, `global` for a price of every region.
        instance_type (Optional[str]): The instance, node or plan type, if any.
        vcpu (Optional[Decimal]): Its virtual CPUs, if any.
        memory_gib (Optional[Decimal]): Its memory, in GiB, if any.
        storage_gib (Optional[Decimal]): Its included storage, in GiB, if any.
        os (Optional[str]): Its operating system or engine, if any.
        attributes (Dict[str, JsonValue]): The other attributes the source states.
        unit (PriceUnit): The normalized unit of the price.
        unit_raw (str): The unit as the source writes it, e.g. `1M requests`.
        unit_factor (Decimal): The normalized units in one raw unit (1,000,000 for `1M requests`): the price of one
            normalized unit is `price / unit_factor`.
        price (Optional[Decimal]): The price of one raw unit, `None` for a service without public price.
        currency (Optional[str]): The currency of the price.
        model (PriceModel): How it is charged, or why there is no price.
        term (PriceTerm): The commitment term.
        tier_start (Decimal): The quantity (in raw units, per billing period) from which this price applies: a free
            tier is a price of 0 from 0.
        tier_end (Optional[Decimal]): The quantity up to which it applies, `None` without upper bound.
        billing_increment_s (Optional[int]): The billing granularity of a time unit, in seconds (60 for per-minute
            billing of an hourly price).
        minimum_quantity (Optional[Decimal]): The least quantity charged.
        minimum_duration_days (Optional[int]): The least storage duration charged (archive classes).
        effective_from (Optional[date]): Since when the source states the price.
        source_url (str): The page or document it was read from.
        source_kind (PriceSourceKind): What kind of source it is.
        captured (Optional[date]): The capture date of an archived source.
        reason (Optional[str]): Why a service has no public price.
        UNPRICED (ClassVar[FrozenSet[PriceModel]]): The models of a service without public price.

    Notes:
        A crawler only reads: the price is streamed as the source states it (its raw unit kept beside the normalized
        one), and `analytics.prices` merges it into the stored prices, which keep its history. Every field has its
        own validator and its own error (`models.cloud.prices.exception`).
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()
    UNPRICED: ClassVar[FrozenSet[PriceModel]] = frozenset(
        {PriceModel.QUOTE, PriceModel.INCLUDED, PriceModel.NOT_PUBLIC}
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The cloud provider.")
    sku_key: str = Field(description="The key of the priced dimension.")
    service: str = Field(description="The service.")
    family: Optional[str] = Field(default=None, description="The family of the dimension.")
    region: str = Field(default="global", description="The region.")
    instance_type: Optional[str] = Field(default=None, description="The instance type.")
    vcpu: Optional[Decimal] = Field(default=None, description="The virtual CPUs.")
    memory_gib: Optional[Decimal] = Field(default=None, description="The memory, in GiB.")
    storage_gib: Optional[Decimal] = Field(default=None, description="The included storage, in GiB.")
    os: Optional[str] = Field(default=None, description="The operating system or engine.")
    attributes: Dict[str, JsonValue] = Field(default_factory=dict, description="The other attributes.")
    unit: PriceUnit = Field(description="The normalized unit.")
    unit_raw: str = Field(description="The unit as written.")
    unit_factor: Decimal = Field(default=Decimal(1), description="The normalized units in a raw unit.")
    price: Optional[Decimal] = Field(default=None, description="The price of a raw unit.")
    currency: Optional[str] = Field(default=None, description="The currency.")
    model: PriceModel = Field(default=PriceModel.ON_DEMAND, description="How it is charged.")
    term: PriceTerm = Field(default=PriceTerm.NONE, description="The commitment term.")
    tier_start: Decimal = Field(default=Decimal(0), description="Where the tier starts.")
    tier_end: Optional[Decimal] = Field(default=None, description="Where the tier ends.")
    billing_increment_s: Optional[int] = Field(default=None, description="The billing granularity, seconds.")
    minimum_quantity: Optional[Decimal] = Field(default=None, description="The least quantity charged.")
    minimum_duration_days: Optional[int] = Field(default=None, description="The least duration charged.")
    effective_from: Optional[date] = Field(default=None, description="Since when the price applies.")
    source_url: str = Field(description="The source.")
    source_kind: PriceSourceKind = Field(description="The kind of source.")
    captured: Optional[date] = Field(default=None, description="The capture date of an archived source.")
    reason: Optional[str] = Field(default=None, description="Why there is no public price.")

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

    @field_validator("sku_key", mode="before")
    def validate_sku_key(cls, value: RawValue) -> RawValue:
        """Validate the raw SKU key: a text of 1 to 400 characters.

        Args:
            value (RawValue): The raw SKU key.

        Returns:
            RawValue: The checked SKU key.

        Raises:
            InvalidSkuKeyError: If it is not a text of 1 to 400 characters.
        """
        try:
            return cls.CHECK.text(value, 400, collapse=False)
        except PriceCheckError as e:
            raise InvalidSkuKeyError(e.value, e.expected) from e

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

    @field_validator("family", mode="before")
    def validate_family(cls, value: RawValue) -> RawValue:
        """Validate the raw price family: a text of 1 to 200 characters, or nothing.

        Args:
            value (RawValue): The raw price family.

        Returns:
            RawValue: The checked price family.

        Raises:
            InvalidFamilyError: If it is not a text of 1 to 200 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 200, optional=True)
        except PriceCheckError as e:
            raise InvalidFamilyError(e.value, e.expected) from e

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

    @field_validator("instance_type", mode="before")
    def validate_instance_type(cls, value: RawValue) -> RawValue:
        """Validate the raw instance type: a text of 1 to 120 characters, or nothing.

        Args:
            value (RawValue): The raw instance type.

        Returns:
            RawValue: The checked instance type.

        Raises:
            InvalidInstanceTypeError: If it is not a text of 1 to 120 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 120, optional=True)
        except PriceCheckError as e:
            raise InvalidInstanceTypeError(e.value, e.expected) from e

    @field_validator("vcpu", mode="before")
    def validate_vcpu(cls, value: RawValue) -> RawValue:
        """Validate the raw virtual CPU count: a number from 0, or nothing.

        Args:
            value (RawValue): The raw virtual CPU count.

        Returns:
            RawValue: The checked virtual CPU count.

        Raises:
            InvalidVcpuError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidVcpuError(e.value, e.expected) from e

    @field_validator("memory_gib", mode="before")
    def validate_memory_gib(cls, value: RawValue) -> RawValue:
        """Validate the raw memory: a number from 0, or nothing.

        Args:
            value (RawValue): The raw memory.

        Returns:
            RawValue: The checked memory.

        Raises:
            InvalidMemoryGibError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidMemoryGibError(e.value, e.expected) from e

    @field_validator("storage_gib", mode="before")
    def validate_storage_gib(cls, value: RawValue) -> RawValue:
        """Validate the raw included storage: a number from 0, or nothing.

        Args:
            value (RawValue): The raw included storage.

        Returns:
            RawValue: The checked included storage.

        Raises:
            InvalidStorageGibError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidStorageGibError(e.value, e.expected) from e

    @field_validator("os", mode="before")
    def validate_os(cls, value: RawValue) -> RawValue:
        """Validate the raw operating system: a text of 1 to 120 characters, or nothing.

        Args:
            value (RawValue): The raw operating system.

        Returns:
            RawValue: The checked operating system.

        Raises:
            InvalidOsError: If it is not a text of 1 to 120 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 120, optional=True)
        except PriceCheckError as e:
            raise InvalidOsError(e.value, e.expected) from e

    @field_validator("attributes", mode="before")
    def validate_attributes(cls, value: RawValue) -> RawValue:
        """Validate the raw attributes: an object with text keys.

        Args:
            value (RawValue): The raw attributes.

        Returns:
            RawValue: The checked attributes.

        Raises:
            InvalidAttributesError: If it is not an object with text keys.
        """
        try:
            return cls.CHECK.mapping(value)
        except PriceCheckError as e:
            raise InvalidAttributesError(e.value, e.expected) from e

    @field_validator("unit", mode="before")
    def validate_unit(cls, value: RawValue) -> RawValue:
        """Validate the raw unit: a `PriceUnit` value.

        Args:
            value (RawValue): The raw unit.

        Returns:
            RawValue: The checked unit.

        Raises:
            InvalidUnitError: If it is not a `PriceUnit` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceUnit])
        except PriceCheckError as e:
            raise InvalidUnitError(e.value, e.expected) from e

    @field_validator("unit_raw", mode="before")
    def validate_unit_raw(cls, value: RawValue) -> RawValue:
        """Validate the unit as written: a text of 1 to 120 characters.

        Args:
            value (RawValue): The unit as written, raw.

        Returns:
            RawValue: The checked unit as written.

        Raises:
            InvalidUnitRawError: If it is not a text of 1 to 120 characters.
        """
        try:
            return cls.CHECK.text(value, 120)
        except PriceCheckError as e:
            raise InvalidUnitRawError(e.value, e.expected) from e

    @field_validator("unit_factor", mode="before")
    def validate_unit_factor(cls, value: RawValue) -> RawValue:
        """Validate the raw unit factor: a number above 0.

        Args:
            value (RawValue): The raw unit factor.

        Returns:
            RawValue: The checked unit factor.

        Raises:
            InvalidUnitFactorError: If it is not a number above 0.
        """
        try:
            return cls.CHECK.number(value, positive=True)
        except PriceCheckError as e:
            raise InvalidUnitFactorError(e.value, e.expected) from e

    @field_validator("price", mode="before")
    def validate_price(cls, value: RawValue) -> RawValue:
        """Validate the raw price: a number from 0, or nothing.

        Args:
            value (RawValue): The raw price.

        Returns:
            RawValue: The checked price.

        Raises:
            InvalidPriceError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidPriceError(e.value, e.expected) from e

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

    @field_validator("model", mode="before")
    def validate_model(cls, value: RawValue) -> RawValue:
        """Validate the raw pricing model: a `PriceModel` value.

        Args:
            value (RawValue): The raw pricing model.

        Returns:
            RawValue: The checked pricing model.

        Raises:
            InvalidModelError: If it is not a `PriceModel` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceModel])
        except PriceCheckError as e:
            raise InvalidModelError(e.value, e.expected) from e

    @field_validator("term", mode="before")
    def validate_term(cls, value: RawValue) -> RawValue:
        """Validate the raw commitment term: a `PriceTerm` value.

        Args:
            value (RawValue): The raw commitment term.

        Returns:
            RawValue: The checked commitment term.

        Raises:
            InvalidTermError: If it is not a `PriceTerm` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceTerm])
        except PriceCheckError as e:
            raise InvalidTermError(e.value, e.expected) from e

    @field_validator("tier_start", mode="before")
    def validate_tier_start(cls, value: RawValue) -> RawValue:
        """Validate the raw tier start: a number from 0.

        Args:
            value (RawValue): The raw tier start.

        Returns:
            RawValue: The checked tier start.

        Raises:
            InvalidTierStartError: If it is not a number from 0.
        """
        try:
            return cls.CHECK.number(value)
        except PriceCheckError as e:
            raise InvalidTierStartError(e.value, e.expected) from e

    @field_validator("billing_increment_s", mode="before")
    def validate_billing_increment_s(cls, value: RawValue) -> RawValue:
        """Validate the raw billing increment: a whole number above 0, or nothing.

        Args:
            value (RawValue): The raw billing increment.

        Returns:
            RawValue: The checked billing increment.

        Raises:
            InvalidBillingIncrementSError: If it is not a whole number above 0, or nothing.
        """
        try:
            return cls.CHECK.whole(value, positive=True, optional=True)
        except PriceCheckError as e:
            raise InvalidBillingIncrementSError(e.value, e.expected) from e

    @field_validator("minimum_quantity", mode="before")
    def validate_minimum_quantity(cls, value: RawValue) -> RawValue:
        """Validate the raw minimum quantity: a number from 0, or nothing.

        Args:
            value (RawValue): The raw minimum quantity.

        Returns:
            RawValue: The checked minimum quantity.

        Raises:
            InvalidMinimumQuantityError: If it is not a number from 0, or nothing.
        """
        try:
            return cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidMinimumQuantityError(e.value, e.expected) from e

    @field_validator("minimum_duration_days", mode="before")
    def validate_minimum_duration_days(cls, value: RawValue) -> RawValue:
        """Validate the raw minimum duration: a whole number above 0, or nothing.

        Args:
            value (RawValue): The raw minimum duration.

        Returns:
            RawValue: The checked minimum duration.

        Raises:
            InvalidMinimumDurationDaysError: If it is not a whole number above 0, or nothing.
        """
        try:
            return cls.CHECK.whole(value, positive=True, optional=True)
        except PriceCheckError as e:
            raise InvalidMinimumDurationDaysError(e.value, e.expected) from e

    @field_validator("effective_from", mode="before")
    def validate_effective_from(cls, value: RawValue) -> RawValue:
        """Validate the raw effective date: a date, or nothing.

        Args:
            value (RawValue): The raw effective date.

        Returns:
            RawValue: The checked effective date.

        Raises:
            InvalidEffectiveFromError: If it is not a date, or nothing.
        """
        try:
            return cls.CHECK.day(value)
        except PriceCheckError as e:
            raise InvalidEffectiveFromError(e.value, e.expected) from e

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

    @field_validator("captured", mode="before")
    def validate_captured(cls, value: RawValue) -> RawValue:
        """Validate the raw capture date: a date, or nothing.

        Args:
            value (RawValue): The raw capture date.

        Returns:
            RawValue: The checked capture date.

        Raises:
            InvalidCapturedError: If it is not a date, or nothing.
        """
        try:
            return cls.CHECK.day(value)
        except PriceCheckError as e:
            raise InvalidCapturedError(e.value, e.expected) from e

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: RawValue) -> RawValue:
        """Validate the raw reason: a text of 1 to 500 characters, or nothing.

        Args:
            value (RawValue): The raw reason.

        Returns:
            RawValue: The checked reason.

        Raises:
            InvalidReasonError: If it is not a text of 1 to 500 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 500, optional=True)
        except PriceCheckError as e:
            raise InvalidReasonError(e.value, e.expected) from e

    @field_validator("tier_end", mode="before")
    def validate_tier_end(cls, value: RawValue, info: ValidationInfo) -> RawValue:
        """Validate the raw tier end: a number above the tier start, or nothing.

        Args:
            value (RawValue): The raw tier end.
            info (ValidationInfo): The fields validated so far (the tier start).

        Returns:
            RawValue: The checked tier end.

        Raises:
            InvalidTierEndError: If it is not a number above the tier start, or nothing.
        """
        try:
            end = cls.CHECK.number(value, optional=True)
        except PriceCheckError as e:
            raise InvalidTierEndError(e.value, e.expected) from e
        start = info.data.get("tier_start")
        if end is not None and isinstance(start, Decimal) and end <= start:
            raise InvalidTierEndError(repr(value), f"a number above the tier start {start}")
        return end

    @model_validator(mode="after")
    def validate_consistency(self) -> ServicePrice:
        """Check the fields against each other: a price has a currency, a service without price a reason.

        Returns:
            ServicePrice: The price.

        Raises:
            InconsistentPriceError: If a priced model has no price or currency, or a model without public price has
                a price or no reason.
        """
        if self.model in self.UNPRICED:
            if self.price is not None or not self.reason:
                raise InconsistentPriceError(self.sku_key, f"a {self.model.value} price has no price and a reason")
        elif self.price is None or self.currency is None:
            raise InconsistentPriceError(self.sku_key, f"a {self.model.value} price has a price and a currency")
        return self
