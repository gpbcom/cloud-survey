from __future__ import annotations

# Standard Library Imports.
import os
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, Optional, Set, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.companies.catalog_loader import CompaniesCatalogLoader
from crawler.companies.enums import CompanyMeta
from crawler.enums import TextEncoding
from crawler.exception import CompaniesCatalogError, MarketsCatalogError, ParseNotImplementedError
from crawler.tls.ca_bundle import CaBundle
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from models.companies.checks.document_numbers import DocumentNumbers
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFactKind, CompanyFeed
from models.companies.facts.financial_fact import FinancialFact
from models.companies.figures.reported_figures import ReportedFigures
from models.companies.identities.identity_candidate import IdentityCandidate
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.history.chronology import Chronology
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

type CompanyFact = Union[
    FinancialFact,
    PatentRecord,
    PatentDetail,
    PatentWindow,
    PaperRecord,
    ResearcherRecord,
    PaperYearCount,
    IdentityCandidate,
    DocumentNumbers,
]


class BaseCompanyCrawler(BaseCloudCrawler):
    """Base class for the crawlers of the companies' financial statements, patents and research papers.

    Attributes:
        USER_AGENT (ClassVar[str]): The user agent of the requests (the impersonated browser's is replaced).
        KIND_KEY (ClassVar[str]): The item key naming the kind of fact streamed.
        KINDS (ClassVar[Dict[type, CompanyFactKind]]): The kind of each fact model.
        feed (ClassVar[CompanyFeed]): The source crawled.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it (never here).
        companies (CompaniesCatalog): Where each company is found.
        concepts (FinancialConcepts): How the statement lines are read.
        markets (MarketsCatalog): The listings of the companies (and the Google Finance consent cookies).
        scope (CrawlScope): The companies read, every one by default.
        facts (int): The facts streamed so far.
        refusal (Optional[str]): Why the source refused the crawl before its end (its remaining work is left for a
            later run), `None` when it did not.
        rejected (Dict[str, Set[str]]): The records the source lists for a company but the crawl rejected as not
            the company's, by company (their stored links to it are removed).

    Notes:
        - A crawler only crawls: it streams the facts as the source states them, each item carrying its kind
          (`kind`), and `analytics.companies` maps, derives and stores them.
        - The sources are read through an HTTP session (`<name>-http`), the default one, one request at a time with
          the delay of the source.
    """

    USER_AGENT: ClassVar[str] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
    KIND_KEY: ClassVar[str] = "kind"
    KINDS: ClassVar[Dict[type, CompanyFactKind]] = {
        FinancialFact: CompanyFactKind.FINANCIAL,
        PatentRecord: CompanyFactKind.PATENT,
        PatentDetail: CompanyFactKind.PATENT_DETAIL,
        PatentWindow: CompanyFactKind.PATENT_WINDOW,
        PaperRecord: CompanyFactKind.PAPER,
        ResearcherRecord: CompanyFactKind.RESEARCHER,
        PaperYearCount: CompanyFactKind.PAPER_COUNT,
        IdentityCandidate: CompanyFactKind.IDENTITY,
        DocumentNumbers: CompanyFactKind.DOCUMENT_NUMBERS,
    }
    feed: ClassVar[CompanyFeed] = CompanyFeed.EDGAR
    lazy_browser: ClassVar[bool] = True

    def __init__(
        self,
        companies: Optional[CompaniesCatalog] = None,
        concepts: Optional[FinancialConcepts] = None,
        markets: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            companies (Optional[CompaniesCatalog]): Where each company is found, the curated bundle's by default.
            concepts (Optional[FinancialConcepts]): How the statement lines are read,
                the `concepts` block of `conf/settings.yaml` by default.
            markets (Optional[MarketsCatalog]): The listings, those of the curated bundle by default.
            scope (Optional[CrawlScope]): The companies read, every one by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            CompaniesCatalogError: If a default catalogue cannot be loaded.
            MarketsCatalogError: If the default markets catalogue cannot be loaded.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.companies = companies if companies else self._bundled_companies()
        self.concepts = concepts if concepts else CompaniesCatalogLoader(self.logger).concepts()
        self.markets = markets if markets else self._bundled_markets()
        self.scope = scope if scope else CrawlScope()
        self.facts = 0
        self.refusal: Optional[str] = None
        self.rejected: Dict[str, Set[str]] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _bundled_companies(self) -> CompaniesCatalog:
        """Read the companies catalogue of the curated bundle, the default of a crawler.

        Returns:
            CompaniesCatalog: The companies catalogue.

        Raises:
            CompaniesCatalogError: If the bundle cannot be read or is invalid.
        """
        try:
            return BundleCatalogs(logger=self.logger).companies()
        except CuratedError as e:
            self.logger.error("The companies catalogue of the bundle cannot be read: %s", e)
            raise CompaniesCatalogError("data/curated/companies.json", str(e)) from e

    def _bundled_markets(self) -> MarketsCatalog:
        """Read the markets catalogue of the curated bundle (the listings), the default of a crawler.

        Returns:
            MarketsCatalog: The markets catalogue.

        Raises:
            MarketsCatalogError: If the bundle cannot be read or is invalid.
        """
        try:
            return BundleCatalogs(logger=self.logger).markets()
        except CuratedError as e:
            self.logger.error("The markets catalogue of the bundle cannot be read: %s", e)
            raise MarketsCatalogError("data/curated/markets.json", str(e)) from e

    def _bundled_chronology(self) -> Chronology:
        """Read the chronology of the curated bundle (the names of the companies), the default of the crawler.

        Returns:
            Chronology: The chronology.

        Raises:
            CompaniesCatalogError: If the bundle cannot be read or is invalid.
        """
        try:
            return BundleCatalogs(logger=self.logger).chronology()
        except CuratedError as e:
            self.logger.error("The chronology of the bundle cannot be read: %s", e)
            raise CompaniesCatalogError("data/curated/chronology.json", str(e)) from e

    def _bundled_figures(self) -> ReportedFigures:
        """Read the researched figures of the curated bundle (their cited documents), the default of the crawler.

        Returns:
            ReportedFigures: The researched figures.

        Raises:
            CompaniesCatalogError: If the bundle cannot be read or is invalid.
        """
        try:
            return BundleCatalogs(logger=self.logger).figures()
        except CuratedError as e:
            self.logger.error("The researched figures of the bundle cannot be read: %s", e)
            raise CompaniesCatalogError("data/curated/figures.json", str(e)) from e

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, e.g. `edgar-financials-http`.
        """
        return f"{self.name}-http"

    def _secret(self, variable: str) -> Optional[str]:
        """Read a secret from its environment variable (the catalogue only names the variable).

        Args:
            variable (str): The environment variable.

        Returns:
            Optional[str]: The secret, `None` when the variable is unset or blank.
        """
        value = (os.getenv(variable) or "").strip()
        if not value:
            self.logger.debug("The environment variable %s is not set.", variable)
        return value or None

    def _headers(self, accept: str) -> Dict[str, str]:
        """Build the headers of a request: the user agent, and the media type asked for.

        Args:
            accept (str): The media type asked for.

        Returns:
            Dict[str, str]: The headers.
        """
        return {"User-Agent": self.USER_AGENT, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}

    def _company_request(
        self, url: str, headers: Dict[str, str], company: str, meta: Optional[Dict[str, JsonValue]] = None
    ) -> Request:
        """Build a GET request of the HTTP session for a company.

        Args:
            url (str): The requested URL.
            headers (Dict[str, str]): The request headers.
            company (str): The company the document is read for.
            meta (Optional[Dict[str, JsonValue]]): The other request meta, given back with the response.

        Returns:
            Request: The request.
        """
        return Request(
            url,
            sid=self._http_session_id(),
            priority=self.PRIMARY_PRIORITY,
            meta={CompanyMeta.COMPANY.value: company, **(meta or {})},
            headers=headers,
            dont_filter=True,
        )

    def _company(self, response: Response) -> str:
        """Get the company a document was read for.

        Args:
            response (Response): The document.

        Returns:
            str: The company key, empty when the request named none.
        """
        company = response.meta.get(CompanyMeta.COMPANY)
        return company if isinstance(company, str) else ""

    def _body_text(self, response: Response) -> str:
        """Read the raw body of a response as text.

        Args:
            response (Response): The response.

        Returns:
            str: The body, decoded as UTF-8 (undecodable bytes replaced).
        """
        return response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)

    def _item(self, fact: CompanyFact) -> Dict[str, JsonValue]:
        """Write a fact as a streamed item, with its kind.

        Args:
            fact (CompanyFact): The fact.

        Returns:
            Dict[str, JsonValue]: The item: the fact's fields, and its kind under `kind`.
        """
        return {self.KIND_KEY: self.KINDS[type(fact)].value, **fact.model_dump(mode="json")}

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the HTTP session, the default one, and the stealth browser session, never started.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.
        """
        super().configure_sessions(manager)
        self.logger.debug("Configuring the HTTP session %s.", self._http_session_id())
        CaBundle(logger=self.logger).install()
        manager.add(
            self._http_session_id(),
            FetcherSession(
                impersonate="chrome",
                stealthy_headers=True,
                timeout=90,
                retries=self.fetch_retries,
                retry_delay=round(self.retry_delay),
            ),
            default=True,
        )

    async def on_start(self, resuming: bool = False) -> None:
        """Count the facts from zero, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.facts = 0

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        self.logger.info("The %s companies crawl is over: %d facts.", self.name, self.facts)

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the facts of a document.

        Args:
            response (Response): The document.

        Returns:
            Iterator[CompanyFact]: The valid facts of the document.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the fact extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Get the requests a document leads to, e.g. the next page of a listing or the halves of a window.

        Args:
            response (Response): The document.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: The requests, none by default.
        """
        self.logger.debug("No follow-up for the %s document %s (%d facts).", self.name, response.url, found)
        return iter(())

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the facts of a document, then its follow-up requests.

        Args:
            response (Response): The document.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each fact, as an item naming its kind, then each follow-up request.
        """
        self.logger.debug("Parsing the %s document %s (HTTP %s).", self.name, response.url, response.status)
        found = 0
        for fact in self.extract_facts(response):
            found += 1
            yield self._item(fact)
        self.facts += found
        for request in self.follow_ups(response, found):
            yield request
        self.logger.info("%s document %s parsed: %d facts.", self.name, response.url, found)
