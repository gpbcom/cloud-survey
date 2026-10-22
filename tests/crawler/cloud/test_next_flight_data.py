from __future__ import annotations

import json
import logging
from typing import List

import pytest
from scrapling.engines.toolbelt.custom import Response

from crawler.cloud.next_flight_data import NextFlightData
from crawler.exception import CatalogueFormatError

URL = "https://cloud.example/products"


def page(chunks: List[str]) -> Response:
    scripts = "".join(f"<script>self.__next_f.push({json.dumps([1, chunk])})</script>" for chunk in chunks)
    html = f"<html><body><script>self.__next_f.push([0])</script>{scripts}</body></html>"
    return Response(url=URL, content=html.encode(), status=200, reason="OK", cookies={}, headers={}, request_headers={})


def test_the_json_rows_are_read_across_the_chunks() -> None:
    reader = NextFlightData("example")
    row = json.dumps({"products": [{"title": "Compute"}], "categories": []})

    rows = reader.rows(page(['1:"$Sreact.fragment"\n2:I["chunk"]\n3:' + row[:15], row[15:] + "\n4:[1,2]\n"]))

    assert rows == [json.loads(row), [1, 2]]
    assert reader.find(rows, "products", "categories") == json.loads(row)
    assert reader.find(rows, "missing") is None
    assert [value.get("title") for value in reader.objects(rows) if "title" in value] == ["Compute"]


def test_a_page_without_flight_data_has_no_rows_or_is_a_format_error(caplog: pytest.LogCaptureFixture) -> None:
    reader = NextFlightData("example")
    empty = Response(
        url=URL, content=b"<html></html>", status=200, reason="OK", cookies={}, headers={}, request_headers={}
    )

    assert reader.rows(empty) == []
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError):
        reader.documents(empty)
    assert any("holds no flight data" in record.getMessage() for record in caplog.records)


def test_unreadable_scripts_and_rows_are_skipped(caplog: pytest.LogCaptureFixture) -> None:
    reader = NextFlightData("example")
    broken = Response(
        url=URL,
        content=b'<script>self.__next_f.push([1, "x)</script>'
        b'<script>self.__next_f.push([1, "5:{broken\\n6:{\\"ok\\":1}"])</script>',
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )

    with caplog.at_level(logging.WARNING):
        assert reader.documents(broken) == [{"ok": 1}]
    assert any("unreadable" in record.getMessage() for record in caplog.records)
