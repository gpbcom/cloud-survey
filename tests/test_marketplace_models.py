from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider, Country, DeliveryMethod, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware


@pytest.fixture
def payload() -> Dict[str, JsonValue]:
    return {
        "name": "Greenhouse",
        "description": "Hiring software.",
        "publisher": " Greenhouse Software ",
        "url": " https://marketplace.example.com/greenhouse ",
        "delivery": "saas",
        "marketplace_categories": ["Human Resources", " ", "Human Resources", "Talent Acquisition"],
        "categories": ["end-user-software", "end-user-software"],
        "types": ["ats", "hris"],
    }


def test_parses_a_software(payload: Dict[str, JsonValue]) -> None:
    software = MarketplaceSoftware.model_validate(payload)

    assert software.publisher == "Greenhouse Software"
    assert software.url == "https://marketplace.example.com/greenhouse"
    assert software.delivery is DeliveryMethod.SAAS
    assert software.marketplace_categories == ["Human Resources", "Talent Acquisition"]
    assert software.categories == [SoftwareCategory.END_USER_SOFTWARE]
    assert software.types == [SoftwareType.ATS, SoftwareType.HRIS]


def test_defaults(payload: Dict[str, JsonValue]) -> None:
    for key in ("publisher", "url", "delivery", "marketplace_categories"):
        payload.pop(key)

    software = MarketplaceSoftware.model_validate(payload)

    assert (software.publisher, software.url, software.delivery, software.marketplace_categories) == (
        None,
        None,
        DeliveryMethod.OTHER,
        [],
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("description", None),
        ("name", "x" * 301),
        ("description", "x" * 1001),
        ("url", "/relative"),
        ("categories", []),
        ("types", []),
        ("types", ["spreadsheet"]),
        ("delivery", "floppy"),
        ("url", 5),
        ("marketplace_categories", "Security"),
    ],
)
def test_invalid_software_is_rejected(payload: Dict[str, JsonValue], field: str, value: JsonValue) -> None:
    payload[field] = value

    with pytest.raises(ValidationError):
        MarketplaceSoftware.model_validate(payload)


@pytest.mark.parametrize(("publisher", "expected"), [("  ", None), (None, None), ("ACME", "ACME")])
def test_blank_publisher_is_none(payload: Dict[str, JsonValue], publisher: JsonValue, expected: JsonValue) -> None:
    payload["publisher"] = publisher

    assert MarketplaceSoftware.model_validate(payload).publisher == expected


def test_blank_url_is_none(payload: Dict[str, JsonValue]) -> None:
    payload["url"] = " "

    assert MarketplaceSoftware.model_validate(payload).url is None


def test_marketplace_country_is_written_and_ignored_on_load(payload: Dict[str, JsonValue]) -> None:
    marketplace = CloudMarketplace(
        provider=CloudProvider.STACKIT,
        crawled_at=datetime(2026, 10, 16, tzinfo=UTC),
        software=[MarketplaceSoftware.model_validate(payload)],
    )

    written = marketplace.model_dump(mode="json")

    assert written["country"] == "de"
    reloaded = CloudMarketplace.model_validate({**written, "country": "fr"})
    assert reloaded.country is Country.GERMANY
    assert reloaded == marketplace


def test_marketplace_software_defaults_to_empty() -> None:
    marketplace = CloudMarketplace(provider=CloudProvider.AWS, crawled_at=datetime(2026, 10, 16, tzinfo=UTC))

    assert marketplace.software == []


def test_marketplace_date_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        CloudMarketplace.model_validate({"provider": "aws", "crawled_at": "2026-10-16T07:24:36"})
