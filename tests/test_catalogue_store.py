from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, List
from unittest.mock import patch

import pytest

from catalogue.exception import CatalogueFileError, CatalogueWriteError
from catalogue.store import DEFAULT_OUTPUT_DIR, CatalogueStore
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider

MakeCatalogue = Callable[[CloudProvider, List[str]], CloudCatalogue]


@pytest.fixture
def store(tmp_path: Path) -> CatalogueStore:
    return CatalogueStore(tmp_path / "output")


def test_default_output_folder() -> None:
    assert Path("output") == DEFAULT_OUTPUT_DIR
    assert CatalogueStore().output_dir == Path("output")


@pytest.mark.parametrize("provider", list(CloudProvider))
def test_one_file_per_provider(store: CatalogueStore, provider: CloudProvider) -> None:
    assert store.path_for(provider) == store.output_dir / f"{provider.value}.json"


def test_save_creates_the_folder_and_writes_json(store: CatalogueStore, make_catalogue: MakeCatalogue) -> None:
    catalogue = make_catalogue(CloudProvider.SCALEWAY, ["Instances", "Object Storage"])

    path = store.save(catalogue)

    assert path == store.output_dir / "scaleway.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["provider"] == "scaleway"
    assert data["crawled_at"] == "2026-10-16T07:24:00Z"
    assert data["products"][0] == {
        "name": "Instances",
        "description": "Instances description",
        "pricing_policy": [],
        "url": None,
        "added_at": None,
        "added_from": None,
        "updated_at": None,
        "updated_from": None,
        "deleted_at": None,
    }
    assert path.read_text(encoding="utf-8").endswith("}\n")
    assert sorted(item.name for item in store.output_dir.iterdir()) == ["scaleway.json"]


def test_save_replaces_the_previous_catalogue(store: CatalogueStore, make_catalogue: MakeCatalogue) -> None:
    store.save(make_catalogue(CloudProvider.AWS, ["Amazon EC2"]))

    store.save(make_catalogue(CloudProvider.AWS, ["Amazon S3"]))

    loaded = store.load(CloudProvider.AWS)
    assert loaded is not None
    assert [product.name for product in loaded.products] == ["Amazon S3"]


def test_failed_save_keeps_the_previous_file(store: CatalogueStore, make_catalogue: MakeCatalogue) -> None:
    path = store.save(make_catalogue(CloudProvider.AWS, ["Amazon EC2"]))
    previous = path.read_text(encoding="utf-8")

    with (
        patch("catalogue.atomic_json_file.os.replace", side_effect=PermissionError(13, "Permission denied")),
        pytest.raises(CatalogueWriteError, match="Permission denied") as exc_info,
    ):
        store.save(make_catalogue(CloudProvider.AWS, ["Amazon S3"]))

    assert exc_info.value.path == path
    assert path.read_text(encoding="utf-8") == previous
    assert sorted(item.name for item in store.output_dir.iterdir()) == ["amazon-web-services.json"]


def test_save_into_a_file_fails(tmp_path: Path, make_catalogue: MakeCatalogue) -> None:
    (tmp_path / "output").write_text("not a folder", encoding="utf-8")

    with pytest.raises(CatalogueWriteError):
        CatalogueStore(tmp_path / "output").save(make_catalogue(CloudProvider.AWS, ["Amazon EC2"]))


def test_load_round_trip(store: CatalogueStore, make_catalogue: MakeCatalogue) -> None:
    catalogue = make_catalogue(CloudProvider.OVH, ["Compute", "Storage"])
    store.save(catalogue)

    assert store.load(CloudProvider.OVH) == catalogue


def test_load_never_crawled_provider(store: CatalogueStore) -> None:
    assert store.load(CloudProvider.AZURE) is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{not json", "the file is not valid JSON"),
        ('{"provider": "scaleway"}', r"invalid catalogue \(1 errors\)"),
        ('{"provider": "ovh-cloud", "crawled_at": "2026-10-16T07:24:00Z", "products": []}', "holds the ovh-cloud"),
    ],
)
def test_load_unusable_files(store: CatalogueStore, content: str, reason: str) -> None:
    path = store.path_for(CloudProvider.SCALEWAY)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    with pytest.raises(CatalogueFileError, match=reason) as exc_info:
        store.load(CloudProvider.SCALEWAY)

    assert exc_info.value.path == path


def test_load_unreadable_file(store: CatalogueStore) -> None:
    path = store.path_for(CloudProvider.SCALEWAY)
    path.mkdir(parents=True)  # A folder where the file is expected.

    with pytest.raises(CatalogueFileError, match="cannot be read") as exc_info:
        store.load(CloudProvider.SCALEWAY)

    assert isinstance(exc_info.value.__cause__, OSError)


def test_operations_are_logged(
    store: CatalogueStore, make_catalogue: MakeCatalogue, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="catalogue.store")
    path = store.save(make_catalogue(CloudProvider.GCP, ["Cloud Run"]))
    store.load(CloudProvider.GCP)
    store.load(CloudProvider.AWS)

    assert [(record.levelname, record.getMessage()) for record in caplog.records] == [
        ("DEBUG", f"Writing the google-cloud-platform catalogue to {path}."),
        ("INFO", f"1 google-cloud-platform products written to {path}."),
        ("INFO", f"1 google-cloud-platform products loaded from {path}."),
        ("DEBUG", f"No amazon-web-services catalogue at {store.path_for(CloudProvider.AWS)}: never crawled."),
    ]
