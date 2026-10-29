from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from curated.bundle.bundle_files import BundleFiles
from models.curated.enums import CuratedFile
from models.curated.records.curated_bundle import CuratedBundle
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.repositories.curated.companies.company_identifier_repository import CompanyIdentifierRepository
from storage.repositories.curated.companies.company_profile_repository import CompanyProfileRepository
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.repositories.curated.figures.reported_company_repository import ReportedCompanyRepository
from storage.repositories.curated.figures.reported_event_repository import ReportedEventRepository
from storage.repositories.curated.figures.reported_year_repository import ReportedYearRepository
from storage.repositories.curated.launches.product_launch_repository import ProductLaunchRepository
from storage.repositories.curated.records.curated_record_repository import CuratedRecordRepository


class CuratedSeeder:
    """Apply the curated bundle (`data/curated/*.json`) to the database, file by file.

    Attributes:
        LOCK_KEYS (ClassVar[Tuple[int, int]]): The keys of the advisory lock of the seed (after the taxonomy's).
        database (Database): The open database.
        state (CuratedStateRepository): The seed and the revision of each bundle file.
        records (CuratedRecordRepository): The chronology and markets sections.
        profiles (CompanyProfileRepository): The companies crawled.
        identifiers (CompanyIdentifierRepository): Their identifiers.
        figure_companies (ReportedCompanyRepository): The companies whose figures were researched.
        figure_years (ReportedYearRepository): The researched fiscal years.
        figure_events (ReportedEventRepository): The researched events.
        launches (ProductLaunchRepository): The curated launches.
        logger (Logger): The seeder logger.

    Notes:
        - A file is applied when its hash differs from the one last applied (or when forced). Its rows replace those
          of the same key, except the rows a person changed (`edited`), kept unless asked.
        - A row of the database the bundle no longer holds is kept: the seed never deletes.
        - Each file is applied in one transaction under an advisory lock: concurrent processes seed once.
    """

    LOCK_KEYS: ClassVar[Tuple[int, int]] = (5, 0)

    def __init__(
        self,
        database: Database,
        state: CuratedStateRepository,
        records: CuratedRecordRepository,
        profiles: CompanyProfileRepository,
        identifiers: CompanyIdentifierRepository,
        figure_companies: ReportedCompanyRepository,
        figure_years: ReportedYearRepository,
        figure_events: ReportedEventRepository,
        launches: ProductLaunchRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the seeder.

        Args:
            database (Database): The open database.
            state (CuratedStateRepository): The seed and the revision of each bundle file.
            records (CuratedRecordRepository): The chronology and markets sections.
            profiles (CompanyProfileRepository): The companies crawled.
            identifiers (CompanyIdentifierRepository): Their identifiers.
            figure_companies (ReportedCompanyRepository): The companies whose figures were researched.
            figure_years (ReportedYearRepository): The researched fiscal years.
            figure_events (ReportedEventRepository): The researched events.
            launches (ProductLaunchRepository): The curated launches.
            logger (Optional[Logger]): The seeder logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.state = state
        self.records = records
        self.profiles = profiles
        self.identifiers = identifiers
        self.figure_companies = figure_companies
        self.figure_years = figure_years
        self.figure_events = figure_events
        self.launches = launches

    ############################
    # Internal Helpers Methods #
    ############################

    async def _write(self, connection: AsyncConnection, part: CuratedBundle, replace_edited: bool) -> Tuple[int, int]:
        """Upsert the rows of a bundle file.

        Args:
            connection (AsyncConnection): The connection, in the seed's transaction.
            part (CuratedBundle): The rows of the file.
            replace_edited (bool): Whether the rows a person changed are replaced too.

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.
        """
        results = [
            await self.records.upsert(part.records, replace_edited, connection),
            await self.profiles.upsert(part.profiles, replace_edited, connection),
            await self.identifiers.upsert(part.identifiers, replace_edited, connection),
            await self.figure_companies.upsert(part.figure_companies, replace_edited, connection),
            await self.figure_years.upsert(part.figure_years, replace_edited, connection),
            await self.figure_events.upsert(part.figure_events, replace_edited, connection),
            await self.launches.upsert(part.launches, replace_edited, connection),
        ]
        return sum(written for written, _ in results), sum(kept for _, kept in results)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def seed(
        self, files: Optional[BundleFiles] = None, force: bool = False, replace_edited: bool = False
    ) -> Dict[CuratedFile, Tuple[int, int]]:
        """Apply the bundle files that changed since the last seed.

        Args:
            files (Optional[BundleFiles]): The bundle, `data/curated` by default.
            force (bool): Whether the files are applied even when unchanged.
            replace_edited (bool): Whether the rows a person changed are replaced too.

        Returns:
            Dict[CuratedFile, Tuple[int, int]]: For each file applied, the rows written and the rows kept because
                a person changed them.

        Raises:
            CuratedBundleError: If a bundle file cannot be read or is invalid.
            StorageWriteError: If the rows cannot be written.
        """
        bundle = files if files else BundleFiles(logger=self.logger)
        hashes = bundle.hashes()
        if not hashes:
            self.logger.warning("No curated bundle file in %s: nothing seeded.", bundle.directory)
            return {}
        applied: Dict[CuratedFile, Tuple[int, int]] = {}
        for file in CuratedFile:
            if file not in hashes:
                self.logger.warning("The curated bundle has no %s file: its rows are left as they are.", file.value)
                continue
            state = await self.state.read(file)
            if state is not None and state.seed_hash == hashes[file] and not force:
                self.logger.debug("The curated %s are up to date.", file.value)
                continue
            part = bundle.read(file)
            kind, key = self.LOCK_KEYS
            try:
                async with self.database.connect() as connection, connection.begin():
                    await connection.execute(
                        text("SELECT pg_advisory_xact_lock(:kind, :key)"), {"kind": kind, "key": key}
                    )
                    applied[file] = await self._write(connection, part, replace_edited)
                    await self.state.seeded(file, hashes[file], connection)
            except SQLAlchemyError as e:
                self.logger.error("The curated %s cannot be seeded: %s", file.value, e)
                raise StorageWriteError(f"curated {file.value}", str(e)) from e
            self.logger.info(
                "Curated %s seeded: %d rows written, %d changed by a person kept.", file.value, *applied[file]
            )
        return applied
