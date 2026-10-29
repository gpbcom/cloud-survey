from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Dict

from pydantic import JsonValue

from analytics.history.version_differ import VersionDiffer
from models.storage.versions.item_version import ItemVersion
from models.storage.versions.version_change import VersionChange

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def version(crawl_id: int, days: int, content: Dict[str, JsonValue]) -> ItemVersion:
    return ItemVersion(
        crawl_id=crawl_id, recorded_at=T0 + timedelta(days=days), crawl_status="succeeded", content=content
    )


def test_no_version_gives_no_change() -> None:
    assert VersionDiffer().changes([]) == []


def test_the_oldest_version_is_first_seen_and_the_newest_comes_first() -> None:
    versions = [
        version(1, 0, {"name": "A", "description": "Old", "pricing": [1]}),
        version(3, 2, {"name": "A", "description": "New", "url": "https://a.example", "pricing": [1]}),
        version(2, 1, {"name": "A", "description": "Old", "pricing": [1]}),
    ]

    changes = VersionDiffer().changes(versions)

    assert [change.crawl_id for change in changes] == [3, 2, 1]
    newest, unchanged, oldest = changes
    assert oldest.first
    assert (oldest.added, oldest.removed, oldest.changed) == ([], [], [])
    assert not newest.first
    assert newest.changed == [("description", "Old", "New")]
    assert newest.added == ["url"]
    assert newest.removed == []
    assert (unchanged.added, unchanged.removed, unchanged.changed) == ([], [], [])


def test_removed_fields_and_nested_values_compared_as_json() -> None:
    older = version(1, 0, {"tags": {"b": 1, "a": [1, 2]}, "regions": ["eu"], "price": None})
    newer = version(2, 1, {"tags": {"a": [1, 2], "b": 1}, "regions": ["eu", "us"]})

    change = VersionDiffer().changes([older, newer])[0]

    assert change.removed == ["price"]
    assert change.changed == [("regions", '["eu"]', '["eu", "us"]')]


def test_long_and_missing_values_are_written_short() -> None:
    older = version(1, 0, {"description": "word " * 100, "url": None})
    newer = version(2, 1, {"description": "short", "url": "https://a.example"})

    change = VersionDiffer().changes([older, newer])[0]
    fields = {field: (before, after) for field, before, after in change.changed}

    before = fields["description"][0]
    assert len(before) == VersionChange.TEXT_LIMIT
    assert before.endswith(VersionDiffer.ELLIPSIS)
    assert fields["url"] == (VersionDiffer.EMPTY, "https://a.example")
