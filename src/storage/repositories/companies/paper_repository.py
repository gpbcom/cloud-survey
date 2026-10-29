from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple, Union, cast

# Third Party Imports.
from sqlalchemy import Select, String, Table, delete, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.companies.enums import CompanyIndicator
from models.companies.papers.paper_authorship import PaperAuthorship
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.stored.papers.stored_paper import StoredPaper
from models.companies.stored.papers.stored_researcher import StoredResearcher
from models.storage.records.enums import RecordSort
from models.storage.records.record_page import RecordPage
from models.storage.records.record_query import RecordQuery
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.record_pager import RecordPager, RecordValue
from storage.tables.base import Base
from storage.tables.companies.papers.paper_author_row import PaperAuthorRow
from storage.tables.companies.papers.paper_company_row import PaperCompanyRow
from storage.tables.companies.papers.research_paper_row import ResearchPaperRow
from storage.tables.companies.papers.researcher_profile_row import ResearcherProfileRow

type Row = Dict[str, Optional[Union[str, int, float, bool, date]]]
type YearKey = Tuple[str, CompanyIndicator, int]


class PaperRepository:
    """Create, read, update, delete and list the research papers, with their authors, and the researchers' profiles.

    Attributes:
        CHUNK (ClassVar[int]): The rows written per statement.
        YEARLY (ClassVar[str]): The query summing the citations and averaging the impact of the papers per year.
        CONFIRM_BY_PROFILE (ClassVar[str]): The statement confirming the researchers by their profile.
        CONFIRM_BY_PAPERS (ClassVar[str]): The statement confirming the researchers by their stored papers.
        STALE_SHARES (ClassVar[str]): The query counting each company's links a search did not find again.
        ORPHANS (ClassVar[str]): The query of the papers linked to no company.
        database (Database): The open database.
        papers (Table): The `research_papers` table.
        companies (Table): The `paper_companies` table.
        authors (Table): The `paper_authors` table.
        researchers (Table): The `researcher_profiles` table.
        logger (Logger): The repository logger.
        pager (RecordPager): The reader of the pages of the Patents & Papers tab.

    Notes:
        - A paper is written once (a later crawl refreshes its citations), linked to every company whose
          institutions it is affiliated with, its authors replaced by the last crawl's.
        - A paper is the aggregate root: `create` and `update` write it with its authors and its company link,
          `delete` removes it with every author and company link. The researcher profiles are read and written
          beside it.
    """

    CHUNK: ClassVar[int] = 1000
    YEARLY: ClassVar[str] = """
        SELECT pc.company, 'paper-citations' AS indicator, p.publication_year, sum(p.cited_by_count)::float
        FROM paper_companies pc JOIN research_papers p ON p.openalex_id = pc.openalex_id
        WHERE p.publication_year IS NOT NULL AND (:all_companies OR pc.company = ANY(:companies))
        GROUP BY pc.company, p.publication_year
        UNION ALL
        SELECT pc.company, 'paper-fwci', p.publication_year, avg(p.fwci)::float
        FROM paper_companies pc JOIN research_papers p ON p.openalex_id = pc.openalex_id
        WHERE p.publication_year IS NOT NULL AND p.fwci IS NOT NULL
          AND (:all_companies OR pc.company = ANY(:companies))
        GROUP BY pc.company, p.publication_year
    """

    CONFIRM_BY_PROFILE: ClassVar[str] = """
        UPDATE researcher_profiles SET confirmed = (current_affiliation OR affiliation_years >= :years)
        WHERE company = ANY(:companies)
    """
    CONFIRM_BY_PAPERS: ClassVar[str] = """
        UPDATE researcher_profiles r SET confirmed = true
        FROM (
            SELECT a.author_id, pc.company FROM paper_authors a
            JOIN paper_companies pc ON pc.openalex_id = a.openalex_id
            WHERE a.company_affiliated AND a.author_id IS NOT NULL AND pc.company = ANY(:companies)
            GROUP BY a.author_id, pc.company HAVING count(DISTINCT a.openalex_id) >= :papers
        ) signed
        WHERE signed.author_id = r.author_id AND signed.company = r.company AND NOT r.confirmed
    """
    STALE_SHARES: ClassVar[str] = """
        SELECT company, count(*) FILTER (WHERE linked_at < :since), count(*) FROM paper_companies
        WHERE company = ANY(:companies) GROUP BY company
    """
    ORPHANS: ClassVar[str] = """
        SELECT p.openalex_id FROM research_papers p
        WHERE NOT EXISTS (SELECT 1 FROM paper_companies pc WHERE pc.openalex_id = p.openalex_id)
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
        self.papers: Table = tables[ResearchPaperRow.__tablename__]
        self.companies: Table = tables[PaperCompanyRow.__tablename__]
        self.authors: Table = tables[PaperAuthorRow.__tablename__]
        self.researchers: Table = tables[ResearcherProfileRow.__tablename__]
        self.pager = RecordPager()
        self.logger.debug("Repository of the research papers ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _paper_selection(self) -> Select[Tuple[RecordValue, ...]]:
        """Select the columns of the listed papers, with the companies each is affiliated with.

        Returns:
            Select[Tuple[RecordValue, ...]]: The papers, unfiltered.
        """
        papers, links = self.papers, self.companies
        owners = (
            select(func.string_agg(links.c.company, literal(",")))
            .where(links.c.openalex_id == papers.c.openalex_id)
            .scalar_subquery()
        )
        columns = [
            papers.c.openalex_id,
            papers.c.doi,
            papers.c.title,
            papers.c.publication_year,
            papers.c.publication_date,
            papers.c.type,
            papers.c.venue,
            papers.c.cited_by_count,
            papers.c.fwci,
            papers.c.is_oa,
            papers.c.topic,
            papers.c.source_url,
            owners.label("companies"),
        ]
        return cast(Select[Tuple[RecordValue, ...]], select(*columns))

    async def _drop_orphans(self, connection: AsyncConnection) -> None:
        """Remove the papers linked to no company any more, with their authors.

        Args:
            connection (AsyncConnection): The open connection, in a transaction.
        """
        orphans = text(self.ORPHANS).columns(openalex_id=String()).subquery()
        await connection.execute(delete(self.authors).where(self.authors.c.openalex_id.in_(select(orphans))))
        removed = (
            await connection.execute(delete(self.papers).where(self.papers.c.openalex_id.in_(select(orphans))))
        ).rowcount
        self.logger.debug("%d papers linked to no company removed.", removed)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def delete(self, openalex_id: str) -> bool:
        """Delete a paper with its authors and company links.

        Args:
            openalex_id (str): The OpenAlex work.

        Returns:
            bool: Whether the paper was stored.

        Raises:
            StorageWriteError: If the paper cannot be deleted.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                for table in (self.authors, self.companies):
                    await connection.execute(delete(table).where(table.c.openalex_id == openalex_id))
                result = await connection.execute(delete(self.papers).where(self.papers.c.openalex_id == openalex_id))
        except SQLAlchemyError as e:
            self.logger.error("The paper %s cannot be deleted: %s", openalex_id, e)
            raise StorageWriteError("research papers", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Paper %s deleted.", openalex_id)
        else:
            self.logger.debug("No paper %s: nothing deleted.", openalex_id)
        return found

    async def upsert_papers(self, records: Sequence[PaperRecord]) -> int:
        """Write papers, link them to their company and replace their authors.

        Args:
            records (Sequence[PaperRecord]): The papers.

        Returns:
            int: The number of papers written.

        Raises:
            StorageWriteError: If the papers cannot be written.
        """
        unique: Dict[str, PaperRecord] = {record.openalex_id: record for record in records}
        if not unique:
            return 0
        rows: List[Row] = [
            {
                "openalex_id": record.openalex_id,
                "doi": record.doi,
                "title": record.title,
                "publication_year": record.publication_year,
                "publication_date": record.publication_date,
                "type": record.type,
                "venue": record.venue,
                "language": record.language,
                "cited_by_count": record.cited_by_count,
                "fwci": record.fwci,
                "is_oa": record.is_oa,
                "topic": record.topic,
                "source_url": record.source_url,
            }
            for record in unique.values()
        ]
        links: List[Row] = [{"openalex_id": record.openalex_id, "company": record.company} for record in records]
        authors: List[Row] = [
            {
                "openalex_id": record.openalex_id,
                "position": authorship.position,
                "author_id": authorship.author_id,
                "name": authorship.name,
                "orcid": authorship.orcid,
                "institutions": ",".join(authorship.institutions),
                "company_affiliated": authorship.company_affiliated,
            }
            for record in unique.values()
            for authorship in record.authorships
        ]
        table = self.papers
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.openalex_id],
                            set_={
                                "doi": excluded.doi,
                                "title": excluded.title,
                                "cited_by_count": excluded.cited_by_count,
                                "fwci": excluded.fwci,
                                "is_oa": excluded.is_oa,
                                "topic": excluded.topic,
                                "venue": excluded.venue,
                                "fetched_at": func.now(),
                            },
                        )
                    )
                for start in range(0, len(links), self.CHUNK):
                    linked = upsert(self.companies).values(links[start : start + self.CHUNK])
                    await connection.execute(
                        linked.on_conflict_do_update(
                            index_elements=[self.companies.c.openalex_id, self.companies.c.company],
                            set_={"linked_at": func.now()},
                        )
                    )
                await connection.execute(delete(self.authors).where(self.authors.c.openalex_id.in_(list(unique))))
                for start in range(0, len(authors), self.CHUNK):
                    await connection.execute(
                        upsert(self.authors).values(authors[start : start + self.CHUNK]).on_conflict_do_nothing()
                    )
        except SQLAlchemyError as e:
            self.logger.error("The research papers cannot be written: %s", e)
            raise StorageWriteError("research papers", str(e)) from e
        self.logger.info("%d research papers written (%d authorships).", len(rows), len(authors))
        return len(rows)

    async def upsert_researchers(self, records: Sequence[ResearcherRecord]) -> int:
        """Write researcher profiles, replacing those of the same author and company.

        Args:
            records (Sequence[ResearcherRecord]): The profiles.

        Returns:
            int: The number of profiles written.

        Raises:
            StorageWriteError: If the profiles cannot be written.
        """
        unique = {(record.author_id, record.company): record for record in records}
        rows: List[Row] = [
            {
                "author_id": record.author_id,
                "company": record.company,
                "name": record.name,
                "orcid": record.orcid,
                "works_count": record.works_count,
                "cited_by_count": record.cited_by_count,
                "h_index": record.h_index,
                "institution": record.institution,
                "current_affiliation": record.current_affiliation,
                "affiliation_years": record.affiliation_years,
                "source_url": record.source_url,
            }
            for record in unique.values()
        ]
        if not rows:
            return 0
        table = self.researchers
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    excluded = statement.excluded
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.author_id, table.c.company],
                            set_={
                                "name": excluded.name,
                                "orcid": excluded.orcid,
                                "works_count": excluded.works_count,
                                "cited_by_count": excluded.cited_by_count,
                                "h_index": excluded.h_index,
                                "institution": excluded.institution,
                                "current_affiliation": excluded.current_affiliation,
                                "affiliation_years": excluded.affiliation_years,
                                "source_url": excluded.source_url,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The researcher profiles cannot be written: %s", e)
            raise StorageWriteError("researcher profiles", str(e)) from e
        self.logger.info("%d researcher profiles written.", len(rows))
        return len(rows)

    async def yearly(self, companies: Optional[Sequence[str]] = None) -> Dict[YearKey, float]:
        """Sum the citations and average the impact of each company's papers per publication year.

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            Dict[YearKey, float]: The value of each papers indicator, by company, indicator and year.

        Raises:
            StorageReadError: If the papers cannot be read.
        """
        parameters = {"all_companies": not companies, "companies": list(companies or [])}
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(text(self.YEARLY), parameters)).all()
        except SQLAlchemyError as e:
            self.logger.error("The yearly papers figures cannot be read: %s", e)
            raise StorageReadError("research papers", str(e)) from e
        figures = {(str(row[0]), CompanyIndicator(str(row[1])), int(row[2])): float(row[3]) for row in rows}
        self.logger.debug("%d yearly papers figures read.", len(figures))
        return figures

    async def coverage(self, companies: Optional[Sequence[str]] = None) -> Dict[str, Tuple[int, int]]:
        """Count what is stored of each company's research (the explorer's Patents & Papers tab).

        Args:
            companies (Optional[Sequence[str]]): Only these companies, every one when `None` or empty.

        Returns:
            Dict[str, Tuple[int, int]]: The papers and the confirmed researcher profiles, by company.

        Raises:
            StorageReadError: If the papers cannot be read.
        """
        papers = select(self.companies.c.company, func.count()).group_by(self.companies.c.company)
        people = (
            select(self.researchers.c.company, func.count())
            .where(self.researchers.c.confirmed)
            .group_by(self.researchers.c.company)
        )
        if companies:
            papers = papers.where(self.companies.c.company.in_(list(companies)))
            people = people.where(self.researchers.c.company.in_(list(companies)))
        try:
            async with self.database.connect() as connection:
                paper_rows = (await connection.execute(papers)).all()
                people_rows = (await connection.execute(people)).all()
        except SQLAlchemyError as e:
            self.logger.error("The papers coverage cannot be read: %s", e)
            raise StorageReadError("research papers", str(e)) from e
        coverage: Dict[str, Tuple[int, int]] = {str(company): (int(count), 0) for company, count in paper_rows}
        for company, count in people_rows:
            coverage[str(company)] = (coverage.get(str(company), (0, 0))[0], int(count))
        self.logger.debug("Papers coverage read for %d companies.", len(coverage))
        return coverage

    async def list(self, query: RecordQuery) -> RecordPage[StoredPaper]:
        """List a page of the stored papers (the Stored data of the Patents & Papers tab).

        Args:
            query (RecordQuery): The companies, the text (in the title, the DOI or the venue), the order and the
                bounds of the page.

        Returns:
            RecordPage[StoredPaper]: The papers of the page (without their authors), the latest first by default.

        Raises:
            StorageReadError: If the papers cannot be read.
        """
        papers, links = self.papers, self.companies
        statement = self._paper_selection()
        if query.companies:
            owned = select(links.c.openalex_id).where(links.c.company.in_(query.companies))
            statement = statement.where(papers.c.openalex_id.in_(owned))
        sorts = {
            RecordSort.TITLE: papers.c.title,
            RecordSort.PUBLISHED: papers.c.publication_date,
            RecordSort.CITATIONS: papers.c.cited_by_count,
            RecordSort.VENUE: papers.c.venue,
        }
        searched = [papers.c.title, papers.c.doi, papers.c.venue]
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.PUBLISHED, [papers.c.openalex_id], searched
                )
        except SQLAlchemyError as e:
            self.logger.error("The stored papers cannot be read: %s", e)
            raise StorageReadError("research papers", str(e)) from e
        items = [StoredPaper.model_validate(dict(row)) for row in rows]
        self.logger.info("%d stored papers read from %d.", len(items), query.offset)
        return RecordPage[StoredPaper](items=items, offset=query.offset, limit=query.limit, total=total)

    async def read(self, openalex_id: str) -> Optional[StoredPaper]:
        """Read one stored paper with its authors.

        Args:
            openalex_id (str): The OpenAlex work.

        Returns:
            Optional[StoredPaper]: The paper, `None` when it is not stored.

        Raises:
            StorageReadError: If the paper cannot be read.
        """
        papers, authors = self.papers, self.authors
        try:
            async with self.database.connect() as connection:
                head = (
                    (await connection.execute(self._paper_selection().where(papers.c.openalex_id == openalex_id)))
                    .mappings()
                    .first()
                )
                if head is None:
                    self.logger.warning("The paper %s is not stored.", openalex_id)
                    return None
                rows = (
                    (
                        await connection.execute(
                            select(authors).where(authors.c.openalex_id == openalex_id).order_by(authors.c.position)
                        )
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError as e:
            self.logger.error("The paper %s cannot be read: %s", openalex_id, e)
            raise StorageReadError("research papers", str(e)) from e
        people = [
            PaperAuthorship(
                position=row["position"],
                author_id=row["author_id"],
                name=row["name"],
                orcid=row["orcid"],
                institutions=[part.strip() for part in (row["institutions"] or "").split(",") if part.strip()],
                company_affiliated=row["company_affiliated"],
            )
            for row in rows
        ]
        paper = StoredPaper.model_validate({**head, "authors": people})
        self.logger.debug("Paper %s read: %d authors.", openalex_id, len(people))
        return paper

    async def create(self, record: PaperRecord) -> StoredPaper:
        """Store a paper never stored, with its authors and its company link.

        Args:
            record (PaperRecord): The paper.

        Returns:
            StoredPaper: The paper, as stored.

        Raises:
            StorageWriteError: If the paper is already stored, or cannot be written.
        """
        if await self.read(record.openalex_id) is not None:
            self.logger.error("The paper %s is already stored: not created.", record.openalex_id)
            raise StorageWriteError("research papers", f"{record.openalex_id} already exists")
        await self.upsert_papers([record])
        created = await self.read(record.openalex_id)
        if created is None:
            self.logger.error("The paper %s was written but cannot be read back.", record.openalex_id)
            raise StorageWriteError("research papers", f"{record.openalex_id} was not stored")
        self.logger.info("Paper %s created.", record.openalex_id)
        return created

    async def update(self, record: PaperRecord) -> bool:
        """Replace a stored paper and its authors (its company link added when new).

        Args:
            record (PaperRecord): The paper.

        Returns:
            bool: Whether the paper was stored (none is created otherwise).

        Raises:
            StorageWriteError: If the paper cannot be written.
        """
        if await self.read(record.openalex_id) is None:
            self.logger.warning("The paper %s is not stored: nothing updated.", record.openalex_id)
            return False
        await self.upsert_papers([record])
        self.logger.info("Paper %s updated.", record.openalex_id)
        return True

    async def researcher_page(self, query: RecordQuery) -> RecordPage[StoredResearcher]:
        """Read a page of the researcher profiles.

        Args:
            query (RecordQuery): The companies, the text (in the name or the institution), the order and the bounds
                of the page.

        Returns:
            RecordPage[StoredResearcher]: The profiles of the page, the most cited first by default.

        Raises:
            StorageReadError: If the profiles cannot be read.
        """
        table = self.researchers
        statement = cast(Select[Tuple[RecordValue, ...]], select(table)).where(table.c.confirmed)
        if query.companies:
            statement = statement.where(table.c.company.in_(query.companies))
        sorts = {
            RecordSort.NAME: table.c.name,
            RecordSort.COMPANY: table.c.company,
            RecordSort.WORKS: table.c.works_count,
            RecordSort.CITATIONS: table.c.cited_by_count,
            RecordSort.H_INDEX: table.c.h_index,
        }
        keys = [table.c.author_id, table.c.company]
        searched = [table.c.name, table.c.institution]
        try:
            async with self.database.connect() as connection:
                rows, total = await self.pager.read(
                    connection, statement, query, sorts, RecordSort.CITATIONS, keys, searched
                )
        except SQLAlchemyError as e:
            self.logger.error("The researcher profiles cannot be read: %s", e)
            raise StorageReadError("researcher profiles", str(e)) from e
        items = [StoredResearcher.model_validate(dict(row)) for row in rows]
        self.logger.info("%d researcher profiles read from %d.", len(items), query.offset)
        return RecordPage[StoredResearcher](items=items, offset=query.offset, limit=query.limit, total=total)

    async def confirm_researchers(self, companies: Sequence[str], years: int, papers: int) -> int:
        """Confirm the researchers who are members of their company, the others being kept out of sight.

        Args:
            companies (Sequence[str]): The companies whose researchers are confirmed.
            years (int): The profile years at the company confirming a member last seen elsewhere.
            papers (int): The stored papers signed with the company confirming such a member.

        Returns:
            int: The researchers confirmed.

        Raises:
            StorageWriteError: If the researchers cannot be updated.

        Notes:
            A researcher is confirmed when the company is their last known institution, or their profile lists it
            for `years` years, or they signed `papers` stored papers with it. The others are mostly affiliations
            OpenAlex copied onto every author of a paper.
        """
        if not companies:
            return 0
        parameters = {"companies": list(companies), "years": years, "papers": papers}
        table = self.researchers
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(text(self.CONFIRM_BY_PROFILE), parameters)
                await connection.execute(text(self.CONFIRM_BY_PAPERS), parameters)
                counted = (
                    await connection.execute(
                        select(func.count().filter(table.c.confirmed), func.count()).where(
                            table.c.company.in_(list(companies))
                        )
                    )
                ).one()
        except SQLAlchemyError as e:
            self.logger.error("The researchers cannot be confirmed: %s", e)
            raise StorageWriteError("researcher profiles", str(e)) from e
        confirmed, total = int(counted[0]), int(counted[1])
        if total > confirmed:
            self.logger.warning(
                "%d of %d researchers of %s not confirmed as members (kept out of sight).",
                total - confirmed,
                total,
                ", ".join(companies),
            )
        self.logger.info("%d researchers of %d companies confirmed.", confirmed, len(companies))
        return confirmed

    async def sweep(self, companies: Sequence[str], since: datetime, max_share: float = 0.5) -> Tuple[int, int]:
        """Remove what a complete papers search of the companies no longer found: their stale links and profiles.

        Args:
            companies (Sequence[str]): The companies searched in full.
            since (datetime): When the search started: what it wrote is newer.
            max_share (float): The largest share of a company's links removed at once (a larger one means the search
                was not complete, the company is then left as it is).

        Returns:
            Tuple[int, int]: The links, then the researcher profiles removed.

        Raises:
            StorageWriteError: If the stale rows cannot be removed.

        Notes:
            A paper left without any company is removed with its authors. A link becomes stale when the search
            leaves the paper out (none of its authors is a member of the company, see `exclude_affiliations`).
        """
        if not companies:
            return 0, 0
        links, researchers = self.companies, self.researchers
        parameters = {"companies": list(companies), "since": since}
        removed_links = removed_people = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                shares = (await connection.execute(text(self.STALE_SHARES), parameters)).all()
                swept: List[str] = []
                for company, stale, total in shares:
                    if stale and stale > max_share * total:
                        self.logger.warning(
                            "%s: the search did not find %d of its %d papers again, nothing removed (incomplete?).",
                            company,
                            stale,
                            total,
                        )
                        continue
                    swept.append(str(company))
                if swept:
                    removed_links = (
                        await connection.execute(
                            delete(links).where(links.c.company.in_(swept), links.c.linked_at < since)
                        )
                    ).rowcount
                    removed_people = (
                        await connection.execute(
                            delete(researchers).where(
                                researchers.c.company.in_(swept), researchers.c.fetched_at < since
                            )
                        )
                    ).rowcount
                    await self._drop_orphans(connection)
        except SQLAlchemyError as e:
            self.logger.error("The stale papers links cannot be removed: %s", e)
            raise StorageWriteError("research papers", str(e)) from e
        self.logger.info(
            "Papers sweep of %d companies: %d stale links and %d stale researcher profiles removed.",
            len(companies),
            removed_links,
            removed_people,
        )
        return removed_links, removed_people

    async def unlink(self, rejected: Dict[str, Set[str]]) -> int:
        """Remove the links of the papers a search rejected as not the company's (none of their authors is a member).

        Args:
            rejected (Dict[str, Set[str]]): The papers rejected, by company.

        Returns:
            int: The links removed.

        Raises:
            StorageWriteError: If the links cannot be removed.

        Notes:
            A paper left without any company is removed with its authors.
        """
        total = sum(len(papers) for papers in rejected.values())
        if not total:
            return 0
        links = self.companies
        removed = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                for company, papers in rejected.items():
                    ids = sorted(papers)
                    for start in range(0, len(ids), self.CHUNK):
                        chunk = ids[start : start + self.CHUNK]
                        statement = delete(links).where(links.c.company == company, links.c.openalex_id.in_(chunk))
                        removed += (await connection.execute(statement)).rowcount
                await self._drop_orphans(connection)
        except SQLAlchemyError as e:
            self.logger.error("The rejected papers links cannot be removed: %s", e)
            raise StorageWriteError("research papers", str(e)) from e
        self.logger.info("%d links of %d rejected papers removed.", removed, total)
        return removed
