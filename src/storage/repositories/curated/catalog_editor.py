from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from pydantic import BaseModel

# First Party Imports.
from curated.assembly.catalog_assembler import CatalogAssembler
from curated.bundle.bundle_files import BundleFiles
from curated.catalog_checks import CatalogChecks
from models.curated.enums import CuratedFile
from models.curated.records.curated_bundle import CuratedBundle
from storage.exception import StorageWriteError
from storage.mappers.row_store import RowValue
from storage.repositories.curated.catalog_provider import CatalogProvider
from storage.repositories.curated.curated_rows import CuratedRows


class CatalogEditor:
    """Change the curated rows of a bundle file, the whole catalogue checked before anything is written.

    Attributes:
        catalogs (CatalogProvider): The curated catalogues and their repositories.
        files (BundleFiles): Splits the rows by bundle file.
        assembler (CatalogAssembler): Puts the changed rows back into their catalogue model.
        checks (CatalogChecks): The checks against the chronology.
        logger (Logger): The editor logger.

    Notes:
        - An edit is the rows a bundle file should hold: they are assembled into their catalogue (and checked against
          the chronology, or the other catalogues against a changed chronology) before the differences with the
          stored rows are written, so that a crawl never reads an invalid catalogue.
        - A database never seeded is not edited: its catalogues are those of the bundle, which the first seed would
          write over the edits.
    """

    def __init__(
        self, catalogs: CatalogProvider, files: Optional[BundleFiles] = None, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the editor.

        Args:
            catalogs (CatalogProvider): The curated catalogues and their repositories.
            files (Optional[BundleFiles]): Splits the rows by bundle file, `data/curated` by default.
            logger (Optional[Logger]): The editor logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.catalogs = catalogs
        self.files = files if files else BundleFiles(logger=self.logger)
        self.assembler = CatalogAssembler(self.logger)
        self.checks = CatalogChecks(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _key[Row: BaseModel](self, rows: CuratedRows[Row], value: Row) -> Tuple[RowValue, ...]:
        """Get the primary key of a row.

        Args:
            rows (CuratedRows[Row]): The rows of its table.
            value (Row): The row.

        Returns:
            Tuple[RowValue, ...]: The values of its key columns.
        """
        dumped = value.model_dump(mode="json")
        return tuple(dumped[column.name] for column in rows.table.primary_key.columns)

    async def _sync[Row: BaseModel](self, rows: CuratedRows[Row], before: Sequence[Row], after: Sequence[Row]) -> int:
        """Write the differences between the stored rows of a table and the wanted ones.

        Args:
            rows (CuratedRows[Row]): The rows of the table.
            before (Sequence[Row]): The stored rows of the bundle file.
            after (Sequence[Row]): The rows it should hold.

        Returns:
            int: The rows created, changed or removed.

        Raises:
            StorageWriteError: If a row cannot be written.
        """
        names = [column.name for column in rows.table.primary_key.columns]
        stored: Dict[Tuple[RowValue, ...], Row] = {self._key(rows, value): value for value in before}
        wanted: Dict[Tuple[RowValue, ...], Row] = {self._key(rows, value): value for value in after}
        changes = 0
        for key in stored.keys() - wanted.keys():
            await rows.delete(dict(zip(names, key, strict=True)))
            changes += 1
        for key, value in wanted.items():
            if key not in stored:
                await rows.create(value)
                changes += 1
            elif stored[key] != value:
                await rows.update(value)
                changes += 1
        return changes

    async def _seeded(self, file: CuratedFile) -> None:
        """Check that a bundle file was seeded in the database.

        Args:
            file (CuratedFile): The bundle file.

        Raises:
            StorageReadError: If the state cannot be read.
            StorageWriteError: If the file was never seeded.
        """
        state = await self.catalogs.state.read(file)
        if state is None or state.seed_hash is None:
            self.logger.error("The curated %s were never seeded: they cannot be edited.", file.value)
            raise StorageWriteError(f"curated {file.value}", "the database was never seeded (run `migrate-db seed`).")

    async def _check(self, file: CuratedFile, part: CuratedBundle) -> None:
        """Check that the rows of a bundle file make a valid catalogue.

        Args:
            file (CuratedFile): The bundle file.
            part (CuratedBundle): The rows it should hold.

        Raises:
            StorageReadError: If the other catalogues cannot be read.
            CuratedCatalogError: If the rows do not make a valid catalogue.
            StorageWriteError: If a catalogue would name a company outside the chronology.
        """
        unknown: List[str] = []
        match file:
            case CuratedFile.CHRONOLOGY:
                chronology = self.assembler.chronology(part)
                unknown += self.checks.unknown_market_companies(await self.catalogs.markets(), chronology)
                unknown += self.checks.unknown_companies(await self.catalogs.companies(), chronology)
                unknown += self.checks.unknown_figure_companies(await self.catalogs.figures(), chronology)
            case CuratedFile.MARKETS:
                markets = self.assembler.markets(part, self.catalogs.settings.block("markets"))
                unknown += self.checks.unknown_market_companies(markets, await self.catalogs.chronology())
            case CuratedFile.COMPANIES:
                companies = self.assembler.companies(part, self.catalogs.settings.block("companies"))
                unknown += self.checks.unknown_companies(companies, await self.catalogs.chronology())
            case CuratedFile.FIGURES:
                figures = self.assembler.figures(part)
                unknown += self.checks.unknown_figure_companies(figures, await self.catalogs.chronology())
            case CuratedFile.LAUNCHES:
                self.assembler.launches(part)
        if unknown:
            self.logger.error("The edited %s would name companies outside the chronology: %s", file.value, unknown)
            raise StorageWriteError(
                f"curated {file.value}", f"unknown companies (define them in the chronology): {sorted(set(unknown))}"
            )
        self.logger.debug("The edited %s make a valid catalogue.", file.value)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def part(self, file: CuratedFile) -> CuratedBundle:
        """Read the stored rows of a bundle file.

        Args:
            file (CuratedFile): The bundle file.

        Returns:
            CuratedBundle: Its rows, in their order.

        Raises:
            StorageReadError: If the rows cannot be read.
        """
        part = self.files.part(await self.catalogs.bundle(), file)
        self.logger.debug("Curated %s read for editing.", file.value)
        return part

    async def save(self, file: CuratedFile, part: CuratedBundle) -> int:
        """Make the stored rows of a bundle file those of an edit, once they make a valid catalogue.

        Args:
            file (CuratedFile): The bundle file.
            part (CuratedBundle): The rows it should hold (those of the other files are ignored).

        Returns:
            int: The rows created, changed or removed.

        Raises:
            StorageReadError: If the stored rows cannot be read.
            CuratedCatalogError: If the rows do not make a valid catalogue.
            StorageWriteError: If the file was never seeded, a catalogue would name a company outside the chronology,
                or a row cannot be written.
        """
        await self._seeded(file)
        wanted = self.files.part(part, file)
        await self._check(file, wanted)
        stored = await self.part(file)
        catalogs = self.catalogs
        changes = await self._sync(catalogs.records.rows, stored.records, wanted.records)
        changes += await self._sync(catalogs.profiles.rows, stored.profiles, wanted.profiles)
        changes += await self._sync(catalogs.identifiers.rows, stored.identifiers, wanted.identifiers)
        changes += await self._sync(catalogs.figure_companies.rows, stored.figure_companies, wanted.figure_companies)
        changes += await self._sync(catalogs.figure_years.rows, stored.figure_years, wanted.figure_years)
        changes += await self._sync(catalogs.figure_events.rows, stored.figure_events, wanted.figure_events)
        changes += await self._sync(catalogs.launches_rows.rows, stored.launches, wanted.launches)
        if changes:
            self.logger.info("Curated %s edited: %d rows written.", file.value, changes)
        else:
            self.logger.warning("The edit of the curated %s changes nothing.", file.value)
        return changes
