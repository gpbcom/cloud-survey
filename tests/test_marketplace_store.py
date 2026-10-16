from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from catalogue.exception import CatalogueFileError
from catalogue.marketplace_store import DEFAULT_MARKETPLACE_DIR, MarketplaceStore
from models.cloud.enums import CloudProvider, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware


def marketplace(provider: CloudProvider = CloudProvider.CIVO) -> CloudMarketplace:
    software = MarketplaceSoftware(
        name="Grafana",
        description="Dashboards",
        categories=[SoftwareCategory.DEVELOPER_TOOL],
        types=[SoftwareType.MONITORING],
    )
    return CloudMarketplace(provider=provider, crawled_at=datetime(2026, 10, 16, tzinfo=UTC), software=[software])


def test_default_folder() -> None:
    assert Path("output") / "marketplaces" == DEFAULT_MARKETPLACE_DIR
    assert MarketplaceStore().output_dir == DEFAULT_MARKETPLACE_DIR
    assert MarketplaceStore().logger.name == "catalogue.marketplace_store"


def test_round_trip(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="catalogue.marketplace_store")
    store = MarketplaceStore(tmp_path / "marketplaces")

    path = store.save(marketplace())

    assert path == tmp_path / "marketplaces" / "civo.json"
    assert store.load(CloudProvider.CIVO) == marketplace()
    assert store.load(CloudProvider.AWS) is None
    assert f"1 civo software written to {path}." in caplog.messages
    assert f"1 civo software loaded from {path}." in caplog.messages


def test_file_of_another_provider_is_rejected(tmp_path: Path) -> None:
    store = MarketplaceStore(tmp_path)
    store.path_for(CloudProvider.AWS).write_text(marketplace().model_dump_json(), encoding="utf-8")

    with pytest.raises(CatalogueFileError, match="it holds the civo marketplace"):
        store.load(CloudProvider.AWS)


def test_invalid_file_is_rejected(tmp_path: Path) -> None:
    store = MarketplaceStore(tmp_path)
    store.path_for(CloudProvider.AWS).write_text('{"provider": "amazon-web-services"}', encoding="utf-8")

    with pytest.raises(CatalogueFileError, match="invalid marketplace"):
        store.load(CloudProvider.AWS)
