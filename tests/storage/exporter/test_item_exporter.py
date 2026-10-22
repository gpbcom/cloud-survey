from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from conftest import build_product, build_software, seed_catalogue, seed_marketplace
from models.cloud.enums import CloudProvider, SoftwareCategory
from models.storage.enums import ExportFormat, ItemSort
from models.storage.pages.item_query import ItemQuery
from storage.exception import StorageExportError
from storage.exporter.item_exporter import ItemExporter
from storage.storage import Storage

pytestmark = pytest.mark.db


async def test_products_are_exported_as_csv(storage: Storage, tmp_path: Path) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product(name) for name in ("Beta", "Alpha")])
    path = tmp_path / "products.csv"

    exported = await ItemExporter(storage.catalogues).export(ItemQuery(sort=ItemSort.NAME), path, ExportFormat.CSV)

    assert exported == 2
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["name"] for row in rows] == ["Alpha", "Beta"]
    assert rows[0]["provider"] == CloudProvider.CIVO.value
    assert rows[0]["pricing_policy"] == "[]", "lists are JSON texts"
    assert rows[0]["deleted_at"] == ""
    assert not path.with_name("products.csv.part").exists()


async def test_software_is_exported_as_json_and_json_lines(storage: Storage, tmp_path: Path) -> None:
    software = [build_software(name, ["crm"], [SoftwareCategory.END_USER_SOFTWARE]) for name in "AB"]
    await seed_marketplace(storage, CloudProvider.AWS, software)
    exporter = ItemExporter(storage.marketplaces)
    query = ItemQuery(sort=ItemSort.NAME, name="A")

    assert await exporter.export(query, tmp_path / "software.json", ExportFormat.JSON) == 1
    assert await exporter.export(ItemQuery(sort=ItemSort.NAME), tmp_path / "all.jsonl", ExportFormat.JSON_LINES) == 2

    [only] = json.loads((tmp_path / "software.json").read_text(encoding="utf-8"))
    assert (only["name"], only["marketplace_categories"], only["provider"]) == ("A", ["crm"], CloudProvider.AWS.value)
    lines = (tmp_path / "all.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["name"] for line in lines] == ["A", "B"]


async def test_an_empty_export_is_still_a_valid_file(storage: Storage, tmp_path: Path) -> None:
    exporter = ItemExporter(storage.catalogues)

    assert await exporter.export(ItemQuery(), tmp_path / "none.csv", ExportFormat.CSV) == 0
    assert await exporter.export(ItemQuery(), tmp_path / "none.json", ExportFormat.JSON) == 0

    assert (tmp_path / "none.csv").read_text(encoding="utf-8").startswith("id,provider,")
    assert json.loads((tmp_path / "none.json").read_text(encoding="utf-8")) == []


async def test_an_unwritable_file_leaves_nothing(storage: Storage, tmp_path: Path) -> None:
    await seed_catalogue(storage, CloudProvider.CIVO, [build_product("Alpha")])
    target = tmp_path / "missing" / "products.csv"

    with pytest.raises(StorageExportError, match="Cannot export to"):
        await ItemExporter(storage.catalogues).export(ItemQuery(), target, ExportFormat.CSV)

    assert not target.parent.exists()
