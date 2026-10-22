from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.storage.storage_settings import StorageSettings
from models.storage.crawl_summary import CrawlSummary
from models.storage.dataset_changes import DatasetChanges
from models.storage.dataset_stamp import DatasetStamp
from models.storage.enums import CrawlStatus, DatasetKind, DeletedState, ExportFormat, SelectionAction
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.storage.pages.software_facets import SoftwareFacets
from models.storage.pages.stored_item import StoredItem

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_a_query_cleans_its_search_and_category() -> None:
    query = ItemQuery(search="  my   tool ", service_categories=[" data ", "", "databases"], source_labels=[3, 1, 3])

    assert (query.search, query.service_categories) == ("my tool", ["data", "databases"])
    assert query.source_labels == [3, 1]
    assert ItemQuery(search="   ").search is None
    assert query.page(400).offset == 400
    assert query.page(400, 50).limit == 50


@pytest.mark.parametrize("values", [{"limit": 0}, {"limit": 5001}, {"offset": -1}, {"search": "a" * 201}])
def test_a_query_has_bounds(values: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        ItemQuery.model_validate(values)


def test_a_page_tells_whether_items_follow(make_software: Callable[..., MarketplaceSoftware]) -> None:
    item = StoredItem[MarketplaceSoftware](
        id=1,
        provider=CloudProvider.CIVO,
        item=make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL]),
    )

    assert Page[MarketplaceSoftware](items=[item], limit=1, total=2).has_more
    assert not Page[MarketplaceSoftware](items=[item], limit=1, total=1).has_more
    assert Page[MarketplaceSoftware](items=[item], limit=1).has_more
    assert not Page[MarketplaceSoftware](items=[], limit=1).has_more


def test_the_storage_models_validate_their_fields() -> None:
    stamp = DatasetStamp(kind=DatasetKind.CATALOGUE, dataset="civo", crawled_at=T0, size=3, revision=9)
    summary = CrawlSummary(
        crawl_id=1, kind=DatasetKind.CATALOGUE, dataset="civo", status=CrawlStatus.SUCCEEDED, started_at=T0
    )

    assert DatasetChanges[MarketplaceSoftware](stamp=stamp, revision=9).items == {}
    assert summary.found == summary.deleted == 0
    assert SoftwareFacets().total == 0
    with pytest.raises(ValidationError):
        DatasetStamp(kind=DatasetKind.CATALOGUE, dataset="", crawled_at=T0)
    with pytest.raises(ValidationError):
        CrawlSummary(
            crawl_id=0, kind=DatasetKind.CATALOGUE, dataset="civo", status=CrawlStatus.SUCCEEDED, started_at=T0
        )


@pytest.mark.parametrize("values", [{"url": "mysql://db/x"}, {"pool_size": 0}, {"max_overflow": -1}, {"batch_size": 0}])
def test_the_storage_settings_have_bounds(values: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        StorageSettings.model_validate(values)


def test_the_bulk_selection_enums_are_their_values() -> None:
    assert [format_.value for format_ in ExportFormat] == ["csv", "json", "jsonl"]
    assert [action.value for action in SelectionAction] == ["filter", "export", "delete"]
    assert DeletedState("deleted") is DeletedState.DELETED
