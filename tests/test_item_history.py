from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import pytest
from pydantic import JsonValue, ValidationError

from catalogue.item_history import ItemHistory
from models.cloud.dated_item import DatedItem
from models.cloud.enums import DateSource, SoftwareCategory, SoftwareType
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct

BEFORE = datetime(2026, 9, 1, tzinfo=UTC)
NOW = datetime(2026, 10, 16, 7, 24, tzinfo=UTC)


def product(
    name: str, description: str = "", url: Optional[str] = None, **dates: Optional[Union[datetime, DateSource]]
) -> CloudProduct:
    fields: Dict[str, Optional[Union[str, datetime, DateSource]]] = {
        "name": name,
        "description": description or f"{name} description",
        "url": url,
    }
    return CloudProduct.model_validate({**fields, **dates})


class TestDatedItem:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2024-03-01", datetime(2024, 3, 1, tzinfo=UTC)),
            ("2024-03-01T10:00:00Z", datetime(2024, 3, 1, 10, tzinfo=UTC)),
            ("2024-03-01 10:00:00+08:00", datetime(2024, 3, 1, 2, tzinfo=UTC)),
            (1709287200, datetime(2024, 3, 1, 10, tzinfo=UTC)),
            (1709287200000, datetime(2024, 3, 1, 10, tzinfo=UTC)),
            ("1709287200", datetime(2024, 3, 1, 10, tzinfo=UTC)),
            (date(2024, 3, 1), datetime(2024, 3, 1, tzinfo=UTC)),
            (datetime(2024, 3, 1, 10), datetime(2024, 3, 1, 10, tzinfo=UTC)),
            (datetime(2024, 3, 1, 18, tzinfo=timezone(timedelta(hours=8))), datetime(2024, 3, 1, 10, tzinfo=UTC)),
            ("  ", None),
            (0, None),
            (None, None),
        ],
    )
    def test_dates(self, raw: Union[JsonValue, date], expected: Optional[datetime]) -> None:
        item = CloudProduct.model_validate({"name": "VM", "description": "Virtual machines", "added_at": raw})

        assert item.added_at == expected
        assert item.added_at is None or item.added_at.tzinfo is not None

    @pytest.mark.parametrize("raw", ["March 2024", True, [2024]])
    def test_invalid_dates(self, raw: JsonValue) -> None:
        with pytest.raises(ValidationError):
            CloudProduct.model_validate({"name": "VM", "description": "Virtual machines", "updated_at": raw})

    def test_invalid_date_message(self) -> None:
        with pytest.raises(ValidationError, match="ISO 8601 date or a Unix timestamp"):
            CloudProduct.model_validate({"name": "VM", "description": "Virtual machines", "deleted_at": "soon"})

    def test_dates_are_serialized_last(self) -> None:
        item = product("VM", added_at=BEFORE, added_from=DateSource.WEBSITE)

        data = json.loads(item.model_dump_json())

        assert list(data) == [
            "name",
            "description",
            "pricing_policy",
            "url",
            "added_at",
            "added_from",
            "updated_at",
            "updated_from",
            "deleted_at",
        ]
        assert (data["added_at"], data["added_from"]) == ("2026-09-01T00:00:00Z", "website")
        assert CloudProduct.model_validate(data) == item

    def test_base_item(self) -> None:
        item = DatedItem(deleted_at=NOW)

        assert (item.match_keys(), item.fingerprint(), item.is_deleted) == ([], "{}", True)

    def test_match_keys_and_fingerprint(self) -> None:
        listed = product("Object  Storage", url="https://example.com/Storage/")
        software = MarketplaceSoftware(
            name="Datadog",
            description="Monitoring",
            publisher="Datadog Inc",
            categories=[SoftwareCategory.DEVELOPER_TOOL],
            types=[SoftwareType.MONITORING],
        )

        assert listed.match_keys() == ["url:https://example.com/storage", "name:object storage"]
        assert product("VM").match_keys() == ["name:vm"]
        assert software.match_keys() == ["id:datadog|datadog inc", "name:datadog|datadog inc"]
        assert listed.fingerprint() == listed.model_copy(update={"added_at": NOW}).fingerprint()
        assert listed.fingerprint() != listed.model_copy(update={"description": "New"}).fingerprint()
        reclassified = software.model_copy(update={"types": [SoftwareType.SECURITY]})
        assert software.fingerprint() == reclassified.fingerprint()


class TestItemHistory:
    @pytest.fixture
    def history(self) -> ItemHistory[CloudProduct]:
        return ItemHistory[CloudProduct]("aws catalogue")

    def test_first_crawl_has_no_observed_dates(self, history: ItemHistory[CloudProduct]) -> None:
        merged = history.merge(None, [product("VM"), product("S3", added_at=BEFORE)], NOW)

        assert [(item.added_at, item.added_from, item.updated_at) for item in merged] == [
            (None, None, None),
            (BEFORE, DateSource.WEBSITE, None),
        ]

    def test_added_updated_unchanged_and_deleted(
        self, history: ItemHistory[CloudProduct], caplog: pytest.LogCaptureFixture
    ) -> None:
        previous = [
            product("VM", added_at=BEFORE, added_from=DateSource.CRAWL),
            product("S3"),
            product("Glacier"),
            product("Old", deleted_at=BEFORE),
        ]
        current = [product("VM"), product("S3", description="Bigger buckets"), product("Lambda"), product("Glacier")]

        with caplog.at_level(logging.INFO):
            merged = history.merge(previous, current, NOW)

        dated = {item.name: item for item in merged}
        assert [item.name for item in merged] == ["VM", "S3", "Lambda", "Glacier", "Old"]
        assert (dated["VM"].added_at, dated["VM"].added_from, dated["VM"].updated_at) == (
            BEFORE,
            DateSource.CRAWL,
            None,
        )
        assert (dated["S3"].updated_at, dated["S3"].updated_from) == (NOW, DateSource.CRAWL)
        assert (dated["Lambda"].added_at, dated["Lambda"].added_from) == (NOW, DateSource.CRAWL)
        assert dated["Old"].deleted_at == BEFORE
        assert "aws catalogue history: 1 added, 1 updated, 0 deleted since the previous crawl." in caplog.messages

    def test_missing_items_are_deleted_and_restored(self, history: ItemHistory[CloudProduct]) -> None:
        previous = [product("VM"), product("S3"), product("Glacier", url="https://aws.example/glacier")]

        deleted = history.merge(previous, [product("VM"), product("S3")], NOW)
        restored = history.merge(
            deleted, [product("VM"), product("S3 Glacier", url="https://aws.example/glacier/")], NOW
        )

        assert [(item.name, item.deleted_at) for item in deleted] == [("VM", None), ("S3", None), ("Glacier", NOW)]
        assert [item.name for item in restored] == ["VM", "S3 Glacier", "S3"]
        glacier, s3 = restored[1], restored[2]
        assert (glacier.deleted_at, glacier.updated_at, glacier.updated_from) == (None, NOW, DateSource.CRAWL)
        assert s3.deleted_at == NOW

    def test_website_dates_win(self, history: ItemHistory[CloudProduct]) -> None:
        previous = [product("VM", added_at=NOW, added_from=DateSource.CRAWL)]

        (item,) = history.merge(previous, [product("VM", description="New", added_at=BEFORE, updated_at=BEFORE)], NOW)

        assert (item.added_at, item.added_from) == (BEFORE, DateSource.WEBSITE)
        assert (item.updated_at, item.updated_from) == (BEFORE, DateSource.WEBSITE)

    def test_unchanged_item_keeps_its_update(self, history: ItemHistory[CloudProduct]) -> None:
        previous = [product("VM", updated_at=BEFORE, updated_from=DateSource.CRAWL)]

        (item,) = history.merge(previous, [product("VM")], NOW)

        assert (item.updated_at, item.updated_from) == (BEFORE, DateSource.CRAWL)

    def test_partial_crawl_deletes_nothing(
        self, history: ItemHistory[CloudProduct], caplog: pytest.LogCaptureFixture
    ) -> None:
        previous = [product(name) for name in ("VM", "S3", "Glacier", "Lambda", "RDS")]

        merged = history.merge(previous, [product("VM"), product("S3")], NOW)

        assert len(merged) == 5
        assert not any(item.is_deleted for item in merged)
        assert "The aws catalogue crawl found 2 items out of 5 listed before: it looks partial" in caplog.text

    def test_duplicates_match_once(self, history: ItemHistory[CloudProduct]) -> None:
        previous = [product("VM", url="https://aws.example/vm")]
        current: List[CloudProduct] = [product("VM", url="https://aws.example/vm"), product("VM")]

        merged = history.merge(previous, current, NOW)

        assert [(item.added_at, item.deleted_at) for item in merged] == [(None, None), (NOW, None)]
