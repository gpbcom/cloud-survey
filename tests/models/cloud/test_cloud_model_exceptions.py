from __future__ import annotations

from typing import Callable, Dict, Type

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from models.cloud.exception import (
    CloudModelError,
    EmptyCurrencyError,
    EmptyMandatoryFieldError,
    InvalidPricingPolicyError,
    InvalidProductUrlError,
    MissingPricingPolicyError,
    NegativeAmountError,
)
from models.cloud.products.pricing import ServicePricingPolicy
from models.cloud.products.product import CloudProduct

ERRORS = [InvalidPricingPolicyError, NegativeAmountError, EmptyCurrencyError, EmptyMandatoryFieldError]


class TestCloudModelError:
    def test_is_a_value_error(self) -> None:
        assert issubclass(CloudModelError, ValueError)

    def test_keeps_its_message(self) -> None:
        error = CloudModelError("Something went wrong.")

        assert error.message == "Something went wrong."
        assert str(error) == "Something went wrong."

    @pytest.mark.parametrize("error_cls", [*ERRORS, MissingPricingPolicyError])
    def test_every_error_inherits_from_it(self, error_cls: Type[CloudModelError]) -> None:
        assert issubclass(error_cls, CloudModelError)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (InvalidPricingPolicyError("flat-fee"), "The pricing policy is invalid: 'flat-fee'."),
        (NegativeAmountError(-1.5), "The amount and free_limit must be greater than or equal to 0 (got -1.5)."),
        (EmptyCurrencyError(), "The currency symbol cannot be empty."),
        (EmptyMandatoryFieldError(), "The name or description field(s) cannot be empty."),
        (MissingPricingPolicyError(), "The pricing policy cannot be empty."),
    ],
)
def test_messages(error: CloudModelError, message: str) -> None:
    assert str(error) == message
    assert error.message == message


def test_attributes() -> None:
    assert InvalidPricingPolicyError("flat-fee").value == "flat-fee"
    assert NegativeAmountError(-1.5).value == -1.5


def validate_pricing(payload: Dict[str, JsonValue]) -> BaseModel:
    return ServicePricingPolicy.model_validate(payload)


def validate_product(payload: Dict[str, JsonValue]) -> BaseModel:
    return CloudProduct.model_validate(payload)


@pytest.mark.parametrize(
    ("validate", "override", "error_cls"),
    [
        (validate_pricing, {"amount": -1}, NegativeAmountError),
        (validate_pricing, {"free_limit": -1}, NegativeAmountError),
        (validate_pricing, {"currency": ""}, EmptyCurrencyError),
        (validate_product, {"name": "  "}, EmptyMandatoryFieldError),
        (validate_product, {"description": ""}, EmptyMandatoryFieldError),
    ],
)
def test_models_report_them_as_validation_errors(
    pricing_payload: Dict[str, JsonValue],
    product_payload: Dict[str, JsonValue],
    validate: Callable[[Dict[str, JsonValue]], BaseModel],
    override: Dict[str, JsonValue],
    error_cls: Type[CloudModelError],
) -> None:
    payload = pricing_payload if validate is validate_pricing else product_payload

    with pytest.raises(ValidationError) as exc_info:
        validate({**payload, **override})

    (error,) = exc_info.value.errors()
    assert error["type"] == "value_error"
    assert isinstance(error["ctx"]["error"], error_cls)


def test_validators_raise_them_directly() -> None:
    with pytest.raises(InvalidPricingPolicyError) as exc_info:
        ServicePricingPolicy.validate_pricing_policy("flat-fee")
    assert isinstance(exc_info.value.__cause__, ValueError)

    with pytest.raises(MissingPricingPolicyError):
        CloudProduct.validate_pricing_policy(None)


def test_invalid_product_url_error() -> None:
    error = InvalidProductUrlError("/en/products/")

    assert isinstance(error, CloudModelError)
    assert error.value == "/en/products/"
    assert str(error) == "The product URL must be an absolute http(s) link (got '/en/products/')."
