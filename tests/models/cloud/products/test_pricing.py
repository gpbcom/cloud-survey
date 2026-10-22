from __future__ import annotations

from typing import Dict, Optional, Union

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import PricingPolicy
from models.cloud.exception import InvalidPricingPolicyError, NegativeAmountError
from models.cloud.products.pricing import ServicePricingPolicy


def test_valid_pricing_policy(pricing_payload: Dict[str, JsonValue]) -> None:
    policy = ServicePricingPolicy(**pricing_payload)

    assert policy.pricing_policy is PricingPolicy.BY_RESOURCE
    assert policy.free_limit == 10.0
    assert policy.amount == 0.25
    assert policy.currency == "EUR"


@pytest.mark.parametrize("raw_policy", [PricingPolicy.BY_ARTIFACT, "artifacts-billing"])
def test_pricing_policy_accepts_enum_or_string(
    pricing_payload: Dict[str, JsonValue], raw_policy: Union[PricingPolicy, str]
) -> None:
    pricing_payload["pricing_policy"] = raw_policy

    policy = ServicePricingPolicy(**pricing_payload)

    assert policy.pricing_policy is PricingPolicy.BY_ARTIFACT


def test_invalid_pricing_policy_is_rejected(pricing_payload: Dict[str, JsonValue]) -> None:
    pricing_payload["pricing_policy"] = "pay-what-you-want"

    with pytest.raises(ValidationError) as exc_info:
        ServicePricingPolicy(**pricing_payload)

    assert exc_info.value.errors()[0]["loc"] == ("pricing_policy",)


@pytest.mark.parametrize("field", ["free_limit", "amount"])
def test_negative_numbers_are_rejected(pricing_payload: Dict[str, JsonValue], field: str) -> None:
    pricing_payload[field] = -0.01

    with pytest.raises(ValidationError, match="greater than or equal to 0") as exc_info:
        ServicePricingPolicy(**pricing_payload)

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["free_limit", "amount"])
def test_zero_is_accepted(pricing_payload: Dict[str, JsonValue], field: str) -> None:
    pricing_payload[field] = 0

    policy = ServicePricingPolicy(**pricing_payload)

    assert getattr(policy, field) == 0.0


@pytest.mark.parametrize("field", ["free_limit", "amount"])
def test_numeric_strings_are_coerced(pricing_payload: Dict[str, JsonValue], field: str) -> None:
    pricing_payload[field] = "3.5"

    policy = ServicePricingPolicy(**pricing_payload)

    assert getattr(policy, field) == 3.5


@pytest.mark.parametrize("field", ["free_limit", "amount"])
def test_non_numeric_values_are_rejected(pricing_payload: Dict[str, JsonValue], field: str) -> None:
    pricing_payload[field] = "free"

    with pytest.raises(ValidationError):
        ServicePricingPolicy(**pricing_payload)


def test_empty_currency_is_rejected(pricing_payload: Dict[str, JsonValue]) -> None:
    pricing_payload["currency"] = ""

    with pytest.raises(ValidationError, match="currency symbol cannot be empty"):
        ServicePricingPolicy(**pricing_payload)


def test_none_currency_is_rejected(pricing_payload: Dict[str, JsonValue]) -> None:
    pricing_payload["currency"] = None

    with pytest.raises(ValidationError):
        ServicePricingPolicy(**pricing_payload)


@pytest.mark.parametrize("field", ["pricing_policy", "free_limit", "amount", "currency"])
def test_missing_field_is_rejected(pricing_payload: Dict[str, JsonValue], field: str) -> None:
    del pricing_payload[field]

    with pytest.raises(ValidationError) as exc_info:
        ServicePricingPolicy(**pricing_payload)

    assert exc_info.value.errors()[0]["type"] == "missing"
    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_round_trip_serialization(pricing_payload: Dict[str, JsonValue]) -> None:
    policy = ServicePricingPolicy(**pricing_payload)

    assert policy.model_dump(mode="json") == pricing_payload
    assert ServicePricingPolicy.model_validate_json(policy.model_dump_json()) == policy


class TestValidatorsDirectly:
    """Exercise the validators on their own, independently of pydantic's own coercion."""

    @pytest.mark.parametrize("value", [PricingPolicy.BY_RESOURCE, "resources-billing"])
    def test_validate_pricing_policy_returns_enum(self, value: Union[PricingPolicy, str]) -> None:
        assert ServicePricingPolicy.validate_pricing_policy(value) is PricingPolicy.BY_RESOURCE

    def test_validate_pricing_policy_wraps_error(self) -> None:
        with pytest.raises(ValueError, match="pricing policy is invalid") as exc_info:
            ServicePricingPolicy.validate_pricing_policy("unknown")

        assert isinstance(exc_info.value.__cause__, ValueError)

    @pytest.mark.parametrize("value", [0.0, 1.0, 1e9])
    def test_validate_numbers_returns_value(self, value: float) -> None:
        assert ServicePricingPolicy.validate_numbers(value) == value

    def test_validate_numbers_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            ServicePricingPolicy.validate_numbers(-1.0)

    @pytest.mark.parametrize("value", [None, ""])
    def test_validate_currency_rejects_empty(self, value: Optional[str]) -> None:
        with pytest.raises(ValueError, match="currency symbol cannot be empty"):
            ServicePricingPolicy.validate_currency(value)

    def test_validate_currency_returns_value(self) -> None:
        assert ServicePricingPolicy.validate_currency("USD") == "USD"

    @pytest.mark.parametrize("value", [1, None, ["artifacts-billing"]])
    def test_validate_pricing_policy_rejects_non_strings(self, value: JsonValue) -> None:
        with pytest.raises(InvalidPricingPolicyError) as exc_info:
            ServicePricingPolicy.validate_pricing_policy(value)

        assert exc_info.value.value == str(value)

    @pytest.mark.parametrize("value", ["3.5", "0", 2, None, "free", [1]])
    def test_validate_numbers_leaves_other_values_unchanged(self, value: JsonValue) -> None:
        assert ServicePricingPolicy.validate_numbers(value) == value

    @pytest.mark.parametrize(("value", "number"), [("-2", -2.0), ("-0.5", -0.5), (-3, -3.0)])
    def test_validate_numbers_rejects_negative_raw_numbers(self, value: JsonValue, number: float) -> None:
        with pytest.raises(NegativeAmountError) as exc_info:
            ServicePricingPolicy.validate_numbers(value)

        assert exc_info.value.value == number


class TestRawInputs:
    """Validators run before pydantic's own validation: unexpected raw types must end up as validation errors."""

    @pytest.mark.parametrize("field", ["free_limit", "amount"])
    def test_negative_numeric_strings_are_rejected(self, pricing_payload: Dict[str, JsonValue], field: str) -> None:
        pricing_payload[field] = "-2"

        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            ServicePricingPolicy.model_validate(pricing_payload)

    @pytest.mark.parametrize(("field", "value"), [("free_limit", None), ("amount", [1]), ("amount", {"value": 1})])
    def test_non_numeric_values_are_rejected(
        self, pricing_payload: Dict[str, JsonValue], field: str, value: JsonValue
    ) -> None:
        pricing_payload[field] = value

        with pytest.raises(ValidationError) as exc_info:
            ServicePricingPolicy.model_validate(pricing_payload)

        assert exc_info.value.errors()[0]["type"] == "float_type"

    @pytest.mark.parametrize("value", [5, ["EUR"]])
    def test_non_string_currency_is_rejected(self, pricing_payload: Dict[str, JsonValue], value: JsonValue) -> None:
        pricing_payload["currency"] = value

        with pytest.raises(ValidationError) as exc_info:
            ServicePricingPolicy.model_validate(pricing_payload)

        assert exc_info.value.errors()[0]["type"] == "string_type"

    def test_non_string_pricing_policy_is_rejected(self, pricing_payload: Dict[str, JsonValue]) -> None:
        pricing_payload["pricing_policy"] = 1

        with pytest.raises(ValidationError, match="The pricing policy is invalid: '1'"):
            ServicePricingPolicy.model_validate(pricing_payload)
