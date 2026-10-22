from __future__ import annotations

from typing import Dict, List, Optional, Union

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import PricingPolicy, SoftwareCategory
from models.cloud.products.pricing import ServicePricingPolicy
from models.cloud.products.product import CloudProduct


def test_valid_product(product_payload: Dict[str, JsonValue]) -> None:
    product = CloudProduct(**product_payload)

    assert product.name == "Object Storage"
    assert product.description == "S3 compatible object storage."
    assert len(product.pricing_policy) == 1
    assert isinstance(product.pricing_policy[0], ServicePricingPolicy)
    assert product.pricing_policy[0].pricing_policy is PricingPolicy.BY_RESOURCE


def test_pricing_policy_defaults_to_empty_list() -> None:
    first = CloudProduct(name="Compute", description="Virtual machines.")
    second = CloudProduct(name="Network", description="Load balancers.")

    assert first.pricing_policy == []
    assert first.pricing_policy is not second.pricing_policy


def test_pricing_policy_accepts_model_instances(pricing_payload: Dict[str, JsonValue]) -> None:
    policy = ServicePricingPolicy(**pricing_payload)

    product = CloudProduct(name="Compute", description="Virtual machines.", pricing_policy=[policy])

    assert product.pricing_policy == [policy]


def test_pricing_policy_accepts_several_entries(pricing_payload: Dict[str, JsonValue]) -> None:
    artifact_payload = {**pricing_payload, "pricing_policy": PricingPolicy.BY_ARTIFACT.value}

    product = CloudProduct(
        name="Kubernetes", description="Managed cluster.", pricing_policy=[pricing_payload, artifact_payload]
    )

    assert [p.pricing_policy for p in product.pricing_policy] == [PricingPolicy.BY_RESOURCE, PricingPolicy.BY_ARTIFACT]


def test_invalid_nested_pricing_policy_is_rejected(
    product_payload: Dict[str, JsonValue], pricing_payload: Dict[str, JsonValue]
) -> None:
    pricing_payload["amount"] = -1  # `product_payload` references this pricing policy.

    with pytest.raises(ValidationError) as exc_info:
        CloudProduct(**product_payload)

    assert exc_info.value.errors()[0]["loc"] == ("pricing_policy", 0, "amount")


def test_none_pricing_policy_is_rejected(product_payload: Dict[str, JsonValue]) -> None:
    product_payload["pricing_policy"] = None

    with pytest.raises(ValidationError):
        CloudProduct(**product_payload)


@pytest.mark.parametrize("field", ["name", "description"])
@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_blank_mandatory_fields_are_rejected(product_payload: Dict[str, JsonValue], field: str, value: str) -> None:
    product_payload[field] = value

    with pytest.raises(ValidationError, match="cannot be empty") as exc_info:
        CloudProduct(**product_payload)

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["name", "description"])
def test_missing_mandatory_fields_are_rejected(product_payload: Dict[str, JsonValue], field: str) -> None:
    del product_payload[field]

    with pytest.raises(ValidationError) as exc_info:
        CloudProduct(**product_payload)

    assert exc_info.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(("field", "max_length"), [("name", 200), ("description", 1000)])
def test_max_length_boundary(product_payload: Dict[str, JsonValue], field: str, max_length: int) -> None:
    product_payload[field] = "x" * max_length
    assert len(getattr(CloudProduct(**product_payload), field)) == max_length

    product_payload[field] = "x" * (max_length + 1)
    with pytest.raises(ValidationError) as exc_info:
        CloudProduct(**product_payload)
    assert exc_info.value.errors()[0]["type"] == "string_too_long"


def test_mandatory_fields_are_not_stripped(product_payload: Dict[str, JsonValue]) -> None:
    product_payload["name"] = "  Compute  "

    assert CloudProduct(**product_payload).name == "  Compute  "


def test_round_trip_serialization(product_payload: Dict[str, JsonValue]) -> None:
    product = CloudProduct(**product_payload)

    assert product.model_dump(mode="json") == {
        **product_payload,
        "url": None,
        "catalogue_categories": [],
        "categories": [],
        "service_categories": [],
        "service_domains": [],
        "source_label_ids": [],
        "categories_source": None,
        "added_at": None,
        "added_from": None,
        "added_caveat": None,
        "updated_at": None,
        "updated_from": None,
        "updated_caveat": None,
        "deleted_at": None,
    }
    assert product.item_dump() == {**product_payload, "url": None}
    assert CloudProduct.model_validate_json(product.model_dump_json()) == product


class TestValidatorsDirectly:
    """Exercise the validators on their own, independently of pydantic's own coercion."""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_validate_mandatory_fields_rejects_blank(self, value: Optional[str]) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            CloudProduct.validate_mandatory_fields(value)

    def test_validate_mandatory_fields_returns_value(self) -> None:
        assert CloudProduct.validate_mandatory_fields("Compute") == "Compute"

    def test_validate_pricing_policy_rejects_none(self) -> None:
        with pytest.raises(ValueError, match="pricing policy cannot be empty"):
            CloudProduct.validate_pricing_policy(None)

    def test_validate_pricing_policy_accepts_empty_list(self) -> None:
        assert CloudProduct.validate_pricing_policy([]) == []

    def test_validate_pricing_policy_leaves_dicts_to_pydantic(self, pricing_payload: Dict[str, JsonValue]) -> None:
        raw = [pricing_payload]

        assert CloudProduct.validate_pricing_policy(raw) is raw

    def test_validate_pricing_policy_keeps_models_and_mixed_entries(
        self, pricing_payload: Dict[str, JsonValue]
    ) -> None:
        policy = ServicePricingPolicy.model_validate(pricing_payload)
        raw: List[Union[ServicePricingPolicy, Dict[str, JsonValue]]] = [policy, pricing_payload]

        assert CloudProduct.validate_pricing_policy(raw) is raw

    def test_validate_pricing_policy_leaves_invalid_dicts_to_pydantic(
        self, pricing_payload: Dict[str, JsonValue]
    ) -> None:
        pricing_payload["currency"] = ""
        raw = [pricing_payload]

        assert CloudProduct.validate_pricing_policy(raw) is raw

    @pytest.mark.parametrize("value", ["Compute", 5, ["Compute"]])
    def test_validate_mandatory_fields_leaves_types_to_pydantic(self, value: JsonValue) -> None:
        assert CloudProduct.validate_mandatory_fields(value) == value


class TestRawInputs:
    """Validators run before pydantic's own validation: unexpected raw types must end up as validation errors."""

    @pytest.mark.parametrize(("field", "value"), [("name", 5), ("description", ["S3"]), ("name", {"en": "Compute"})])
    def test_non_string_mandatory_fields(
        self, product_payload: Dict[str, JsonValue], field: str, value: JsonValue
    ) -> None:
        product_payload[field] = value

        with pytest.raises(ValidationError) as exc_info:
            CloudProduct.model_validate(product_payload)

        assert exc_info.value.errors()[0]["type"] == "string_type"

    @pytest.mark.parametrize("value", ["Free tier", 5, {"amount": 1}])
    def test_non_list_pricing_policy(self, product_payload: Dict[str, JsonValue], value: JsonValue) -> None:
        product_payload["pricing_policy"] = value

        with pytest.raises(ValidationError) as exc_info:
            CloudProduct.model_validate(product_payload)

        assert exc_info.value.errors()[0]["type"] == "list_type"


class TestUrl:
    def test_defaults_to_none(self, product_payload: Dict[str, JsonValue]) -> None:
        assert CloudProduct.model_validate(product_payload).url is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://aws.amazon.com/ec2/", "https://aws.amazon.com/ec2/"),
            ("  http://example.com/product  ", "http://example.com/product"),
            ("", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_valid_urls(self, product_payload: Dict[str, JsonValue], value: JsonValue, expected: Optional[str]) -> None:
        product_payload["url"] = value

        assert CloudProduct.model_validate(product_payload).url == expected

    @pytest.mark.parametrize("value", ["/en/products/", "ftp://example.com/file", "https://", "javascript:void(0)"])
    def test_invalid_urls_are_rejected(self, product_payload: Dict[str, JsonValue], value: str) -> None:
        product_payload["url"] = value

        with pytest.raises(ValidationError, match="absolute http"):
            CloudProduct.model_validate(product_payload)

    def test_non_string_url_is_left_to_pydantic(self, product_payload: Dict[str, JsonValue]) -> None:
        product_payload["url"] = 5

        with pytest.raises(ValidationError) as exc_info:
            CloudProduct.model_validate(product_payload)

        assert exc_info.value.errors()[0]["type"] == "string_type"

    def test_validator_directly(self) -> None:
        assert CloudProduct.validate_url(["not", "a", "url"]) == ["not", "a", "url"]


def test_catalogue_categories_default_to_empty_list() -> None:
    product = CloudProduct(name="Compute", description="Virtual machines.")

    assert product.catalogue_categories == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ([], []),
        (["Compute", "  AI &   Machine Learning ", ""], ["Compute", "AI & Machine Learning"]),
        (["Storage", "Storage", "  "], ["Storage"]),
    ],
)
def test_catalogue_categories_are_cleaned(raw: Optional[List[str]], expected: List[str]) -> None:
    product = CloudProduct(name="Compute", description="Virtual machines.", catalogue_categories=raw)

    assert product.catalogue_categories == expected


def test_catalogue_categories_reject_non_text_labels() -> None:
    with pytest.raises(ValidationError):
        CloudProduct(name="Compute", description="Virtual machines.", catalogue_categories=[{"label": "Compute"}])


def test_catalogue_categories_do_not_change_the_fingerprint() -> None:
    plain = CloudProduct(name="Compute", description="Virtual machines.")
    filed = CloudProduct(name="Compute", description="Virtual machines.", catalogue_categories=["Compute"])

    assert plain.fingerprint_hash() == filed.fingerprint_hash()


def test_catalogue_categories_are_streamed_only_when_filled() -> None:
    plain = CloudProduct(name="Compute", description="Virtual machines.")
    filed = CloudProduct(name="Compute", description="Virtual machines.", catalogue_categories=["Compute"])

    assert "catalogue_categories" not in plain.item_dump()
    assert filed.item_dump()["catalogue_categories"] == ["Compute"]


def test_the_categories_are_kept_in_enum_order_without_duplicates(product_payload: Dict[str, JsonValue]) -> None:
    payload = {**product_payload, "categories": ["end-user-software", "developer-tool", "end-user-software"]}

    product = CloudProduct.model_validate(payload)

    assert product.categories == [SoftwareCategory.DEVELOPER_TOOL, SoftwareCategory.END_USER_SOFTWARE]
    assert CloudProduct.model_validate({**product_payload, "categories": None}).categories == []
    assert "categories" not in CloudProduct.model_validate(product_payload).item_dump(), "streamed once classified"
    assert (
        CloudProduct.model_validate(payload).fingerprint() == CloudProduct.model_validate(product_payload).fingerprint()
    )
    with pytest.raises(ValidationError):
        CloudProduct.model_validate({**product_payload, "categories": ["robots"]})
