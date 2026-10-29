from __future__ import annotations

from curated.assembly.catalog_assembler import CatalogAssembler
from curated.assembly.catalog_splitter import CatalogSplitter
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.bundle.bundle_files import BundleFiles
from curated.bundle.settings_reader import SettingsReader


def test_the_shipped_catalogues_survive_a_split_and_an_assembly() -> None:
    catalogs = BundleCatalogs()
    chronology, markets, companies = catalogs.chronology(), catalogs.markets(), catalogs.companies()
    figures, launches = catalogs.figures(), catalogs.launches()
    settings = SettingsReader()

    bundle = CatalogSplitter().bundle(chronology, markets, companies, figures, launches)
    assembler = CatalogAssembler()

    assert assembler.chronology(bundle) == chronology
    assert assembler.markets(bundle, settings.block("markets")) == markets
    assert assembler.companies(bundle, settings.block("companies")) == companies
    assert assembler.figures(bundle) == figures
    assert assembler.launches(bundle) == launches


def test_the_shipped_catalogues_are_complete() -> None:
    catalogs = BundleCatalogs()

    assert len(catalogs.chronology().companies) >= 100
    assert len(catalogs.companies().companies) >= 100
    assert len(catalogs.figures().companies) >= 50
    assert len(catalogs.launches().launches) >= 2600


def test_the_research_notes_are_kept() -> None:
    bundle = BundleFiles().read()

    ibm_cik = next(item for item in bundle.identifiers if item.company == "ibm" and item.value == "0000051143")
    assert ibm_cik.note == "INTERNATIONAL BUSINESS MACHINES CORP; XBRL 200"
    tymshare = next(profile for profile in bundle.profiles if profile.company == "tymshare")
    assert tymshare.note is not None
    assert "McDonnell Douglas" in tymshare.note
