from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider, Country
from models.cloud.products.catalogue import CloudCatalogue

MakeCatalogue = Callable[[CloudProvider, List[str]], CloudCatalogue]


@pytest.fixture
def payload() -> Dict[str, JsonValue]:
    return {
        "provider": "scaleway",
        "crawled_at": "2026-10-16T07:24:36.222672Z",
        "products": [{"name": "Instances", "description": "Virtual machines", "pricing_policy": []}],
    }


def test_parses_the_catalogue_file_format(payload: Dict[str, JsonValue]) -> None:
    catalogue = CloudCatalogue.model_validate(payload)

    assert catalogue.provider is CloudProvider.SCALEWAY
    assert catalogue.crawled_at.utcoffset() is not None
    assert [product.name for product in catalogue.products] == ["Instances"]


def test_products_default_to_empty() -> None:
    assert (
        CloudCatalogue(provider=CloudProvider.AWS, crawled_at=datetime.fromisoformat("2026-10-16T07:00Z")).products
        == []
    )


def test_crawl_date_must_be_timezone_aware(payload: Dict[str, JsonValue]) -> None:
    payload["crawled_at"] = "2026-10-16T07:24:36"

    with pytest.raises(ValidationError, match="timezone"):
        CloudCatalogue.model_validate(payload)


@pytest.mark.parametrize(("field", "value"), [("provider", "unknown-cloud"), ("products", [{"name": ""}])])
def test_invalid_content_is_rejected(payload: Dict[str, JsonValue], field: str, value: JsonValue) -> None:
    payload[field] = value

    with pytest.raises(ValidationError):
        CloudCatalogue.model_validate(payload)


def test_json_round_trip(make_catalogue: MakeCatalogue) -> None:
    catalogue = make_catalogue(CloudProvider.GCP, ["Cloud Run", "BigQuery"])

    assert CloudCatalogue.model_validate_json(catalogue.model_dump_json(indent=2)) == catalogue


def test_country_is_written_and_ignored_on_load(make_catalogue: MakeCatalogue) -> None:
    catalogue = make_catalogue(CloudProvider.CIVO, ["Kubernetes"])

    written = catalogue.model_dump(mode="json")

    assert written["country"] == "gb"
    assert CloudCatalogue.model_validate({**written, "country": "fr"}).country is Country.UNITED_KINGDOM


def test_files_without_country_still_load(payload: Dict[str, JsonValue]) -> None:
    assert CloudCatalogue.model_validate(payload).country is Country.FRANCE
