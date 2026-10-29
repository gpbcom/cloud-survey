from __future__ import annotations

# Standard Library Imports.
import unicodedata
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union, cast

# Third Party Imports.
from sqlalchemy import Select, Table, delete, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.companies.enums import CompanyIndicator, PatentCitationKind, PatentWindowStatus
from models.companies.patents.patent_citation import PatentCitation
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.companies.stored.patents.patent_file import PatentFile
from models.companies.stored.patents.stored_patent import StoredPatent
from models.companies.stored.patents.stored_window import StoredWindow
from models.storage.records.enums import RecordSort
from models.storage.records.record_page import RecordPage
from models.storage.records.record_query import RecordQuery
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.record_pager import RecordPager, RecordValue
from storage.tables.base import Base
from storage.tables.companies.graph.patent_citation_row import PatentCitationRow
from storage.tables.companies.graph.patent_window_row import PatentWindowRow
from storage.tables.companies.patents.patent_assignee_row import PatentAssigneeRow
from storage.tables.companies.patents.patent_classification_row import PatentClassificationRow
from storage.tables.companies.patents.patent_company_row import PatentCompanyRow
from storage.tables.companies.patents.patent_inventor_row import PatentInventorRow
from storage.tables.companies.patents.patent_row import PatentRow

type Row = Dict[str, Optional[Union[str, int, bool, date]]]
type YearKey = Tuple[str, CompanyIndicator, int]


class PatentRepository:
    """Create, read, update, delete and list the patent publications, with their inventors, assignees and citations.

    Attributes:
        CHUNK (ClassVar[int]): The rows written per statement.
        YEARLY (ClassVar[str]): The query counting the publications, families, grants and citations per year.
        database (Database): The open database.
        patents (Table): The `patents` table.
        companies (Table): The `patent_companies` table.
        inventors (Table): The `patent_inventors` table.
        assignees (Table): The `patent_assignees` table.
        classes (Table): The `patent_classifications` table.
        citations (Table): The `patent_citations` table.
        windows (Table): The `patent_windows` table.
        logger (Logger): The repository logger.
        pager (RecordPager): The reader of the pages of the Patents & Papers tab.

    Notes:
        - A search row writes the publication once (later searches refresh its dates), links it to the company and
          adds its inventors if none is stored. A page replaces its inventors, assignees, classes and citations and
          marks it read (`detail_fetched_at`), so it leaves the queue of the pages to read.
        - The inventors' names are folded (`name_key`: case, accents and punctuation removed) for the profiles.
        - A publication is the aggregate root: `create` and `update` write its page (its inventors, assignees,
          classes and citations with it) and `delete` removes it with every row of the publication, its company
          links included. The search windows are bookkeeping of the crawls, read and written beside it.
    """

    CHUNK: ClassVar[int] = 2000
    YEARLY: ClassVar[str] = """
        WITH owned AS (
            SELECT pc.company, p.publication_number, p.family_id, p.priority_date, p.grant_date, p.detail_fetched_at
            FROM patent_companies pc JOIN patents p ON p.publication_number = pc.publication_number
            WHERE (:all_companies OR pc.company = ANY(:companies))
        ), cited AS (
            SELECT publication_number, count(*) AS received FROM patent_citations
            WHERE kind = 'cited-by' GROUP BY publication_number
        )
        SELECT company, 'patent-filings' AS indicator, extract(year FROM priority_date)::int AS year,
               count(DISTINCT publication_number)::float AS value
        FROM owned WHERE priority_date IS NOT NULL GROUP BY company, year
        UNION ALL
        SELECT company, 'patent-families', extract(year FROM priority_date)::int,
               count(DISTINCT coalesce(family_id, publication_number))::float
        FROM owned WHERE priority_date IS NOT NULL GROUP BY company, 3
        UNION ALL
        SELECT company, 'patent-grants', extract(year FROM grant_date)::int, count(DISTINCT publication_number)::float
        FROM owned WHERE grant_date IS NOT NULL GROUP BY company, 3
        UNION ALL
        SELECT o.company, 'patent-citations', extract(year FROM o.priority_date)::int,
               coalesce(sum(c.received), 0)::float
        FROM owned o LEFT JOIN cited c ON c.publication_number = o.publication_number
        WHERE o.priority_date IS NOT NULL AND o.detail_fetched_at IS NOT NULL GROUP BY o.company, 3
        UNION ALL
        SELECT o.company, 'citations-per-patent', extract(year FROM o.priority_date)::int,
               coalesce(sum(c.received), 0)::float / count(DISTINCT o.publication_number)
        FROM owned o LEFT JOIN cited c ON c.publication_number = o.publication_number
        WHERE o.priority_date IS NOT NULL AND o.detail_fetched_at IS NOT NULL GROUP BY o.company, 3
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        tables = Base.metadata.tables
        self.patents: Table = tables[PatentRow.__tablename__]
        self.companies: Table = tables[PatentCompanyRow.__tablename__]
        self.inventors: Table = tables[PatentInventorRow.__tablename__]
        self.assignees: Table = tables[PatentAssigneeRow.__tablename__]
        self.classes: Table = tables[PatentClassificationRow.__tablename__]
        self.citations: Table = tables[PatentCitationRow.__tablename__]
        self.windows: Table = tables[PatentWindowRow.__tablename__]
        self.pager = RecordPager()
        self.logger.debug("Repository of the patents ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _name_key(self, name: str) -> str:
        """Fold a name for the profiles: lower case, accents and punctuation removed, spaces collapsed.

        Args:
            name (str): The name.

        Returns:
            str: The folded name.
        """
        decomposed = unicodedata.normalize("NFKD", name.casefold())
        letters = "".join(char if char.isalnum() else " " for char in decomposed if not unicodedata.combining(char))
        return " ".join(letters.split())[:200]

    async def _insert(self, connection: AsyncConnection, table: Table, rows: List[Row]) -> None:
        """Insert rows, the ones already stored left as they are.

        Args:
            connection (AsyncConnection): The open connection, in a transaction.
            table (Table): The table.
            rows (List[Row]): The rows.
        """
        for start in range(0, len(rows), self.CHUNK):
            await connection.execute(upsert(table).values(rows[start : start + self.CHUNK]).on_conflict_do_nothing())

    def _record_row(self, record: PatentRecord) -> Row:
        """Write a search row as a `patents` row.

        Args:
            record (PatentRecord): The publication.

        Returns:
            Row: The row.
        """
        return {
            "publication_number": record.publication_number,
            "country": record.publication_number[:2],
            "title": record.title,
            "assignee": record.assignee,
            "priority_date": record.priority_date,
            "filing_date": record.filing_date,
            "publication_date": record.publication_date,
            "grant_date": record.grant_date,
            "source_url": record.source_url,
        }

    def _detail_row(self, detail: PatentDetail) -> Row:
        """Write a page as a `patents` row.

        Args:
            detail (PatentDetail): The publication's page.

        Returns:
            Row: The row.
        """
        return {
            "publication_number": detail.publication_number,
            "country": detail.publication_number[:2],
            "title": detail.title,
            "assignee": detail.assignees_original[0][:300] if detail.assignees_original else None,
            "priority_date": detail.priority_date,
            "filing_date": detail.filing_date,
            "publication_date": detail.publication_date,
            "grant_date": detail.grant_date,
            "family_id": detail.family_id,
            "abstract": detail.abstract,
            "claims": detail.claims,
            "source_url": detail.source_url,
        }

    def _patent_selection(self) -> Select[Tuple[RecordValue, ...]]:
        """Select the columns of the listed publications, with the companies whose search found each.

        Returns:
            Select[Tuple[RecordValue, ...]]: The publications, unfiltered.
        """
        patents, links = self.patents, self.companies
        owners = (
            select(func.string_agg(links.c.company, literal(",")))
            .where(links.c.publication_number == patents.c.publication_number)
            .scalar_subquery()
        )
        columns = [
            patents.c.publication_number,
            patents.c.country,
            patents.c.title,
            patents.c.assignee,
            patents.c.priority_date,
            patents.c.publication_date,
            patents.c.grant_date,
            patents.c.family_id,
            patents.c.claims,
            patents.c.detail_fetched_at.is_not(None).label("page_read"),
            patents.c.source_url,
            owners.label("companies"),
        ]
        return cast(Select[Tuple[RecordValue, ...]], select(*columns))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def delete(self, publication_number: str) -> bool:
        """Delete a publication with its inventors, assignees, classes, citations and company links.

        Args:
            publication_number (str): The publication.

        Returns:
            bool: Whether the publication was stored.

        Raises:
            StorageWriteError: If the publication cannot be deleted.
        """
        number = publication_number.strip().upper()
        owned = (self.inventors, self.assignees, self.classes, self.citations, self.companies)
        try:
            async with self.database.connect() as connection, connection.begin():
                for table in owned:
                    await connection.execute(delete(table).where(table.c.publication_number == number))
                result = await connection.execute(
                    delete(self.patents).where(self.patents.c.publication_number == number)
                )
        except SQLAlchemyError as e:
            self.logger.error("The patent %s cannot be deleted: %s", number, e)
            raise StorageWriteError("patents", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Patent %s deleted.", number)
        else:
            self.logger.debug("No patent %s: nothing deleted.", number)
        return found

    async def upsert_records(self, records: Sequence[PatentRecord]) -> int:
        """Write the publications of a search, link them to their company and add their inventors.

        Args:
            records (Sequence[PatentRecord]): The publications (homonyms already left out).

        Returns:
            int: The number of publications written.

        Raises:
            StorageWriteError: If the publications cannot be written.
        """
        unique: Dict[str, PatentRecord] = {}
        for record in records:
            unique.setdefault(record.publication_number, record)
        rows = [self._record_row(record) for record in unique.values()]
        if not rows:
            return 0
        links: List[Row] = [
            {"publication_number": record.publication_number, "company": record.company, "query": record.query}
            for record in records
        ]
        inventors: List[Row] = [
            {"publication_number": number, "position": position, "name": name[:200], "name_key": self._name_key(name)}
            for number, record in unique.items()
            for position, name in enumerate(record.inventors)
        ]
        table = self.patents
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.publication_number],
                            set_={
                                "title": func.coalesce(table.c.title, excluded.title),
                                "assignee": func.coalesce(excluded.assignee, table.c.assignee),
                                "priority_date": func.coalesce(excluded.priority_date, table.c.priority_date),
                                "filing_date": func.coalesce(excluded.filing_date, table.c.filing_date),
                                "publication_date": func.coalesce(excluded.publication_date, table.c.publication_date),
                                "grant_date": func.coalesce(excluded.grant_date, table.c.grant_date),
                                "fetched_at": func.now(),
                            },
                        )
                    )
                await self._insert(connection, self.companies, links)
                await self._insert(connection, self.inventors, inventors)
        except SQLAlchemyError as e:
            self.logger.error("The patents cannot be written: %s", e)
            raise StorageWriteError("patents", str(e)) from e
        self.logger.info("%d patents written (%d inventors).", len(rows), len(inventors))
        return len(rows)

    async def upsert_details(self, details: Sequence[PatentDetail]) -> int:
        """Write what the publication pages state, replacing their inventors, assignees, classes and citations.

        Args:
            details (Sequence[PatentDetail]): The pages.

        Returns:
            int: The number of publications written.

        Raises:
            StorageWriteError: If the pages cannot be written.
        """
        unique = {detail.publication_number: detail for detail in details}
        if not unique:
            return 0
        numbers = list(unique)
        rows = [self._detail_row(detail) for detail in unique.values()]
        inventors: List[Row] = [
            {"publication_number": number, "position": position, "name": name[:200], "name_key": self._name_key(name)}
            for number, detail in unique.items()
            for position, name in enumerate(detail.inventors)
        ]
        assignees: List[Row] = [
            {"publication_number": number, "position": position, "original": original, "name": name[:300]}
            for number, detail in unique.items()
            for original, names in ((True, detail.assignees_original), (False, detail.assignees_current))
            for position, name in enumerate(names)
        ]
        classes: List[Row] = [
            {"publication_number": number, "cpc": code, "main": index == 0}
            for number, detail in unique.items()
            for index, code in enumerate(detail.cpc)
        ]
        citations: List[Row] = [
            {
                "publication_number": number,
                "other": citation.publication_number,
                "kind": citation.kind.value,
                "examiner": citation.examiner,
                "other_priority_date": citation.priority_date,
                "other_publication_date": citation.publication_date,
                "other_assignee": citation.assignee,
                "other_title": citation.title,
            }
            for number, detail in unique.items()
            for citation in detail.citations
        ]
        table = self.patents
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.publication_number],
                            set_={
                                "title": func.coalesce(excluded.title, table.c.title),
                                "assignee": func.coalesce(table.c.assignee, excluded.assignee),
                                "priority_date": func.coalesce(excluded.priority_date, table.c.priority_date),
                                "filing_date": func.coalesce(excluded.filing_date, table.c.filing_date),
                                "publication_date": func.coalesce(excluded.publication_date, table.c.publication_date),
                                "grant_date": func.coalesce(excluded.grant_date, table.c.grant_date),
                                "family_id": excluded.family_id,
                                "abstract": excluded.abstract,
                                "claims": excluded.claims,
                                "detail_fetched_at": func.now(),
                                "fetched_at": func.now(),
                            },
                        )
                    )
                for linked in (self.inventors, self.assignees, self.classes, self.citations):
                    await connection.execute(delete(linked).where(linked.c.publication_number.in_(numbers)))
                await self._insert(connection, self.inventors, inventors)
                await self._insert(connection, self.assignees, assignees)
                await self._insert(connection, self.classes, classes)
                await self._insert(connection, self.citations, citations)
        except SQLAlchemyError as e:
            self.logger.error("The patent pages cannot be written: %s", e)
            raise StorageWriteError("patent pages", str(e)) from e
        self.logger.info("%d patent pages written (%d citations).", len(rows), len(citations))
        return len(rows)

    async def upsert_windows(self, windows: Sequence[PatentWindow]) -> int:
        """Write the windows searched, replacing those of the same company, search, dates and office.

        Args:
            windows (Sequence[PatentWindow]): The windows.

        Returns:
            int: The number of windows written.

        Raises:
            StorageWriteError: If the windows cannot be written.
        """
        rows: List[Row] = [
            {
                "company": window.company,
                "query": window.query,
                "after": window.after,
                "before": window.before,
                "country": window.country or "",
                "expected": window.expected,
                "fetched": window.fetched,
                "status": window.status.value,
            }
            for window in windows
        ]
        if not rows:
            return 0
        table = self.windows
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                table.c.company,
                                table.c.query,
                                table.c.after,
                                table.c.before,
                                table.c.country,
                            ],
                            set_={
                                "expected": excluded.expected,
                                "fetched": excluded.fetched,
                                "status": excluded.status,
                                "searched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The patent windows cannot be written: %s", e)
            raise StorageWriteError("patent windows", str(e)) from e
        self.logger.info("%d patent windows written.", len(rows))
        return len(rows)

    async def read_windows(self, companies: Optional[Sequence[str]] = None) -> List[PatentWindow]:
        """Read the windows searched.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            List[PatentWindow]: The windows.

        Raises:
            StorageReadError: If the windows cannot be read.
        """
        table = self.windows
        statement = select(table).order_by(table.c.company, table.c.query, table.c.after)
        if companies:
            statement = statement.where(table.c.company.in_(list(companies)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The patent windows cannot be read: %s", e)
            raise StorageReadError("patent windows", str(e)) from e
        windows = [
            PatentWindow(
                company=row["company"],
                query=row["query"],
                after=row["after"],
                before=row["before"],
                country=row["country"] or None,
                expected=row["expected"],
                fetched=row["fetched"],
                status=PatentWindowStatus(row["status"]),
            )
            for row in rows
        ]
        self.logger.debug("%d patent windows read.", len(windows))
        return windows

    async def queue(self, companies: Optional[Sequence[str]] = None, limit: int = 2000) -> List[str]:
        """Get the publications whose page is still to be read: granted ones first, the most recent first.

        Args:
            companies (Optional[Sequence[str]]): Only the publications of these companies, every one when empty.
            limit (int): The most publications returned.

        Returns:
            List[str]: The publications, in the order their pages are read.

        Raises:
            StorageReadError: If the publications cannot be read.
        """
        patents, links = self.patents, self.companies
        statement = (
            select(patents.c.publication_number)
            .where(patents.c.detail_fetched_at.is_(None))
            .order_by(patents.c.grant_date.is_(None), patents.c.priority_date.desc().nulls_last())
            .limit(limit)
        )
        if companies:
            owned = select(links.c.publication_number).where(links.c.company.in_(list(companies)))
            statement = statement.where(patents.c.publication_number.in_(owned))
        try:
            async with self.database.connect() as connection:
                numbers = [str(row[0]) for row in (await connection.execute(statement)).all()]
        except SQLAlchemyError as e:
            self.logger.error("The queue of the patent pages cannot be read: %s", e)
            raise StorageReadError("patents", str(e)) from e
        self.logger.info("%d publication pages waiting to be read (limit %d).", len(numbers), limit)
        return numbers

    async def yearly(self, companies: Optional[Sequence[str]] = None) -> Dict[YearKey, float]:
        """Count the publications, families, grants and citations of each company per year.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            Dict[YearKey, float]: The value of each patents indicator, by company, indicator and year.

        Raises:
            StorageReadError: If the patents cannot be read.

        Notes:
            The filings, families and citations are counted by priority year (the year of the invention), the
            grants by grant year. The citations count only the publications whose page was read.
        """
        parameters = {"all_companies": not companies, "companies": list(companies or [])}
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(text(self.YEARLY), parameters)).all()
        except SQLAlchemyError as e:
            self.logger.error("The yearly patents counts cannot be read: %s", e)
            raise StorageReadError("patents", str(e)) from e
        counts = {(str(row[0]), CompanyIndicator(str(row[1])), int(row[2])): float(row[3]) for row in rows}
        self.logger.debug("%d yearly patents counts read.", len(counts))
        return counts

    async def coverage(self, companies: Optional[Sequence[str]] = None) -> Dict[str, Tuple[int, int, int, int]]:
        """Count what is stored of each company's patents (the explorer's Patents & Papers tab).

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            Dict[str, Tuple[int, int, int, int]]: The publications found, those whose page was read, the search
                windows complete and the windows still open (pending or incomplete), by company.

        Raises:
            StorageReadError: If the patents cannot be read.
        """
        links, patents, windows = self.companies, self.patents, self.windows
        found = (
            select(links.c.company, func.count(), func.count(patents.c.detail_fetched_at))
            .select_from(links.join(patents, links.c.publication_number == patents.c.publication_number))
            .group_by(links.c.company)
        )
        searched = select(
            windows.c.company,
            func.count().filter(windows.c.status == PatentWindowStatus.COMPLETE.value),
            func.count().filter(
                windows.c.status.in_([PatentWindowStatus.PENDING.value, PatentWindowStatus.INCOMPLETE.value])
            ),
        ).group_by(windows.c.company)
        if companies:
            found = found.where(links.c.company.in_(list(companies)))
            searched = searched.where(windows.c.company.in_(list(companies)))
        try:
            async with self.database.connect() as connection:
                found_rows = (await connection.execute(found)).all()
                window_rows = (await connection.execute(searched)).all()
        except SQLAlchemyError as e:
            self.logger.error("The patents coverage cannot be read: %s", e)
            raise StorageReadError("patents", str(e)) from e
        coverage: Dict[str, Tuple[int, int, int, int]] = {}
        for company, total, read in found_rows:
            coverage[str(company)] = (int(total), int(read), 0, 0)
        for company, done, still in window_rows:
            total, read, _, _ = coverage.get(str(company), (0, 0, 0, 0))
            coverage[str(company)] = (total, read, int(done), int(still))
        self.logger.debug("Patents coverage read for %d companies.", len(coverage))
        return coverage

    async def list(self, query: RecordQuery) -> RecordPage[StoredPatent]:
        """List a page of the stored publications (the Stored data of the Patents & Papers tab).

        Args:
            query (RecordQuery): The companies, the text (in the publication, its title or its assignee), the order
                and the bounds of the page.

        Returns:
            RecordPage[StoredPatent]: The publications of the page, the most recent priority first by default.

        Raises:
            StorageReadError: If the publications cannot be read.
        """
        patents, links = self.patents, self.companies
        statement = self._patent_selection()
        if query.companies:
            owned = select(links.c.publication_number).where(links.c.company.in_(query.companies))
            statement = statement.where(patents.c.publication_number.in_(owned))
        sorts = {
            RecordSort.PUBLICATION: patents.c.publication_number,
            RecordSort.TITLE: patents.c.title,
            RecordSort.ASSIGNEE: patents.c.assignee,
            RecordSort.PRIORITY: patents.c.priority_date,
            RecordSort.PUBLISHED: patents.c.publication_date,
            RecordSort.GRANTED: patents.c.grant_date,
        }
        searched = [patents.c.publication_number, patents.c.title, patents.c.assignee]
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.PRIORITY, [patents.c.publication_number], searched
                )
        except SQLAlchemyError as e:
            self.logger.error("The stored patents cannot be read: %s", e)
            raise StorageReadError("patents", str(e)) from e
        items = [StoredPatent.model_validate(dict(row)) for row in rows]
        self.logger.info("%d stored patents read from %d.", len(items), query.offset)
        return RecordPage[StoredPatent](items=items, offset=query.offset, limit=query.limit, total=total)

    async def read(self, publication_number: str) -> Optional[PatentFile]:
        """Read everything stored about one publication: its abstract, inventors, assignees, classes and citations.

        Args:
            publication_number (str): The publication.

        Returns:
            Optional[PatentFile]: The publication, `None` when it is not stored.

        Raises:
            StorageReadError: If the publication cannot be read.
        """
        number = publication_number.strip().upper()
        patents = self.patents
        inventors, assignees, classes, citations = self.inventors, self.assignees, self.classes, self.citations
        try:
            async with self.database.connect() as connection:
                head = (
                    (
                        await connection.execute(
                            self._patent_selection()
                            .add_columns(patents.c.abstract)
                            .where(patents.c.publication_number == number)
                        )
                    )
                    .mappings()
                    .first()
                )
                if head is None:
                    self.logger.warning("The patent %s is not stored.", number)
                    return None
                names = (
                    await connection.execute(
                        select(inventors.c.name)
                        .where(inventors.c.publication_number == number)
                        .order_by(inventors.c.position)
                    )
                ).all()
                owners = (
                    await connection.execute(
                        select(assignees.c.original, assignees.c.name)
                        .where(assignees.c.publication_number == number)
                        .order_by(assignees.c.original.desc(), assignees.c.position)
                    )
                ).all()
                codes = (
                    await connection.execute(
                        select(classes.c.cpc)
                        .where(classes.c.publication_number == number)
                        .order_by(classes.c.main.desc(), classes.c.cpc)
                    )
                ).all()
                cited = (
                    (
                        await connection.execute(
                            select(citations)
                            .where(citations.c.publication_number == number)
                            .order_by(citations.c.kind, citations.c.other_priority_date.desc().nulls_last())
                        )
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError as e:
            self.logger.error("The patent %s cannot be read: %s", number, e)
            raise StorageReadError("patents", str(e)) from e
        known = {kind.value for kind in PatentCitationKind}
        file = PatentFile(
            patent=StoredPatent.model_validate({key: value for key, value in head.items() if key != "abstract"}),
            abstract=head["abstract"],
            inventors=[str(row[0]) for row in names],
            assignees_original=[str(row[1]) for row in owners if row[0]],
            assignees_current=[str(row[1]) for row in owners if not row[0]],
            cpc=[str(row[0]) for row in codes],
            citations=[
                PatentCitation(
                    publication_number=row["other"],
                    kind=PatentCitationKind(row["kind"]),
                    examiner=row["examiner"],
                    priority_date=row["other_priority_date"],
                    publication_date=row["other_publication_date"],
                    assignee=row["other_assignee"],
                    title=row["other_title"],
                )
                for row in cited
                if row["kind"] in known
            ],
        )
        self.logger.debug("Patent %s read: %d citations.", number, len(file.citations))
        return file

    async def create(self, detail: PatentDetail) -> PatentFile:
        """Store a publication never stored, from its page (linked to no company: a search links it).

        Args:
            detail (PatentDetail): The publication's page.

        Returns:
            PatentFile: The publication, as stored.

        Raises:
            StorageWriteError: If the publication is already stored, or cannot be written.
        """
        if await self.read(detail.publication_number) is not None:
            self.logger.error("The patent %s is already stored: not created.", detail.publication_number)
            raise StorageWriteError("patents", f"{detail.publication_number} already exists")
        await self.upsert_details([detail])
        created = await self.read(detail.publication_number)
        if created is None:
            self.logger.error("The patent %s was written but cannot be read back.", detail.publication_number)
            raise StorageWriteError("patents", f"{detail.publication_number} was not stored")
        self.logger.info("Patent %s created.", detail.publication_number)
        return created

    async def update(self, detail: PatentDetail) -> bool:
        """Replace what a stored publication's page states (its inventors, assignees, classes and citations).

        Args:
            detail (PatentDetail): The publication's page.

        Returns:
            bool: Whether the publication was stored (none is created otherwise).

        Raises:
            StorageWriteError: If the publication cannot be written.
        """
        if await self.read(detail.publication_number) is None:
            self.logger.warning("The patent %s is not stored: nothing updated.", detail.publication_number)
            return False
        await self.upsert_details([detail])
        self.logger.info("Patent %s updated.", detail.publication_number)
        return True

    async def window_page(self, query: RecordQuery) -> RecordPage[StoredWindow]:
        """Read a page of the patents search windows.

        Args:
            query (RecordQuery): The companies, the text (in the company or the assignee searched), the order and
                the bounds of the page.

        Returns:
            RecordPage[StoredWindow]: The windows of the page, the latest first by default.

        Raises:
            StorageReadError: If the windows cannot be read.
        """
        table = self.windows
        statement = cast(Select[Tuple[RecordValue, ...]], select(table))
        if query.companies:
            statement = statement.where(table.c.company.in_(query.companies))
        sorts = {
            RecordSort.COMPANY: table.c.company,
            RecordSort.AFTER: table.c.after,
            RecordSort.STATUS: table.c.status,
            RecordSort.EXPECTED: table.c.expected,
            RecordSort.FETCHED: table.c.fetched,
            RecordSort.SEARCHED: table.c.searched_at,
        }
        keys = [table.c.company, table.c.query, table.c.after, table.c.before, table.c.country]
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.AFTER, keys, [table.c.company, table.c.query]
                )
        except SQLAlchemyError as e:
            self.logger.error("The patent windows cannot be read: %s", e)
            raise StorageReadError("patent windows", str(e)) from e
        items = [StoredWindow.model_validate({**row, "country": row["country"] or None}) for row in rows]
        self.logger.info("%d patent windows read from %d.", len(items), query.offset)
        return RecordPage[StoredWindow](items=items, offset=query.offset, limit=query.limit, total=total)
