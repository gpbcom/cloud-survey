from __future__ import annotations

from pathlib import Path

import pytest

from curated.bundle.bundle_files import BundleFiles
from models.configuration.storage.storage_settings import StorageSettings
from scripts.curated.curated_cli import CuratedCli

pytestmark = pytest.mark.db


def test_an_imported_bundle_shows_no_difference(
    storage_settings: StorageSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = CuratedCli(settings=storage_settings)

    assert cli.parse(["import", "--force", "--replace-edited"]) == 0
    capsys.readouterr()
    assert cli.parse(["diff"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    assert all(line.endswith(": 0 only in the database, 0 only in the bundle or different") for line in lines)


def test_an_export_gives_the_bundle_back(storage_settings: StorageSettings, tmp_path: Path) -> None:
    cli = CuratedCli(settings=storage_settings)
    assert cli.parse(["import", "--force", "--replace-edited"]) == 0

    assert cli.parse(["export", "--dir", str(tmp_path)]) == 0

    exported, bundled = BundleFiles(tmp_path).read(), BundleFiles().read()
    for field in type(bundled).model_fields:
        mine, theirs = getattr(exported, field), getattr(bundled, field)
        first = next(((ours, their) for ours, their in zip(mine, theirs) if ours != their), None)
        assert first is None, f"{field}: {first}"
        assert len(mine) == len(theirs), field
