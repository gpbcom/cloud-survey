from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Dict

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from curated.bundle.settings_reader import SettingsReader
from models.cloud.enums import FreeTierKind, PriceModel, PriceUnit
from models.cloud.prices import exception as errors
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.profiles.price_quote import PriceQuote
from models.cloud.prices.profiles.usage_item import UsageItem
from models.cloud.prices.profiles.usage_profile import UsageProfile
from models.cloud.prices.settings.prices_settings import PricesSettings
from models.cloud.prices.stored.price_source import PriceSource
from models.cloud.prices.stored.stored_free_tier import StoredFreeTier
from models.cloud.prices.stored.stored_price import StoredPrice

PRICE: Dict[str, JsonValue] = {
    "provider": "amazon-web-services",
    "sku_key": "AmazonEC2|JRTCKXETXF|m7i.large|us-east-1|on-demand",
    "service": "Amazon Elastic Compute Cloud",
    "family": "Compute Instance",
    "region": "us-east-1",
    "instance_type": "m7i.large",
    "vcpu": 2,
    "memory_gib": "8",
    "os": "Linux",
    "attributes": {"tenancy": "Shared"},
    "unit": "hour",
    "unit_raw": "Hrs",
    "price": "0.1008",
    "currency": "usd",
    "source_url": "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.csv",
    "source_kind": "api",
    "effective_from": "2026-10-01",
}
FREE: Dict[str, JsonValue] = {
    "provider": "microsoft-azure",
    "free_key": "functions|executions",
    "service": "Azure Functions",
    "kind": "always-free",
    "quantity": 1000000,
    "unit": "request",
    "period": "month",
    "source_url": "https://azure.microsoft.com/en-us/pricing/free-services",
    "source_kind": "page",
}
SOURCE: Dict[str, JsonValue] = {"provider": "amazon-web-services", "source_key": "AmazonEC2/us-east-1", "rows": 12}
ITEM: Dict[str, JsonValue] = {"label": "Web servers", "family": "Compute Instance", "unit": "hour", "quantity": 1460}
QUOTE: Dict[str, JsonValue] = {
    "profile": "Web app",
    "provider": "google-cloud-platform",
    "region": "europe-west1",
    "currency": "EUR",
    "monthly_total": "182.50",
    "breakdown": [{"label": "Web servers", "cost": "120.00"}],
}
NOW = datetime(2026, 10, 29, tzinfo=UTC)


def error_of(model: type[BaseModel], data: Dict[str, JsonValue]) -> type[Exception]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    error = caught.value.errors()[0].get("ctx", {}).get("error")
    assert isinstance(error, errors.PriceModelError), caught.value
    return type(error)


class TestServicePrice:
    def test_a_price_is_read_and_normalized(self) -> None:
        price = ServicePrice.model_validate(PRICE)

        assert price.price == Decimal("0.1008")
        assert price.currency == "USD"
        assert price.unit is PriceUnit.HOUR
        assert price.model is PriceModel.ON_DEMAND
        assert price.effective_from == date(2026, 10, 1)

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("provider", "aws", errors.InvalidProviderError),
            ("sku_key", "", errors.InvalidSkuKeyError),
            ("service", 3, errors.InvalidServiceError),
            ("family", "x" * 201, errors.InvalidFamilyError),
            ("region", "", errors.InvalidRegionError),
            ("instance_type", "x" * 121, errors.InvalidInstanceTypeError),
            ("vcpu", -1, errors.InvalidVcpuError),
            ("memory_gib", "lots", errors.InvalidMemoryGibError),
            ("storage_gib", True, errors.InvalidStorageGibError),
            ("os", "x" * 121, errors.InvalidOsError),
            ("attributes", ["tenancy"], errors.InvalidAttributesError),
            ("unit", "hours", errors.InvalidUnitError),
            ("unit_raw", "", errors.InvalidUnitRawError),
            ("unit_factor", 0, errors.InvalidUnitFactorError),
            ("price", "-0.1", errors.InvalidPriceError),
            ("currency", "dollars", errors.InvalidCurrencyError),
            ("model", "pay-as-you-go", errors.InvalidModelError),
            ("term", "7y", errors.InvalidTermError),
            ("tier_start", "NaN", errors.InvalidTierStartError),
            ("tier_end", "-5", errors.InvalidTierEndError),
            ("billing_increment_s", 0, errors.InvalidBillingIncrementSError),
            ("minimum_quantity", -2, errors.InvalidMinimumQuantityError),
            ("minimum_duration_days", 1.5, errors.InvalidMinimumDurationDaysError),
            ("effective_from", "October", errors.InvalidEffectiveFromError),
            ("source_url", "ftp://x", errors.InvalidSourceUrlError),
            ("source_kind", "rumour", errors.InvalidSourceKindError),
            ("captured", 2026, errors.InvalidCapturedError),
            ("reason", "x" * 501, errors.InvalidReasonError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(ServicePrice, {**PRICE, field: value}) is error

    def test_a_tier_ends_after_it_starts(self) -> None:
        assert error_of(ServicePrice, {**PRICE, "tier_start": 50, "tier_end": 50}) is errors.InvalidTierEndError

    @pytest.mark.parametrize(
        "changes",
        [
            {"price": None},
            {"currency": None},
            {"model": "quote", "reason": "Contact sales."},
            {"model": "quote", "price": None, "currency": None},
        ],
    )
    def test_the_fields_must_agree(self, changes: Dict[str, JsonValue]) -> None:
        assert error_of(ServicePrice, {**PRICE, **changes}) is errors.InconsistentPriceError

    def test_a_service_without_public_price_states_why(self) -> None:
        price = ServicePrice.model_validate(
            {**PRICE, "model": "quote", "price": None, "currency": None, "reason": "Contact sales."}
        )

        assert price.price is None
        assert price.reason == "Contact sales."


class TestStoredPrice:
    def test_a_stored_price_keeps_its_history_fields(self) -> None:
        stored = StoredPrice.model_validate({**PRICE, "id": 4, "fingerprint": "a1b2", "valid_from": NOW})

        assert stored.valid_to is None
        assert not stored.edited

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("id", 0, errors.InvalidIdError),
            ("product_id", "seven", errors.InvalidProductIdError),
            ("fingerprint", "", errors.InvalidFingerprintError),
            ("origin", "robot", errors.InvalidOriginError),
            ("edited", "yes", errors.InvalidEditedError),
            ("valid_from", "2026-10-29T10:00:00", errors.InvalidValidFromError),
            ("valid_to", "2020-01-01T00:00:00+00:00", errors.InvalidValidToError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        data: Dict[str, JsonValue] = {**PRICE, "fingerprint": "a1b2", "valid_from": NOW.isoformat()}
        assert error_of(StoredPrice, {**data, field: value}) is error


class TestFreeTier:
    def test_a_free_offer_is_read(self) -> None:
        free = FreeTier.model_validate(FREE)

        assert free.kind is FreeTierKind.ALWAYS_FREE
        assert free.quantity == Decimal(1000000)

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("provider", "azure", errors.InvalidProviderError),
            ("free_key", "", errors.InvalidFreeKeyError),
            ("service", "", errors.InvalidServiceError),
            ("kind", "forever", errors.InvalidKindError),
            ("quantity", -1, errors.InvalidQuantityError),
            ("unit", "executions", errors.InvalidUnitError),
            ("unit_raw", "x" * 121, errors.InvalidUnitRawError),
            ("currency", "euro", errors.InvalidCurrencyError),
            ("period", "x" * 21, errors.InvalidPeriodError),
            ("duration_days", 0, errors.InvalidDurationDaysError),
            ("region_scope", "", errors.InvalidRegionScopeError),
            ("conditions", "x" * 1001, errors.InvalidConditionsError),
            ("source_url", "azure.com", errors.InvalidSourceUrlError),
            ("source_kind", "word", errors.InvalidSourceKindError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(FreeTier, {**FREE, field: value}) is error

    def test_a_stored_offer_checks_its_history(self) -> None:
        data: Dict[str, JsonValue] = {**FREE, "fingerprint": "f", "valid_from": NOW.isoformat()}

        assert StoredFreeTier.model_validate(data).origin.value == "crawler"
        assert error_of(StoredFreeTier, {**data, "edited": 1}) is errors.InvalidEditedError


class TestPriceSource:
    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("provider", "", errors.InvalidProviderError),
            ("source_key", "", errors.InvalidSourceKeyError),
            ("version", "x" * 201, errors.InvalidVersionError),
            ("etag", 7, errors.InvalidEtagError),
            ("last_modified", "x" * 101, errors.InvalidLastModifiedError),
            ("fetched_at", "yesterday", errors.InvalidFetchedAtError),
            ("rows", -1, errors.InvalidRowsError),
            ("status", "stale", errors.InvalidStatusError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(PriceSource, {**SOURCE, field: value}) is error


class TestUsageProfile:
    def test_a_profile_and_its_items_are_read(self) -> None:
        profile = UsageProfile.model_validate(
            {"name": "Web app", "items": [{**ITEM, "minimums": {"vcpu": 2, "memory_gib": "8"}}]}
        )

        assert profile.items[0].minimums == {"vcpu": Decimal(2), "memory_gib": Decimal(8)}

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("label", "", errors.InvalidLabelError),
            ("concept", "x" * 201, errors.InvalidConceptError),
            ("family", 5, errors.InvalidFamilyError),
            ("unit", "hours", errors.InvalidUnitError),
            ("quantity", -3, errors.InvalidQuantityError),
            ("minimums", {"gpu": 1}, errors.InvalidMinimumsError),
            ("minimums", {"vcpu": -1}, errors.InvalidMinimumsError),
            ("os", "x" * 121, errors.InvalidOsError),
            ("model", "cheap", errors.InvalidModelError),
            ("term", "forever", errors.InvalidTermError),
        ],
    )
    def test_each_item_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(UsageItem, {**ITEM, field: value}) is error

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("name", "", errors.InvalidNameError),
            ("description", "x" * 1001, errors.InvalidDescriptionError),
            ("items", "web", errors.InvalidItemsError),
            ("origin", "ai", errors.InvalidOriginError),
            ("edited", None, errors.InvalidEditedError),
        ],
    )
    def test_each_profile_field_raises_its_own_error(
        self, field: str, value: JsonValue, error: type[Exception]
    ) -> None:
        assert error_of(UsageProfile, {"name": "Web app", field: value}) is error


class TestPriceQuote:
    def test_a_quote_is_read(self) -> None:
        assert PriceQuote.model_validate(QUOTE).monthly_total == Decimal("182.50")

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("profile", "", errors.InvalidProfileError),
            ("provider", "gcp", errors.InvalidProviderError),
            ("region", "", errors.InvalidRegionError),
            ("options", "", errors.InvalidOptionsError),
            ("currency", None, errors.InvalidCurrencyError),
            ("monthly_total", "-1", errors.InvalidMonthlyTotalError),
            ("breakdown", [1, 2], errors.InvalidBreakdownError),
            ("computed_at", "now", errors.InvalidComputedAtError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(PriceQuote, {**QUOTE, field: value}) is error


class TestPricesSettings:
    def test_the_shipped_settings_are_read(self) -> None:
        settings = PricesSettings.model_validate(SettingsReader().block("prices"))

        assert settings.max_memory_mb == 1024
        assert settings.download_dir == ""
        assert settings.request_delay_ms == 2000
        assert settings.merge_timeout_s == 3600

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("max_memory_mb", 64, errors.InvalidMaxMemoryMbError),
            ("max_concurrency", 0, errors.InvalidMaxConcurrencyError),
            ("max_requests_per_host", 9, errors.InvalidMaxRequestsPerHostError),
            ("batch_rows", 10, errors.InvalidBatchRowsError),
            ("max_disk_mb", "lots", errors.InvalidMaxDiskMbError),
            ("download_dir", 5, errors.InvalidDownloadDirError),
            ("request_delay_ms", 100, errors.InvalidRequestDelayMsError),
            ("merge_timeout_s", 10, errors.InvalidMergeTimeoutSError),
            ("merge_timeout_s", "long", errors.InvalidMergeTimeoutSError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(PricesSettings, {field: value}) is error
