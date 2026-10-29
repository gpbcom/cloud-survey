from __future__ import annotations

# Standard Library Imports.
import asyncio
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, Optional, Type

# Third Party Imports.
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.software.marketplace import CloudMarketplace
from models.stats.market_statistics import MarketStatistics
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind, StorageTable
from storage.exception import StorageError, StorageImportError
from storage.storage import Storage


class JsonImporter:
    """Import the JSON files of the former file storage (`output/`) into the database.

    Attributes:
        MARKETPLACE_DIR (ClassVar[str]): The folder of the marketplace files, in the output folder.
        STATISTICS_DIR (ClassVar[str]): The folder of the statistics files, in the output folder.
        ANALYZED_TABLES (ClassVar[str]): The tables whose planner statistics are refreshed after an import.
        storage (Storage): The open storage.
        logger (Logger): The importer logger.

    Notes:
        Each file is imported in one transaction, its items with their dates as they are, and a version each. A
        dataset already stored is kept, unless it is replaced. The files are left in place.
    """

    MARKETPLACE_DIR: ClassVar[str] = "marketplaces"
    STATISTICS_DIR: ClassVar[str] = "stats"
    ANALYZED_TABLES: ClassVar[str] = ", ".join(StorageTable)

    def __init__(self, storage: Storage, logger: Optional[Logger] = None) -> None:
        """Initialize the importer.

        Args:
            storage (Storage): The open storage.
            logger (Optional[Logger]): The importer logger.
        """
        self.storage = storage
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("JSON importer into %s ready.", storage.url)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _read[D: BaseModel](self, path: Path, model: Type[D]) -> D:
        """Read and validate a JSON file, in a thread (a marketplace file is tens of megabytes).

        Args:
            path (Path): The JSON file.
            model (Type[D]): The document model.

        Returns:
            D: The validated document.

        Raises:
            StorageImportError: If the file cannot be read or is invalid.
        """
        try:
            content = await asyncio.to_thread(path.read_bytes)
            return await asyncio.to_thread(model.model_validate_json, content)
        except OSError as e:
            self.logger.error("The file %s cannot be read: %s", path, e)
            raise StorageImportError(str(path), f"the file cannot be read ({e.strerror})") from e
        except ValidationError as e:
            self.logger.error("The file %s is invalid: %d errors.", path, e.error_count())
            raise StorageImportError(str(path), f"invalid content ({e.error_count()} errors)") from e

    async def _import_catalogue(self, path: Path, replace: bool) -> Optional[CrawlSummary]:
        """Import a catalogue file.

        Args:
            path (Path): The catalogue file, named after its provider.
            replace (bool): Whether a stored catalogue is replaced.

        Returns:
            Optional[CrawlSummary]: What was imported, `None` when the catalogue is kept.

        Raises:
            StorageImportError: If the file is unusable.
            StorageError: If the catalogue cannot be written.
        """
        catalogue = await self._read(path, CloudCatalogue)
        if catalogue.provider.value != path.stem:
            self.logger.error("The file %s holds the %s catalogue.", path, catalogue.provider.value)
            raise StorageImportError(str(path), f"it holds the {catalogue.provider.value} catalogue")
        return await self.storage.catalogues.import_items(
            catalogue.provider, catalogue.crawled_at, catalogue.products, replace
        )

    async def _import_marketplace(self, path: Path, replace: bool) -> Optional[CrawlSummary]:
        """Import a marketplace file.

        Args:
            path (Path): The marketplace file, named after its provider.
            replace (bool): Whether a stored marketplace is replaced.

        Returns:
            Optional[CrawlSummary]: What was imported, `None` when the marketplace is kept.

        Raises:
            StorageImportError: If the file is unusable.
            StorageError: If the marketplace cannot be written.
        """
        marketplace = await self._read(path, CloudMarketplace)
        if marketplace.provider.value != path.stem:
            self.logger.error("The file %s holds the %s marketplace.", path, marketplace.provider.value)
            raise StorageImportError(str(path), f"it holds the {marketplace.provider.value} marketplace")
        return await self.storage.marketplaces.import_items(
            marketplace.provider, marketplace.crawled_at, marketplace.software, replace
        )

    async def _import_statistics(self, path: Path, replace: bool) -> Optional[CrawlSummary]:
        """Import a statistics file.

        Args:
            path (Path): The statistics file, named after its source.
            replace (bool): Whether stored statistics are replaced.

        Returns:
            Optional[CrawlSummary]: What was imported,
                `None` when the statistics are kept.

        Raises:
            StorageImportError: If the file is unusable.
            StorageError: If the statistics cannot be written.
        """
        statistics = await self._read(path, MarketStatistics)
        stamps = await self.storage.datasets.list()
        stored = any(stamp.kind is DatasetKind.STATISTICS and stamp.dataset == path.stem for stamp in stamps)
        if stored and not replace:
            self.logger.warning("The %s statistics are already stored: %s is not imported.", path.stem, path)
            return None
        return await self.storage.statistics.replace(path.stem, statistics, status=CrawlStatus.IMPORTED)

    async def _analyze(self) -> None:
        """Refresh the planner statistics of the imported tables (logged when it fails)."""
        try:
            async with self.storage.database.connect() as connection:
                await connection.execute(text(f"ANALYZE {self.ANALYZED_TABLES}"))
                await connection.commit()
        except SQLAlchemyError as e:
            self.logger.warning("The planner statistics could not be refreshed: %s", e)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def import_folder(self, folder: Path, replace: bool = False) -> Dict[str, int]:
        """Import every JSON file of an output folder: catalogues, marketplaces and statistics.

        Args:
            folder (Path): The output folder (`output/` by default for the crawler).
            replace (bool): Whether the stored datasets are replaced (else they are kept).

        Returns:
            Dict[str, int]: The number of items imported,
                by file (relative to the folder).
                An unusable file is logged and skipped.
        """
        jobs = [
            *((path, self._import_catalogue) for path in sorted(folder.glob("*.json"))),
            *((path, self._import_marketplace) for path in sorted((folder / self.MARKETPLACE_DIR).glob("*.json"))),
            *((path, self._import_statistics) for path in sorted((folder / self.STATISTICS_DIR).glob("*.json"))),
        ]
        self.logger.info("Importing %d JSON files of %s into %s.", len(jobs), folder, self.storage.url)
        imported: Dict[str, int] = {}
        for path, job in jobs:
            name = str(path.relative_to(folder))
            try:
                summary = await job(path, replace)
            except StorageError as e:
                self.logger.error("%s is not imported: %s", name, e)
                continue
            if summary is not None:
                imported[name] = summary.found
                self.logger.info("%s imported: %d items.", name, summary.found)
        if imported:
            await self._analyze()
        self.logger.info("%d of %d JSON files imported.", len(imported), len(jobs))
        return imported
