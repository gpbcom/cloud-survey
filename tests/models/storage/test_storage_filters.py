from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from models.cloud.enums import DateCaveat, DateSource
from models.storage.filters.date_filter import DateFilter
from models.storage.filters.exception import InvalidDateRangeError, StorageFilterError
from models.storage.pages.category_count import CategoryCount
from models.storage.pages.item_query import ItemQuery

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_a_date_filter_is_active_once_it_filters() -> None:
    assert not DateFilter().is_active
    assert DateFilter(after=T0).is_active
    assert DateFilter(before=T0).is_active
    assert DateFilter(sources=[DateSource.CRAWL]).is_active
    assert DateFilter(known=False).is_active


def test_a_date_range_cannot_end_before_it_starts() -> None:
    with pytest.raises(ValidationError, match="ends"):
        DateFilter(after=T0, before=T0 - timedelta(days=1))

    assert DateFilter(after=T0, before=T0).before == T0


def test_the_filter_errors_explain_themselves() -> None:
    error = InvalidDateRangeError(T0, T0 - timedelta(days=1))

    assert isinstance(error, StorageFilterError)
    assert isinstance(error, ValueError)
    assert str(error) == "The date range ends (2025-12-31T00:00:00+00:00) before it starts (2026-01-01T00:00:00+00:00)."
    assert StorageFilterError("x").message == "x"


def test_a_query_cleans_its_text_and_label_filters() -> None:
    query = ItemQuery(
        name="  grafana  labs ",
        description=" ",
        url=" example.com ",
        publishers=[" ACME ", ""],
        service_categories=["", " crm "],
        caveats=[DateCaveat.YEAR_ONLY],
    )

    assert (query.name, query.description, query.url) == ("grafana labs", None, "example.com")
    assert (query.publishers, query.service_categories) == (["ACME"], ["crm"])
    assert not query.added.is_active
    assert query.caveats == [DateCaveat.YEAR_ONLY]


def test_a_category_count_has_a_readable_label() -> None:
    assert CategoryCount(path=["AI", "Agents"], count=3).label() == "AI > Agents"
    with pytest.raises(ValidationError):
        CategoryCount(path=[], count=1)
