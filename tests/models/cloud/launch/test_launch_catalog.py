from __future__ import annotations

from typing import Dict, List

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.exception import DuplicateLaunchEntryError, InvalidLaunchFieldError
from models.cloud.launch.launch_alias import LaunchAlias
from models.cloud.launch.launch_catalog import LaunchCatalog

SOURCE = "https://cloud.google.com/blog/products/gcp/introducing-cloud-spanner"


def alias(crawler: str, name: str, feed_name: str) -> Dict[str, JsonValue]:
    return {"crawler": crawler, "name": name, "feed_name": feed_name}


def launched(crawler: str, name: str) -> Dict[str, JsonValue]:
    return {"crawler": crawler, "name": name, "launched": "2017-02-14", "source": SOURCE}


def test_alias_fields_are_checked() -> None:
    entry = LaunchAlias.model_validate(alias("azure", " Azure OpenAI  in Foundry Models", "Azure OpenAI Service"))

    assert entry.name == "Azure OpenAI in Foundry Models"
    assert entry.feed_name == "Azure OpenAI Service"
    for bad in (alias("Azure", "A", "B"), alias("azure", "", "B"), alias("azure", "A", "b" * 121)):
        with pytest.raises(ValidationError) as error:
            LaunchAlias.model_validate(bad)
        assert isinstance(error.value.errors()[0]["ctx"]["error"], InvalidLaunchFieldError)


def test_entries_by_crawler() -> None:
    catalog = LaunchCatalog.model_validate(
        {
            "aliases": [alias("azure", "Foundry Models", "Azure AI Studio"), alias("gcp", "GKE", "Kubernetes Engine")],
            "launches": [launched("gcp", "Spanner"), launched("azure", "Cosmos DB")],
        }
    )

    assert catalog.aliases_of("azure") == {"Foundry Models": "Azure AI Studio"}
    assert [entry.name for entry in catalog.launches_of("gcp")] == ["Spanner"]
    assert catalog.launches_of("aws") == []


@pytest.mark.parametrize("raw", [{}, {"aliases": None, "launches": None}])
def test_missing_lists_are_empty(raw: Dict[str, JsonValue]) -> None:
    catalog = LaunchCatalog.model_validate(raw)

    assert catalog.aliases == []
    assert catalog.launches == []


def test_lists_must_be_lists() -> None:
    with pytest.raises(ValidationError) as error:
        LaunchCatalog.model_validate({"launches": "Spanner"})

    assert isinstance(error.value.errors()[0]["ctx"]["error"], InvalidLaunchFieldError)


@pytest.mark.parametrize(
    "raw",
    [
        {"launches": [launched("gcp", "Spanner"), launched("gcp", "spanner")]},
        {"aliases": [alias("azure", "A", "B"), alias("azure", "A", "C")]},
    ],
)
def test_rejects_a_product_listed_twice(raw: Dict[str, List[Dict[str, JsonValue]]]) -> None:
    with pytest.raises(ValidationError) as error:
        LaunchCatalog.model_validate(raw)

    assert isinstance(error.value.errors()[0]["ctx"]["error"], DuplicateLaunchEntryError)


def test_the_same_product_may_be_listed_for_two_crawlers() -> None:
    catalog = LaunchCatalog.model_validate({"launches": [launched("gcp", "Spanner"), launched("azure", "Spanner")]})

    assert len(catalog.launches) == 2
