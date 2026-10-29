from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional, Tuple

# First Party Imports.
from curated.assembly.catalog_assembler import CatalogAssembler
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.bundle.settings_reader import SettingsReader
from curated.catalog_checks import CatalogChecks
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.figures.reported_figures import ReportedFigures
from models.curated.enums import CuratedDataset, CuratedFile
from models.curated.records.curated_bundle import CuratedBundle
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog
from storage.exception import StorageReadError
from storage.repositories.curated.companies.company_identifier_repository import CompanyIdentifierRepository
from storage.repositories.curated.companies.company_profile_repository import CompanyProfileRepository
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.repositories.curated.figures.reported_company_repository import ReportedCompanyRepository
from storage.repositories.curated.figures.reported_event_repository import ReportedEventRepository
from storage.repositories.curated.figures.reported_year_repository import ReportedYearRepository
from storage.repositories.curated.launches.product_launch_repository import ProductLaunchRepository
from storage.repositories.curated.records.curated_record_repository import CuratedRecordRepository


class CatalogProvider:
    """Read the curated catalogues from the database: the same models the YAML files gave, cached by revision.

    Attributes:
        state (CuratedStateRepository): The revision and the seed of each bundle file.
        records (CuratedRecordRepository): The chronology and markets sections.
        profiles (CompanyProfileRepository): The companies crawled.
        identifiers (CompanyIdentifierRepository): Their identifiers.
        figure_companies (ReportedCompanyRepository): The companies whose figures were researched.
        figure_years (ReportedYearRepository): The researched fiscal years.
        figure_events (ReportedEventRepository): The researched events.
        launches_rows (ProductLaunchRepository): The curated launches.
        assembler (CatalogAssembler): Puts the rows back into the catalogue models.
        checks (CatalogChecks): The checks against the chronology.
        settings (SettingsReader): The crawler settings of the catalogues (`conf/settings.yaml`).
        bundled (BundleCatalogs): The catalogues of the bundle, read while the database was never seeded.
        chronology_cache (Optional[Tuple[Tuple[int, ...], Chronology]]): The chronology, by the revisions it was
            read at (as the other caches).
        markets_cache (Optional[Tuple[Tuple[int, ...], MarketsCatalog]]): The markets catalogue.
        companies_cache (Optional[Tuple[Tuple[int, ...], CompaniesCatalog]]): The companies catalogue.
        figures_cache (Optional[Tuple[Tuple[int, ...], ReportedFigures]]): The researched figures.
        launches_cache (Optional[Tuple[Tuple[int, ...], LaunchCatalog]]): The launch dates catalogue.
        logger (Logger): The provider logger.

    Notes:
        - A catalogue is assembled once, then served from memory while the revisions of the bundle files it is
          made of stay the same (every write of a curated row increments its file's revision).
        - A database never seeded holds no curated row: its catalogues are those of the bundle (what a seed would
          write), with a warning telling to run `migrate-db seed`, never empty catalogues (an empty figures
          catalogue would delete the stored figures).
    """

    def __init__(
        self,
        state: CuratedStateRepository,
        records: CuratedRecordRepository,
        profiles: CompanyProfileRepository,
        identifiers: CompanyIdentifierRepository,
        figure_companies: ReportedCompanyRepository,
        figure_years: ReportedYearRepository,
        figure_events: ReportedEventRepository,
        launches: ProductLaunchRepository,
        settings: Optional[SettingsReader] = None,
        bundle: Optional[BundleCatalogs] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the provider.

        Args:
            state (CuratedStateRepository): The revision and the seed of each bundle file.
            records (CuratedRecordRepository): The chronology and markets sections.
            profiles (CompanyProfileRepository): The companies crawled.
            identifiers (CompanyIdentifierRepository): Their identifiers.
            figure_companies (ReportedCompanyRepository): The companies whose figures were researched.
            figure_years (ReportedYearRepository): The researched fiscal years.
            figure_events (ReportedEventRepository): The researched events.
            launches (ProductLaunchRepository): The curated launches.
            settings (Optional[SettingsReader]): The crawler settings, `conf/settings.yaml` by default.
            bundle (Optional[BundleCatalogs]): The catalogues of the bundle, `data/curated` by default.
            logger (Optional[Logger]): The provider logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.state = state
        self.records = records
        self.profiles = profiles
        self.identifiers = identifiers
        self.figure_companies = figure_companies
        self.figure_years = figure_years
        self.figure_events = figure_events
        self.launches_rows = launches
        self.assembler = CatalogAssembler(self.logger)
        self.checks = CatalogChecks(self.logger)
        self.settings = settings if settings else SettingsReader(logger=self.logger)
        self.bundled = bundle if bundle else BundleCatalogs(settings=self.settings, logger=self.logger)
        self.chronology_cache: Optional[Tuple[Tuple[int, ...], Chronology]] = None
        self.markets_cache: Optional[Tuple[Tuple[int, ...], MarketsCatalog]] = None
        self.companies_cache: Optional[Tuple[Tuple[int, ...], CompaniesCatalog]] = None
        self.figures_cache: Optional[Tuple[Tuple[int, ...], ReportedFigures]] = None
        self.launches_cache: Optional[Tuple[Tuple[int, ...], LaunchCatalog]] = None

    ############################
    # Internal Helpers Methods #
    ############################

    async def _revisions(self, *files: CuratedFile) -> Optional[Tuple[int, ...]]:
        """Read the revisions of some bundle files.

        Args:
            *files (CuratedFile): The bundle files.

        Returns:
            Optional[Tuple[int, ...]]: Their revisions, in their order, `None` when one was never seeded.

        Raises:
            StorageReadError: If the state cannot be read.
        """
        revisions = []
        for file in files:
            state = await self.state.read(file)
            if state is None or state.seed_hash is None:
                self.logger.warning(
                    "The curated %s were never seeded in this database: the bundle is read (run `migrate-db seed`).",
                    file.value,
                )
                return None
            revisions.append(state.revision)
        return tuple(revisions)

    async def _records(self, *datasets: CuratedDataset) -> CuratedBundle:
        """Read the records of some sections.

        Args:
            *datasets (CuratedDataset): The sections.

        Returns:
            CuratedBundle: Their records.

        Raises:
            StorageReadError: If the records cannot be read.
        """
        return CuratedBundle(records=await self.records.list(list(datasets)))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def bundle(self) -> CuratedBundle:
        """Read every curated row (what `curated export` writes).

        Returns:
            CuratedBundle: Every row.

        Raises:
            StorageReadError: If the rows cannot be read.
        """
        bundle = CuratedBundle(
            records=await self.records.list(),
            profiles=await self.profiles.list(),
            identifiers=await self.identifiers.list(),
            figure_companies=await self.figure_companies.list(),
            figure_years=await self.figure_years.list(),
            figure_events=await self.figure_events.list(),
            launches=await self.launches_rows.list(),
        )
        self.logger.info("Curated rows read: %d records, %d launches.", len(bundle.records), len(bundle.launches))
        return bundle

    async def chronology(self) -> Chronology:
        """Get the chronology.

        Returns:
            Chronology: The chronology.

        Raises:
            StorageReadError: If the database cannot be read.
            CuratedError: If the database was never seeded and the bundle cannot be read.
            CuratedCatalogError: If the rows do not make a valid chronology.
        """
        revisions = await self._revisions(CuratedFile.CHRONOLOGY)
        if revisions is None:
            return self.bundled.chronology()
        if self.chronology_cache is not None and self.chronology_cache[0] == revisions:
            return self.chronology_cache[1]
        datasets = [dataset for dataset in CuratedDataset if dataset.value.startswith("chronology-")]
        chronology = self.assembler.chronology(await self._records(*datasets))
        self.chronology_cache = (revisions, chronology)
        self.logger.info("Chronology read from the database: %d companies.", len(chronology.companies))
        return chronology

    async def markets(self) -> MarketsCatalog:
        """Get the markets catalogue, checked against the chronology.

        Returns:
            MarketsCatalog: The markets catalogue.

        Raises:
            StorageReadError: If the database cannot be read, or the catalogue names a company
                outside the chronology.
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        revisions = await self._revisions(CuratedFile.MARKETS, CuratedFile.CHRONOLOGY)
        if revisions is None:
            return self.bundled.markets()
        if self.markets_cache is not None and self.markets_cache[0] == revisions:
            return self.markets_cache[1]
        datasets = [dataset for dataset in CuratedDataset if dataset.value.startswith("markets-")]
        catalog = self.assembler.markets(await self._records(*datasets), self.settings.block("markets"))
        chronology = await self.chronology()
        unknown = self.checks.unknown_market_companies(catalog, chronology)
        if unknown:
            self.logger.error("The curated markets catalogue names companies outside the chronology: %s", unknown)
            raise StorageReadError("curated markets", f"unknown companies (define them in the chronology): {unknown}")
        self.checks.unknown_segment_links(catalog, chronology)
        self.markets_cache = (revisions, catalog)
        self.logger.info("Markets catalogue read from the database: %d listings.", len(catalog.listings))
        return catalog

    async def companies(self) -> CompaniesCatalog:
        """Get the companies catalogue (its confirmed identifiers only), checked against the chronology.

        Returns:
            CompaniesCatalog: The companies catalogue.

        Raises:
            StorageReadError: If the database cannot be read, or the catalogue names a company
                outside the chronology.
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        revisions = await self._revisions(CuratedFile.COMPANIES, CuratedFile.CHRONOLOGY)
        if revisions is None:
            return self.bundled.companies()
        if self.companies_cache is not None and self.companies_cache[0] == revisions:
            return self.companies_cache[1]
        rows = CuratedBundle(profiles=await self.profiles.list(), identifiers=await self.identifiers.list())
        catalog = self.assembler.companies(rows, self.settings.block("companies"))
        chronology = await self.chronology()
        unknown = self.checks.unknown_companies(catalog, chronology)
        if unknown:
            self.logger.error("The curated companies catalogue names companies outside the chronology: %s", unknown)
            raise StorageReadError("curated companies", f"unknown companies (define them in the chronology): {unknown}")
        self.companies_cache = (revisions, catalog)
        self.logger.info("Companies catalogue read from the database: %d companies.", len(catalog.companies))
        return catalog

    async def figures(self) -> ReportedFigures:
        """Get the researched figures, checked against the chronology.

        Returns:
            ReportedFigures: The researched figures.

        Raises:
            StorageReadError: If the database cannot be read, or the figures name a company
                outside the chronology.
            CuratedCatalogError: If the rows do not make valid figures.
        """
        revisions = await self._revisions(CuratedFile.FIGURES, CuratedFile.CHRONOLOGY)
        if revisions is None:
            return self.bundled.figures()
        if self.figures_cache is not None and self.figures_cache[0] == revisions:
            return self.figures_cache[1]
        rows = CuratedBundle(
            figure_companies=await self.figure_companies.list(),
            figure_years=await self.figure_years.list(),
            figure_events=await self.figure_events.list(),
        )
        figures = self.assembler.figures(rows)
        unknown = self.checks.unknown_figure_companies(figures, await self.chronology())
        if unknown:
            self.logger.error("The curated figures name companies outside the chronology: %s", unknown)
            raise StorageReadError("curated figures", f"unknown companies (define them in the chronology): {unknown}")
        self.figures_cache = (revisions, figures)
        self.logger.info("Researched figures read from the database: %d companies.", len(figures.companies))
        return figures

    async def launches(self) -> LaunchCatalog:
        """Get the launch dates catalogue.

        Returns:
            LaunchCatalog: The launch dates catalogue.

        Raises:
            StorageReadError: If the database cannot be read.
            CuratedError: If the database was never seeded and the bundle cannot be read.
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        revisions = await self._revisions(CuratedFile.LAUNCHES)
        if revisions is None:
            return self.bundled.launches()
        if self.launches_cache is not None and self.launches_cache[0] == revisions:
            return self.launches_cache[1]
        rows = CuratedBundle(
            records=await self.records.list([CuratedDataset.LAUNCH_ALIASES]),
            launches=await self.launches_rows.list(),
        )
        catalog = self.assembler.launches(rows)
        self.launches_cache = (revisions, catalog)
        self.logger.info("Launch dates read from the database: %d launches.", len(catalog.launches))
        return catalog

    def forget(self) -> None:
        """Forget the catalogues in memory (the next reads assemble them again)."""
        self.chronology_cache = self.markets_cache = None
        self.companies_cache = self.figures_cache = self.launches_cache = None
        self.logger.debug("Curated catalogues forgotten.")
