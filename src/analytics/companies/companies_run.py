from __future__ import annotations

# Standard Library Imports.
import os
import threading
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# First Party Imports.
from analytics.companies.companies_collector import CompaniesCollector
from analytics.companies.identities.assignee_refiner import AssigneeRefiner
from crawler.companies.catalog_loader import CompaniesCatalogLoader
from crawler.runner import CatalogueRunner, CompanyObserver
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.enums import CompanyFeed
from models.companies.patents.patent_window import PatentWindow
from models.markets.crawl_scope import CrawlScope


class CompaniesRun:
    """Run a companies crawl: each source in turn, its facts written as they come, then the indicator series derived.

    Attributes:
        LOCAL_FEEDS (ClassVar[Tuple[CompanyFeed, ...]]): The sources read from the database, without network (the
            figures researched by hand, the assignees of the stored patents).
        ON_DEMAND_FEEDS (ClassVar[Tuple[CompanyFeed, ...]]): The identity resolvers, which propose identifiers of
            the companies, and the figures check, which checks the researched figures against their documents:
            run only when asked for.
        runner (CatalogueRunner): The runner streaming the crawls (its storage is open).
        logger (Logger): The run logger.
        refusals (Dict[CompanyFeed, str]): Why a source refused the last run before its end, by source.
        rejected (Dict[str, Set[str]]): The papers the last run rejected as not the company's, by company.

    Notes:
        - The patents search resumes from the windows stored by the former runs, the patent pages read the next
          publications waiting (`CRAWLER_PATENT_PAGES` of them, else the catalogue's budget).
        - The command line (`CRAWLER_SOURCE=companies`) and the explorer's Companies menu both run this.
        - After the papers search, the papers it rejected (no author signed as a member of the company) lose their
          link to the company, the researchers are confirmed as members of their company (see `OpenAlexSettings`),
          and when the search was neither stopped, refused nor capped (`max_works`), the papers and profiles of its
          companies it no longer found are removed (`PaperRepository.sweep`).
    """

    LOCAL_FEEDS: ClassVar[Tuple[CompanyFeed, ...]] = (CompanyFeed.REPORTED, CompanyFeed.ASSIGNEE_IDENTITY)
    ON_DEMAND_FEEDS: ClassVar[Tuple[CompanyFeed, ...]] = (
        CompanyFeed.SEC_IDENTITY,
        CompanyFeed.OPENALEX_IDENTITY,
        CompanyFeed.ASSIGNEE_IDENTITY,
        CompanyFeed.FIGURE_CHECK,
    )

    def __init__(self, runner: CatalogueRunner, logger: Optional[Logger] = None) -> None:
        """Initialize the run.

        Args:
            runner (CatalogueRunner): The runner streaming the crawls (its storage is open).
            logger (Optional[Logger]): The run logger.
        """
        self.runner = runner
        self.logger = logger if logger else getLogger(__name__)
        self.refusals: Dict[CompanyFeed, str] = {}
        self.rejected: Dict[str, Set[str]] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    async def _settle_papers(
        self, companies: CompaniesCatalog, scope: CrawlScope, started: datetime, complete: bool
    ) -> None:
        """Remove the papers the search rejected, confirm the researchers, and remove what a complete search missed.

        Args:
            companies (CompaniesCatalog): The catalogue, with the OpenAlex settings.
            scope (CrawlScope): The companies searched, every one when empty.
            started (datetime): When the search started.
            complete (bool): Whether the search ended by itself (neither stopped nor refused): only then are the
                papers it did not find again removed.

        Raises:
            StorageError: If the papers cannot be updated.
        """
        settings = companies.openalex
        searched = [entry.key for entry in companies.entries(scope.companies) if entry.openalex.institutions]
        storage = self.runner.storage
        await storage.papers.unlink(self.rejected)
        await storage.papers.confirm_researchers(searched, settings.min_affiliation_years, settings.min_company_papers)
        if not complete or settings.max_works:
            self.logger.warning("The papers search was stopped, refused or capped: the papers it missed are kept.")
            return
        await storage.papers.sweep(searched, started)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def run(
        self,
        feeds: Sequence[CompanyFeed],
        scope: CrawlScope,
        observer: Optional[CompanyObserver] = None,
        batch_size: Optional[int] = None,
        stop: Optional[threading.Event] = None,
    ) -> int:
        """Crawl the sources, write their facts and derive the indicators of the companies read.

        Args:
            feeds (Sequence[CompanyFeed]): The sources, in the order they run.
            scope (CrawlScope): The companies read, every one when empty.
            observer (Optional[CompanyObserver]): Called after each batch is written (the explorer's progress).
            batch_size (Optional[int]): The facts written at once, the runner's default when `None`.
            stop (Optional[threading.Event]): Once set, the source running ends gracefully and the next ones are
                skipped. The indicators of what was read are still derived.

        Returns:
            int: The rows written.

        Raises:
            CompaniesCatalogError: If the statement mapping cannot be loaded.
            CuratedCatalogError: If the curated catalogues stored are invalid.
            CompaniesCollectorError: If the researched figures stored hold no company.
            StorageError: If the storage cannot be read or written, or the curated catalogues were never seeded.
        """
        storage = self.runner.storage
        companies, concepts = await storage.catalogs.companies(), CompaniesCatalogLoader().concepts()
        markets, chronology = await storage.catalogs.markets(), await storage.catalogs.chronology()
        collector = CompaniesCollector(companies, concepts, markets, storage, scope.companies)
        written = 0
        self.refusals = {}
        self.rejected = {}
        for feed in feeds:
            if stop is not None and stop.is_set():
                self.logger.warning("Stop requested: the companies source %s is skipped.", feed.value)
                continue
            if feed is CompanyFeed.REPORTED:
                written += await collector.write_reported(await storage.catalogs.figures())
                continue
            if feed is CompanyFeed.ASSIGNEE_IDENTITY:
                homonyms = await AssigneeRefiner(self.logger).candidates(storage, companies, scope.companies)
                written += await collector.identities.write(homonyms)
                continue
            known: Optional[List[PatentWindow]] = None
            queue: Optional[List[str]] = None
            if feed is CompanyFeed.GOOGLE_PATENTS:
                known = await storage.patents.read_windows(scope.companies)
            if feed is CompanyFeed.GOOGLE_PATENT_PAGES:
                raw = os.getenv(companies.patents.page_budget_env, "").strip()
                budget = int(raw) if raw.isdigit() else companies.patents.page_budget
                queue = await storage.patents.queue(scope.companies, limit=budget)
            started = datetime.now(UTC)
            written += await self.runner.stream_companies(
                feed,
                collector.write,
                companies,
                concepts,
                markets,
                scope,
                known=known,
                queue=queue,
                batch_size=batch_size,
                observer=observer,
                stop=stop,
                refusals=self.refusals,
                rejected=self.rejected,
                chronology=chronology,
                figures=await storage.catalogs.figures() if feed is CompanyFeed.FIGURE_CHECK else None,
            )
            if feed is CompanyFeed.OPENALEX:
                complete = not (stop is not None and stop.is_set()) and feed not in self.refusals
                await self._settle_papers(companies, scope, started, complete)
        written += await collector.finish(feeds)
        if not written:
            self.logger.warning("The companies crawl wrote no row.")
        self.logger.info("%d companies rows written from %s.", written, ", ".join(feed.value for feed in feeds))
        return written
