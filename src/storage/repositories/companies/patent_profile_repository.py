from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple, Union, cast

# Third Party Imports.
from sqlalchemy import Select, Table, delete, func, insert, literal, or_, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# First Party Imports.
from models.companies.stored.patents.assignee_profile import AssigneeProfile
from models.companies.stored.patents.inventor_profile import InventorProfile
from models.storage.records.enums import RecordSort
from models.storage.records.record_page import RecordPage
from models.storage.records.record_query import RecordQuery
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.record_pager import RecordPager, RecordValue
from storage.tables.base import Base
from storage.tables.companies.graph.assignee_profile_row import AssigneeProfileRow
from storage.tables.companies.graph.inventor_profile_row import InventorProfileRow

type ProfileRow = Dict[str, Optional[Union[str, int, date]]]


class PatentProfileRepository:
    """Create, read, update, delete and list the inventor profiles, derived with the assignee profiles from patents.

    Attributes:
        INVENTORS (ClassVar[str]): The query deriving the inventor profiles.
        ASSIGNEES (ClassVar[str]): The query deriving the assignee profiles.
        TOP (ClassVar[int]): The classes, offices and inventors a profile lists.
        database (Database): The open database.
        logger (Logger): The repository logger.
        inventors (Table): The `inventor_profiles` table.
        assignees (Table): The `assignee_profiles` table.
        pager (RecordPager): The reader of the pages of the Patents & Papers tab.

    Notes:
        - An inventor is identified by the folded spelling of their name across every company (Google Patents
          gives no inventor identifier): two homonyms share a profile, the profile of a prolific name is an upper
          bound.
        - The profiles are derived again, whole, after each patents crawl: they never need to be edited, and a
          profile written by `create` or `update` lasts until the next derivation.
        - The inventor profile is the main entity, the assignee profiles are derived and read beside it.
    """

    INVENTORS: ClassVar[str] = """
        INSERT INTO inventor_profiles (name_key, name, publications, families, first_priority, last_priority,
                                       companies, top_cpc, co_inventors, citations_received)
        WITH base AS (
            SELECT i.name_key, i.name, p.publication_number, coalesce(p.family_id, p.publication_number) AS family,
                   p.priority_date
            FROM patent_inventors i JOIN patents p ON p.publication_number = i.publication_number
            WHERE i.name_key <> ''
        ), cpc AS (
            SELECT name_key, string_agg(cpc, ',' ORDER BY n DESC, cpc) AS top_cpc FROM (
                SELECT b.name_key, c.cpc, count(*) AS n,
                       row_number() OVER (PARTITION BY b.name_key ORDER BY count(*) DESC, c.cpc) AS rank
                FROM base b JOIN patent_classifications c ON c.publication_number = b.publication_number AND c.main
                GROUP BY b.name_key, c.cpc
            ) ranked WHERE rank <= :top GROUP BY name_key
        ), owners AS (
            SELECT b.name_key, string_agg(DISTINCT pc.company, ',' ORDER BY pc.company) AS companies
            FROM base b JOIN patent_companies pc ON pc.publication_number = b.publication_number GROUP BY b.name_key
        ), peers AS (
            SELECT a.name_key, count(DISTINCT o.name_key) AS co_inventors
            FROM patent_inventors a JOIN patent_inventors o
              ON o.publication_number = a.publication_number AND o.name_key <> a.name_key
            GROUP BY a.name_key
        ), cited AS (
            SELECT b.name_key, count(*) AS received
            FROM base b JOIN patent_citations c ON c.publication_number = b.publication_number AND c.kind = 'cited-by'
            GROUP BY b.name_key
        )
        SELECT b.name_key, mode() WITHIN GROUP (ORDER BY b.name), count(DISTINCT b.publication_number),
               count(DISTINCT b.family), min(b.priority_date), max(b.priority_date), coalesce(o.companies, ''),
               cpc.top_cpc, coalesce(peers.co_inventors, 0), coalesce(cited.received, 0)
        FROM base b
        LEFT JOIN owners o ON o.name_key = b.name_key
        LEFT JOIN cpc ON cpc.name_key = b.name_key
        LEFT JOIN peers ON peers.name_key = b.name_key
        LEFT JOIN cited ON cited.name_key = b.name_key
        GROUP BY b.name_key, o.companies, cpc.top_cpc, peers.co_inventors, cited.received
    """
    ASSIGNEES: ClassVar[str] = """
        INSERT INTO assignee_profiles (company, name, publications, first_year, last_year, countries, top_cpc,
                                       top_inventors)
        WITH base AS (
            SELECT pc.company, p.assignee AS name, p.publication_number, p.country, p.priority_date
            FROM patent_companies pc JOIN patents p ON p.publication_number = pc.publication_number
            WHERE p.assignee IS NOT NULL AND p.assignee <> ''
        ), offices AS (
            SELECT company, name, string_agg(country, ',' ORDER BY n DESC, country) AS countries FROM (
                SELECT company, name, country, count(*) AS n FROM base GROUP BY company, name, country
            ) counted GROUP BY company, name
        ), cpc AS (
            SELECT company, name, string_agg(cpc, ',' ORDER BY n DESC, cpc) AS top_cpc FROM (
                SELECT b.company, b.name, c.cpc, count(*) AS n,
                       row_number() OVER (PARTITION BY b.company, b.name ORDER BY count(*) DESC, c.cpc) AS rank
                FROM base b JOIN patent_classifications c ON c.publication_number = b.publication_number AND c.main
                GROUP BY b.company, b.name, c.cpc
            ) ranked WHERE rank <= :top GROUP BY company, name
        ), people AS (
            SELECT company, name, string_agg(inventor, ', ' ORDER BY n DESC, inventor) AS top_inventors FROM (
                SELECT b.company, b.name, i.name AS inventor, count(*) AS n,
                       row_number() OVER (PARTITION BY b.company, b.name ORDER BY count(*) DESC, i.name) AS rank
                FROM base b JOIN patent_inventors i ON i.publication_number = b.publication_number
                GROUP BY b.company, b.name, i.name
            ) ranked WHERE rank <= :top GROUP BY company, name
        )
        SELECT b.company, left(b.name, 300), count(DISTINCT b.publication_number),
               min(extract(year FROM b.priority_date))::int, max(extract(year FROM b.priority_date))::int,
               coalesce(o.countries, ''), cpc.top_cpc, people.top_inventors
        FROM base b
        LEFT JOIN offices o ON o.company = b.company AND o.name = b.name
        LEFT JOIN cpc ON cpc.company = b.company AND cpc.name = b.name
        LEFT JOIN people ON people.company = b.company AND people.name = b.name
        GROUP BY b.company, b.name, o.countries, cpc.top_cpc, people.top_inventors
    """
    TOP: ClassVar[int] = 5

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.inventors: Table = Base.metadata.tables[InventorProfileRow.__tablename__]
        self.assignees: Table = Base.metadata.tables[AssigneeProfileRow.__tablename__]
        self.pager = RecordPager()
        self.logger.debug("Repository of the patent profiles ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _inventor_row(self, profile: InventorProfile) -> ProfileRow:
        """Write an inventor profile as a row (its companies as a comma-separated text).

        Args:
            profile (InventorProfile): The profile.

        Returns:
            ProfileRow: The row.
        """
        return {
            "name_key": profile.name_key,
            "name": profile.name,
            "publications": profile.publications,
            "families": profile.families,
            "first_priority": profile.first_priority,
            "last_priority": profile.last_priority,
            "companies": ",".join(profile.companies),
            "top_cpc": profile.top_cpc,
            "co_inventors": profile.co_inventors,
            "citations_received": profile.citations_received,
        }

    ############################
    # Publicly Exposed Methods #
    ############################

    async def read(self, name_key: str) -> Optional[InventorProfile]:
        """Read one inventor profile.

        Args:
            name_key (str): The folded name.

        Returns:
            Optional[InventorProfile]: The profile, `None` when there is none.

        Raises:
            StorageReadError: If the profile cannot be read.
        """
        table = self.inventors
        try:
            async with self.database.connect() as connection:
                row = (await connection.execute(select(table).where(table.c.name_key == name_key))).mappings().first()
        except SQLAlchemyError as e:
            self.logger.error("The inventor profile %s cannot be read: %s", name_key, e)
            raise StorageReadError("inventor profiles", str(e)) from e
        if row is None:
            self.logger.debug("No inventor profile %s.", name_key)
            return None
        return InventorProfile.model_validate(dict(row))

    async def create(self, profile: InventorProfile) -> InventorProfile:
        """Insert one inventor profile.

        Args:
            profile (InventorProfile): The profile.

        Returns:
            InventorProfile: The profile, as stored.

        Raises:
            StorageWriteError: If a profile has the same folded name, or cannot be written.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(insert(self.inventors).values(self._inventor_row(profile)))
        except IntegrityError as e:
            self.logger.error("The inventor profile %s already exists: not created.", profile.name_key)
            raise StorageWriteError("inventor profiles", f"{profile.name_key} already exists") from e
        except SQLAlchemyError as e:
            self.logger.error("The inventor profile %s cannot be created: %s", profile.name_key, e)
            raise StorageWriteError("inventor profiles", str(e)) from e
        self.logger.info("Inventor profile %s created.", profile.name_key)
        return await self.read(profile.name_key) or profile

    async def update(self, profile: InventorProfile) -> bool:
        """Replace one inventor profile (that of the same folded name).

        Args:
            profile (InventorProfile): The profile.

        Returns:
            bool: Whether the profile existed (none is created otherwise).

        Raises:
            StorageWriteError: If the profile cannot be written.
        """
        table = self.inventors
        changes = {key: value for key, value in self._inventor_row(profile).items() if key != "name_key"}
        statement = update(table).where(table.c.name_key == profile.name_key).values(changes)
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The inventor profile %s cannot be updated: %s", profile.name_key, e)
            raise StorageWriteError("inventor profiles", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Inventor profile %s updated.", profile.name_key)
        else:
            self.logger.warning("No inventor profile %s: nothing updated.", profile.name_key)
        return found

    async def delete(self, name_key: str) -> bool:
        """Delete one inventor profile.

        Args:
            name_key (str): The folded name.

        Returns:
            bool: Whether a profile was deleted.

        Raises:
            StorageWriteError: If the profile cannot be deleted.
        """
        table = self.inventors
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(delete(table).where(table.c.name_key == name_key))
        except SQLAlchemyError as e:
            self.logger.error("The inventor profile %s cannot be deleted: %s", name_key, e)
            raise StorageWriteError("inventor profiles", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Inventor profile %s deleted.", name_key)
        else:
            self.logger.debug("No inventor profile %s: nothing deleted.", name_key)
        return found

    async def rebuild(self) -> Tuple[int, int]:
        """Derive every inventor and assignee profile again from the stored publications.

        Returns:
            Tuple[int, int]: The number of inventor profiles, then of assignee profiles.

        Raises:
            StorageWriteError: If the profiles cannot be written.
        """
        inventors, assignees = self.inventors, self.assignees
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(inventors.delete())
                await connection.execute(text(self.INVENTORS), {"top": self.TOP})
                await connection.execute(assignees.delete())
                await connection.execute(text(self.ASSIGNEES), {"top": self.TOP})
                counted = (
                    await connection.execute(
                        select(select(func.count()).select_from(inventors).scalar_subquery(), func.count()).select_from(
                            assignees
                        )
                    )
                ).one()
        except SQLAlchemyError as e:
            self.logger.error("The patent profiles cannot be derived: %s", e)
            raise StorageWriteError("patent profiles", str(e)) from e
        self.logger.info("Patent profiles derived: %d inventors, %d assignee names.", counted[0], counted[1])
        return int(counted[0]), int(counted[1])

    async def counts(self) -> Tuple[int, int]:
        """Count the stored profiles.

        Returns:
            Tuple[int, int]: The number of inventor profiles, then of assignee profiles.

        Raises:
            StorageReadError: If the profiles cannot be counted.
        """
        inventors, assignees = self.inventors, self.assignees
        try:
            async with self.database.connect() as connection:
                first = (await connection.execute(select(func.count()).select_from(inventors))).scalar_one()
                second = (await connection.execute(select(func.count()).select_from(assignees))).scalar_one()
        except SQLAlchemyError as e:
            self.logger.error("The patent profiles cannot be counted: %s", e)
            raise StorageReadError("patent profiles", str(e)) from e
        self.logger.debug("%d inventor profiles, %d assignee profiles stored.", first, second)
        return int(first), int(second)

    async def list(self, query: RecordQuery) -> RecordPage[InventorProfile]:
        """List a page of the inventor profiles.

        Args:
            query (RecordQuery): The companies, the text (in the name), the order and the bounds of the page.

        Returns:
            RecordPage[InventorProfile]: The profiles of the page, the most prolific first by default.

        Raises:
            StorageReadError: If the profiles cannot be read.

        Notes:
            A profile lists its companies as a comma-separated text: it belongs to a company asked when that
            company is one of its items.
        """
        table = self.inventors
        statement = cast(Select[Tuple[RecordValue, ...]], select(table))
        if query.companies:
            listed = literal(",") + table.c.companies + literal(",")
            statement = statement.where(or_(*(listed.contains(f",{key},") for key in query.companies)))
        sorts = {
            RecordSort.NAME: table.c.name,
            RecordSort.PUBLICATIONS: table.c.publications,
            RecordSort.CITATIONS: table.c.citations_received,
            RecordSort.FIRST: table.c.first_priority,
            RecordSort.LAST: table.c.last_priority,
        }
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.PUBLICATIONS, [table.c.name_key], [table.c.name]
                )
        except SQLAlchemyError as e:
            self.logger.error("The inventor profiles cannot be read: %s", e)
            raise StorageReadError("inventor profiles", str(e)) from e
        items = [InventorProfile.model_validate(dict(row)) for row in rows]
        self.logger.info("%d inventor profiles read from %d.", len(items), query.offset)
        return RecordPage[InventorProfile](items=items, offset=query.offset, limit=query.limit, total=total)

    async def assignee_page(self, query: RecordQuery) -> RecordPage[AssigneeProfile]:
        """Read a page of the assignee profiles.

        Args:
            query (RecordQuery): The companies, the text (in the name), the order and the bounds of the page.

        Returns:
            RecordPage[AssigneeProfile]: The profiles of the page, the most prolific first by default.

        Raises:
            StorageReadError: If the profiles cannot be read.
        """
        table = self.assignees
        statement = cast(Select[Tuple[RecordValue, ...]], select(table))
        if query.companies:
            statement = statement.where(table.c.company.in_(query.companies))
        sorts = {
            RecordSort.COMPANY: table.c.company,
            RecordSort.NAME: table.c.name,
            RecordSort.PUBLICATIONS: table.c.publications,
            RecordSort.FIRST: table.c.first_year,
            RecordSort.LAST: table.c.last_year,
        }
        keys = [table.c.company, table.c.name]
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.PUBLICATIONS, keys, [table.c.name]
                )
        except SQLAlchemyError as e:
            self.logger.error("The assignee profiles cannot be read: %s", e)
            raise StorageReadError("assignee profiles", str(e)) from e
        items = [AssigneeProfile.model_validate(dict(row)) for row in rows]
        self.logger.info("%d assignee profiles read from %d.", len(items), query.offset)
        return RecordPage[AssigneeProfile](items=items, offset=query.offset, limit=query.limit, total=total)
