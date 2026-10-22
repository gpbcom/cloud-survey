from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import pytest

from conftest import CRAWLED_AT
from models.cloud.enums import CloudProvider, MarketPlayer, SoftwareCategory
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.software.marketplace import CloudMarketplace
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from storage.importer.json_importer import JsonImporter
from storage.storage import Storage

pytestmark = pytest.mark.db


def write_output(
    folder: Path,
    make_catalogue: Callable[[CloudProvider, List[str]], CloudCatalogue],
    make_marketplace: Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace],
    make_software: Callable[..., MarketplaceSoftware],
    make_report: Callable[..., MarketReport],
) -> None:
    (folder / "marketplaces").mkdir(parents=True)
    (folder / "stats").mkdir()
    (folder / "civo.json").write_text(make_catalogue(CloudProvider.CIVO, ["Compute", "Storage"]).model_dump_json())
    marketplace = make_marketplace(
        CloudProvider.CIVO, [make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])]
    )
    (folder / "marketplaces" / "civo.json").write_text(marketplace.model_dump_json())
    statistics = MarketStatistics(
        source="Synergy Research Group",
        crawled_at=CRAWLED_AT,
        reports=[make_report("2026Q1", [(MarketPlayer.AMAZON, 30.0)])],
    )
    (folder / "stats" / "synergy.json").write_text(statistics.model_dump_json())
    (folder / "scaleway.json").write_text("{not json")
    (folder / "ovh-cloud.json").write_text(make_catalogue(CloudProvider.CIVO, ["Other"]).model_dump_json())


async def test_the_output_folder_is_imported_once(
    storage: Storage,
    tmp_path: Path,
    make_catalogue: Callable[[CloudProvider, List[str]], CloudCatalogue],
    make_marketplace: Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace],
    make_software: Callable[..., MarketplaceSoftware],
    make_report: Callable[..., MarketReport],
) -> None:
    write_output(tmp_path, make_catalogue, make_marketplace, make_software, make_report)
    importer = JsonImporter(storage)

    imported = await importer.import_folder(tmp_path)
    again = await importer.import_folder(tmp_path)
    replaced = await importer.import_folder(tmp_path, replace=True)

    assert imported == {"civo.json": 2, "marketplaces/civo.json": 1, "stats/synergy.json": 1}
    assert again == {}
    assert replaced == imported
    catalogue = await storage.catalogues.load(CloudProvider.CIVO)
    assert catalogue is not None
    assert catalogue.crawled_at == CRAWLED_AT
    assert [product.name for product in catalogue.products] == ["Compute", "Storage"]
    assert await storage.catalogues.load(CloudProvider.SCALEWAY) is None, "an invalid file is skipped"
    assert await storage.catalogues.load(CloudProvider.OVH) is None, "a file of another provider is skipped"
    statistics = await storage.statistics.load("synergy")
    assert statistics is not None
    assert len(statistics.reports) == 1
