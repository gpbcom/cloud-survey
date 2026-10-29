from __future__ import annotations

from pathlib import Path

import pytest

from curated.bundle.bundle_files import BundleFiles
from curated.exception import CuratedCatalogError
from models.curated.enums import CuratedDataset, CuratedFile, IdentifierStatus, RecordOrigin
from storage.exception import StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db


class TestCatalogEditor:
    async def test_an_edit_is_read_exported_and_reimported(self, storage: Storage, tmp_path: Path) -> None:
        await storage.curated_seeder.seed()
        part = await storage.catalog_editor.part(CuratedFile.LAUNCHES)
        first = part.launches[0]
        edited = first.model_copy(
            update={
                "body": {**first.body, "launched": "2019-02"},
                "note": "checked by hand",
                "edited": True,
                "origin": RecordOrigin.USER,
            }
        )
        changed = part.model_copy(update={"launches": [edited, *part.launches[1:]]})

        assert await storage.catalog_editor.save(CuratedFile.LAUNCHES, changed) == 1
        launches = (await storage.catalogs.launches()).launches_of(first.crawler)
        launch = next((entry for entry in launches if entry.name == first.name), None)
        BundleFiles(tmp_path).write(await storage.catalogs.bundle())
        exported = next(row for row in BundleFiles(tmp_path).read().launches if row.name == first.name)

        assert launch is not None
        assert launch.launched == "2019-02"
        assert exported.note == "checked by hand"
        assert exported.edited
        assert exported.origin is RecordOrigin.USER
        assert await storage.curated_seeder.seed(BundleFiles(tmp_path), force=True)
        assert await storage.catalog_editor.part(CuratedFile.LAUNCHES) == BundleFiles(tmp_path).part(
            BundleFiles(tmp_path).read(), CuratedFile.LAUNCHES
        )

    async def test_a_chronology_company_still_named_cannot_be_removed(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        part = await storage.catalog_editor.part(CuratedFile.CHRONOLOGY)
        kept = [
            record
            for record in part.records
            if not (record.dataset is CuratedDataset.CHRONOLOGY_COMPANIES and record.key == "tymshare")
        ]

        with pytest.raises((StorageWriteError, CuratedCatalogError)):
            await storage.catalog_editor.save(CuratedFile.CHRONOLOGY, part.model_copy(update={"records": kept}))

        assert await storage.catalog_editor.part(CuratedFile.CHRONOLOGY) == part

    async def test_an_invalid_entry_is_refused_before_anything_is_written(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        part = await storage.catalog_editor.part(CuratedFile.LAUNCHES)
        first = part.launches[0]
        broken = first.model_copy(update={"body": {"crawler": first.crawler, "name": first.name, "launched": "x"}})

        with pytest.raises(CuratedCatalogError):
            await storage.catalog_editor.save(
                CuratedFile.LAUNCHES, part.model_copy(update={"launches": [broken, *part.launches[1:]]})
            )

        assert await storage.catalog_editor.part(CuratedFile.LAUNCHES) == part

    async def test_an_accepted_candidate_joins_the_catalogue(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        part = await storage.catalog_editor.part(CuratedFile.COMPANIES)
        cik = next(row for row in part.identifiers if row.company == "ibm" and row.value == "0000051143")
        candidate = cik.model_copy(
            update={"value": "0000099999", "position": 9, "status": IdentifierStatus.CANDIDATE, "note": None}
        )
        await storage.catalog_editor.save(
            CuratedFile.COMPANIES, part.model_copy(update={"identifiers": [*part.identifiers, candidate]})
        )
        before = await storage.catalogs.companies()
        accepted = candidate.model_copy(update={"status": IdentifierStatus.CONFIRMED, "edited": True})

        await storage.catalog_editor.save(
            CuratedFile.COMPANIES, part.model_copy(update={"identifiers": [*part.identifiers, accepted]})
        )
        after = await storage.catalogs.companies()

        assert "0000099999" not in next(entry for entry in before.companies if entry.key == "ibm").sec_ciks
        assert "0000099999" in next(entry for entry in after.companies if entry.key == "ibm").sec_ciks

    async def test_an_unseeded_database_is_not_edited(self, storage: Storage) -> None:
        part = BundleFiles().part(BundleFiles().read(), CuratedFile.LAUNCHES)

        with pytest.raises(StorageWriteError, match="never seeded"):
            await storage.catalog_editor.save(CuratedFile.LAUNCHES, part)

        assert await storage.launches.list() == []
