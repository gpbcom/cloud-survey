from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.markets.exception import (
    InvalidMarketFlagError,
    InvalidMarketListError,
    InvalidMarketNumberError,
    InvalidMarketTextError,
)
from models.storage.versions.item_version import ItemVersion
from models.storage.versions.version_change import VersionChange

T0 = datetime(2026, 1, 1, tzinfo=UTC)


class TestItemVersion:
    def test_a_version_is_read_from_a_row(self) -> None:
        version = ItemVersion.model_validate(
            {
                "crawl_id": "3",
                "recorded_at": " 2026-01-01T00:00:00+00:00 ",
                "crawl_status": " imported ",
                "content": None,
            }
        )

        assert (version.crawl_id, version.recorded_at, version.crawl_status) == (3, T0, "imported")
        assert version.content == {}

    def test_a_blank_status_is_unknown(self) -> None:
        version = ItemVersion(crawl_id=1, recorded_at=T0, crawl_status="  ", content={"name": "A"})

        assert version.crawl_status is None
        assert version.content == {"name": "A"}

    @pytest.mark.parametrize(
        ("values", "error"),
        [
            ({"crawl_id": 0}, InvalidMarketNumberError),
            ({"crawl_id": "x"}, InvalidMarketNumberError),
            ({"crawl_status": "s" * 21}, InvalidMarketTextError),
            ({"crawl_status": 3}, InvalidMarketTextError),
        ],
    )
    def test_bad_values_are_reported(self, values: Dict[str, JsonValue], error: type) -> None:
        with pytest.raises(ValidationError) as raised:
            ItemVersion.model_validate({"crawl_id": 1, "recorded_at": T0, **values})

        assert isinstance(raised.value.errors()[0]["ctx"]["error"], error)

    @pytest.mark.parametrize("values", [{"recorded_at": "2026-01-01T00:00:00"}, {"content": [1, 2]}])
    def test_a_naive_date_or_a_content_not_an_object_is_refused(self, values: Dict[str, JsonValue]) -> None:
        with pytest.raises(ValidationError):
            ItemVersion.model_validate({"crawl_id": 1, "recorded_at": T0, **values})

    def test_a_version_is_frozen(self) -> None:
        version = ItemVersion(crawl_id=1, recorded_at=T0)

        with pytest.raises(ValidationError):
            version.crawl_id = 2  # type: ignore[misc]


class TestVersionChange:
    def test_a_change_cleans_its_fields(self) -> None:
        change = VersionChange.model_validate(
            {
                "crawl_id": 2,
                "recorded_at": T0,
                "added": [" url "],
                "removed": ["pricing"],
                "changed": [(" name ", " Old ", "")],
            }
        )

        assert (change.added, change.removed) == (["url"], ["pricing"])
        assert change.changed == [("name", "Old", "")]
        assert not change.first

    @pytest.mark.parametrize(
        ("values", "error"),
        [
            ({"first": "yes"}, InvalidMarketFlagError),
            ({"added": "url"}, InvalidMarketListError),
            ({"removed": [""]}, InvalidMarketTextError),
            ({"changed": [("name", "a" * 121, "b")]}, InvalidMarketTextError),
            ({"changed": [("", "a", "b")]}, InvalidMarketTextError),
            ({"crawl_id": -1}, InvalidMarketNumberError),
        ],
    )
    def test_bad_values_are_reported(self, values: Dict[str, JsonValue], error: type) -> None:
        with pytest.raises(ValidationError) as raised:
            VersionChange.model_validate({"crawl_id": 1, "recorded_at": T0, **values})

        assert isinstance(raised.value.errors()[0]["ctx"]["error"], error)

    def test_a_change_not_a_triple_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            VersionChange.model_validate({"crawl_id": 1, "recorded_at": T0, "changed": [("name", "a")]})
