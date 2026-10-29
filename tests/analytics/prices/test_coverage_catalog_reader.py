from __future__ import annotations

from pathlib import Path

from analytics.prices.coverage_catalog_reader import CoverageCatalogReader
from conf import PRICE_COVERAGE_DIR
from models.cloud.enums import CloudProvider


def test_a_catalogue_is_read_once(tmp_path: Path) -> None:
    (tmp_path / "civo.yaml").write_text(
        "provider: civo\nlinks:\n  Kubernetes: ['^k3s']\nstatements: []\n", encoding="utf-8"
    )
    reader = CoverageCatalogReader(tmp_path)

    catalog = reader.read(CloudProvider.CIVO)

    assert catalog is not None
    assert catalog.links == {"Kubernetes": ["^k3s"]}
    assert reader.read(CloudProvider.CIVO) is catalog


def test_a_missing_invalid_or_misplaced_catalogue_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "civo.yaml").write_text("provider: civo\nlinks: [1]\n", encoding="utf-8")
    (tmp_path / "krystal.yaml").write_text("provider: civo\n", encoding="utf-8")
    (tmp_path / "gcore.yaml").write_text("provider: [unclosed\n", encoding="utf-8")
    reader = CoverageCatalogReader(tmp_path)

    assert reader.read(CloudProvider.CIVO) is None
    assert reader.read(CloudProvider.KRYSTAL) is None
    assert reader.read(CloudProvider.GCORE) is None
    assert reader.read(CloudProvider.AWS) is None


def test_the_shipped_catalogues_are_valid() -> None:
    reader = CoverageCatalogReader()

    for path in sorted(PRICE_COVERAGE_DIR.glob("*.yaml")):
        assert reader.read(CloudProvider(path.stem)) is not None, path.name
