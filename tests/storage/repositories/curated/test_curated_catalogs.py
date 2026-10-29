from __future__ import annotations

from pathlib import Path

import pytest

from conf import CURATED_DIR
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.bundle.bundle_files import BundleFiles
from models.curated.enums import CuratedFile, IdentifierKind, IdentifierStatus, RecordOrigin
from storage.storage import Storage

pytestmark = pytest.mark.db


class TestSeededCatalogs:
    async def test_the_database_gives_the_bundled_catalogues_back(self, storage: Storage) -> None:
        applied = await storage.curated_seeder.seed()
        bundled = BundleCatalogs()

        assert set(applied) == set(CuratedFile)
        assert await storage.catalogs.chronology() == bundled.chronology()
        assert await storage.catalogs.markets() == bundled.markets()
        assert await storage.catalogs.companies() == bundled.companies()
        assert await storage.catalogs.figures() == bundled.figures()
        assert await storage.catalogs.launches() == bundled.launches()

    async def test_a_second_seed_changes_nothing(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()

        assert await storage.curated_seeder.seed() == {}

    async def test_an_unseeded_database_reads_the_bundle(self, storage: Storage) -> None:
        figures = await storage.catalogs.figures()

        assert figures == BundleCatalogs().figures()
        assert figures.companies, "never an empty catalogue: it would delete the stored figures"

    async def test_an_edit_survives_a_reseed_unless_replaced(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        cik = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000051143")
        assert cik is not None
        edited = cik.model_copy(update={"note": "checked by hand", "edited": True, "origin": RecordOrigin.USER})
        assert await storage.company_identifiers.update(edited)

        await storage.curated_seeder.seed(force=True)
        kept = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000051143")
        await storage.curated_seeder.seed(force=True, replace_edited=True)
        replaced = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000051143")

        assert kept is not None
        assert kept.note == "checked by hand"
        assert replaced is not None
        assert replaced.note == "INTERNATIONAL BUSINESS MACHINES CORP; XBRL 200"

    async def test_a_candidate_identifier_stays_out_of_the_catalogue(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        before = await storage.catalogs.companies()
        candidate = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000051143")
        assert candidate is not None
        await storage.company_identifiers.create(
            candidate.model_copy(update={"value": "0000099999", "status": IdentifierStatus.CANDIDATE, "position": 9})
        )

        after = await storage.catalogs.companies()

        assert after == before

    async def test_an_export_reimports_to_the_same_rows(self, storage: Storage, tmp_path: Path) -> None:
        await storage.curated_seeder.seed()
        bundle = await storage.catalogs.bundle()

        BundleFiles(tmp_path).write(bundle)

        assert BundleFiles(tmp_path).read() == BundleFiles().read()
        for file in CuratedFile:
            exported = (tmp_path / f"{file.value}.json").read_text(encoding="utf-8")
            assert exported == (CURATED_DIR / f"{file.value}.json").read_text(encoding="utf-8"), file.value

    async def test_a_write_makes_the_catalogue_read_again(self, storage: Storage) -> None:
        await storage.curated_seeder.seed()
        before = await storage.catalogs.launches()
        first = before.launches[0]
        state = await storage.curated_state.read(CuratedFile.LAUNCHES)

        assert await storage.launches.delete(first.crawler, first.name)
        after = await storage.catalogs.launches()
        bumped = await storage.curated_state.read(CuratedFile.LAUNCHES)

        assert len(after.launches) == len(before.launches) - 1
        assert state is not None
        assert bumped is not None
        assert bumped.revision == state.revision + 1
        assert await storage.launches.read(first.crawler, first.name) is None
