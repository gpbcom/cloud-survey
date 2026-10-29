from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# First Party Imports.
from curated.assembly.catalog_assembler import CatalogAssembler
from curated.bundle.bundle_files import BundleFiles
from curated.bundle.settings_reader import SettingsReader
from curated.catalog_checks import CatalogChecks
from curated.exception import CuratedCatalogError
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.figures.reported_figures import ReportedFigures
from models.curated.enums import CuratedFile
from models.curated.records.curated_bundle import CuratedBundle
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog


class BundleCatalogs:
    """Read the curated catalogues from the bundle (`data/curated/*.json`), without a database.

    Attributes:
        files (BundleFiles): The bundle files.
        settings (SettingsReader): The crawler settings of the catalogues (`conf/settings.yaml`).
        assembler (CatalogAssembler): Puts the rows back into the catalogue models.
        checks (CatalogChecks): The checks against the chronology.
        chronology_cache (Optional[Chronology]): The chronology, once read.
        logger (Logger): The catalogues logger.

    Notes:
        - The bundle is the reviewed copy of the curated data: a crawler built without catalogues (a test, a
          command) reads it, the runs and the explorer read the database (`storage.catalogs`), where the edits are.
        - Each catalogue reads its own bundle file, the chronology once (the others are checked against it).
    """

    def __init__(
        self,
        files: Optional[BundleFiles] = None,
        settings: Optional[SettingsReader] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the catalogues.

        Args:
            files (Optional[BundleFiles]): The bundle files, `data/curated` by default.
            settings (Optional[SettingsReader]): The settings, `conf/settings.yaml` by default.
            logger (Optional[Logger]): The catalogues logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.files = files if files else BundleFiles()
        self.settings = settings if settings else SettingsReader()
        self.assembler = CatalogAssembler()
        self.checks = CatalogChecks()
        self.chronology_cache: Optional[Chronology] = None

    ############################
    # Internal Helpers Methods #
    ############################

    def _part(self, file: CuratedFile) -> CuratedBundle:
        """Read the rows of a bundle file.

        Args:
            file (CuratedFile): The file.

        Returns:
            CuratedBundle: Its rows.

        Raises:
            CuratedBundleError: If the file cannot be read or is invalid.
        """
        return self.files.read(file)

    ############################
    # Publicly Exposed Methods #
    ############################

    def chronology(self) -> Chronology:
        """Get the chronology.

        Returns:
            Chronology: The chronology.

        Raises:
            CuratedBundleError: If the file cannot be read or is invalid.
            CuratedCatalogError: If the rows do not make a valid chronology.
        """
        if self.chronology_cache is None:
            self.chronology_cache = self.assembler.chronology(self._part(CuratedFile.CHRONOLOGY))
        return self.chronology_cache

    def markets(self) -> MarketsCatalog:
        """Get the markets catalogue, checked against the chronology.

        Returns:
            MarketsCatalog: The markets catalogue.

        Raises:
            CuratedBundleError: If a file cannot be read or is invalid.
            CuratedCatalogError: If the rows do not make a valid catalogue, or name a company outside the chronology.
        """
        catalog = self.assembler.markets(self._part(CuratedFile.MARKETS), self.settings.block("markets"))
        chronology = self.chronology()
        unknown = self.checks.unknown_market_companies(catalog, chronology)
        if unknown:
            self.logger.error("The bundled markets catalogue names companies outside the chronology: %s", unknown)
            raise CuratedCatalogError("markets", f"unknown companies (define them in the chronology): {unknown}")
        self.checks.unknown_segment_links(catalog, chronology)
        return catalog

    def companies(self) -> CompaniesCatalog:
        """Get the companies catalogue, checked against the chronology.

        Returns:
            CompaniesCatalog: The companies catalogue.

        Raises:
            CuratedBundleError: If a file cannot be read or is invalid.
            CuratedCatalogError: If the rows do not make a valid catalogue, or name a company outside the chronology.
        """
        catalog = self.assembler.companies(self._part(CuratedFile.COMPANIES), self.settings.block("companies"))
        unknown = self.checks.unknown_companies(catalog, self.chronology())
        if unknown:
            self.logger.error("The bundled companies catalogue names companies outside the chronology: %s", unknown)
            raise CuratedCatalogError("companies", f"unknown companies (define them in the chronology): {unknown}")
        return catalog

    def figures(self) -> ReportedFigures:
        """Get the researched figures, checked against the chronology.

        Returns:
            ReportedFigures: The researched figures.

        Raises:
            CuratedBundleError: If the file cannot be read or is invalid.
            CuratedCatalogError: If the rows do not make valid figures, or name a company outside the chronology.
        """
        figures = self.assembler.figures(self._part(CuratedFile.FIGURES))
        unknown = self.checks.unknown_figure_companies(figures, self.chronology())
        if unknown:
            self.logger.error("The bundled figures name companies outside the chronology: %s", unknown)
            raise CuratedCatalogError("figures", f"unknown companies (define them in the chronology): {unknown}")
        return figures

    def launches(self) -> LaunchCatalog:
        """Get the launch dates catalogue.

        Returns:
            LaunchCatalog: The launch dates catalogue.

        Raises:
            CuratedBundleError: If the file cannot be read or is invalid.
            CuratedCatalogError: If the rows do not make a valid catalogue.
        """
        return self.assembler.launches(self._part(CuratedFile.LAUNCHES))
