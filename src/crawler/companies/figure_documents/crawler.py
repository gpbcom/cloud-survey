from __future__ import annotations

# Standard Library Imports.
import html
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Pattern, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.enums import CompanyMeta
from models.companies.checks.document_numbers import DocumentNumbers
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.companies.figures.reported_figures import ReportedFigures
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog


class FigureDocumentsCrawler(BaseCompanyCrawler):
    """Read the documents the researched fiscal years cite, and stream the numbers each one states.

    Attributes:
        HOSTS (ClassVar[FrozenSet[str]]): The hosts read: SEC EDGAR's archives, the Wayback Machine and the
            Internet Archive (their robots allow it).
        SEC_HOST (ClassVar[str]): The host asking for a contact in the user agent.
        SKIPPED (ClassVar[Tuple[str, ...]]): The document types not read (no text to read numbers from).
        ITEM_PAGE (ClassVar[str]): The path of an Internet Archive item page (its documents are files of the item).
        NUMBER (ClassVar[Pattern[str]]): A number as a document writes it: thousands separators, decimals, an
            amount in parentheses (a negative one).
        MARKUP (ClassVar[Pattern[str]]): The markup and scripts of an HTML document.
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): The figures check.
        catalogue_url (ClassVar[str]): The SEC host.
        download_delay (float): Half a second between two documents.
        figures (ReportedFigures): The researched fiscal years and the documents they cite.

    Notes:
        - A document cited by several fiscal years of a company (a ten-year summary) is read once.
        - The numbers are streamed as written: `FigureChecker` finds each researched figure among them, whatever
          the scale of the document, and marks the fiscal years. A document that cannot be read streams no number.
        - The PDF and spreadsheet documents, the item pages of the Internet Archive and the other hosts are not
          read: their fiscal years stay unchecked.
        - SEC EDGAR asks for a user agent naming a contact, read from the environment variable of the catalogue.
    """

    HOSTS: ClassVar[FrozenSet[str]] = frozenset({"www.sec.gov", "web.archive.org", "archive.org"})
    SEC_HOST: ClassVar[str] = "www.sec.gov"
    SKIPPED: ClassVar[Tuple[str, ...]] = (".pdf", ".xls", ".xlsx", ".zip", ".gif", ".jpg", ".png")
    ITEM_PAGE: ClassVar[str] = "/details/"
    NUMBER: ClassVar[Pattern[str]] = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\w])")
    MARKUP: ClassVar[Pattern[str]] = re.compile(r"(?is)<(script|style)\b.*?</\1>|<[^>]+>")

    name = "figure-documents"
    feed: ClassVar[CompanyFeed] = CompanyFeed.FIGURE_CHECK
    catalogue_url: ClassVar[str] = "https://www.sec.gov/"
    download_delay: float = 0.5

    def __init__(
        self,
        companies: Optional[CompaniesCatalog] = None,
        concepts: Optional[FinancialConcepts] = None,
        markets: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        figures: Optional[ReportedFigures] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            companies (Optional[CompaniesCatalog]): The companies (the SEC contact variable),
                `data/curated/companies.json` by default.
            concepts (Optional[FinancialConcepts]): How the statement lines are read (unused here), by default the
                `concepts` block of `conf/settings.yaml`.
            markets (Optional[MarketsCatalog]): The listings (unused here), `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The companies checked, every one by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            figures (Optional[ReportedFigures]): The researched figures, `data/curated/figures.json` by default.

        Raises:
            CompaniesCatalogError: If a default catalogue cannot be loaded.
            MarketsCatalogError: If the default markets catalogue cannot be loaded.
        """
        super().__init__(
            companies=companies, concepts=concepts, markets=markets, scope=scope, crawldir=crawldir, interval=interval
        )
        self.figures = figures if figures else self._bundled_figures()

    ############################
    # Internal Helpers Methods #
    ############################

    def _readable(self, url: str) -> bool:
        """Tell whether a cited document is read.

        Args:
            url (str): The document.

        Returns:
            bool: Whether it is on a host read, and neither a PDF, a spreadsheet nor an item page.
        """
        parsed = urlparse(url)
        path = parsed.path.casefold()
        return (
            parsed.scheme == "https"
            and parsed.netloc in self.HOSTS
            and not path.endswith(self.SKIPPED)
            and not (parsed.netloc == "archive.org" and path.startswith(self.ITEM_PAGE))
        )

    def _documents(self) -> Dict[Tuple[str, str], List[int]]:
        """Group the readable documents cited by the fiscal years of the companies checked.

        Returns:
            Dict[Tuple[str, str], List[int]]: The fiscal years citing each document, by company and document.
        """
        documents: Dict[Tuple[str, str], List[int]] = {}
        skipped = 0
        keys = self.scope.companies or [entry.company for entry in self.figures.companies]
        for key in keys:
            entry = self.figures.of(key)
            for year in entry.years if entry is not None else []:
                if self._readable(year.source):
                    documents.setdefault((key, year.source), []).append(year.fiscal_year)
                else:
                    skipped += 1
        if skipped:
            self.logger.info(
                "%d researched fiscal years cite a document not read (PDF, other host): unchecked.", skipped
            )
        return documents

    def _numbers(self, response: Response) -> List[float]:
        """Read the numbers a document states.

        Args:
            response (Response): The document.

        Returns:
            List[float]: The distinct numbers, without sign, at most `DocumentNumbers.MAX_NUMBERS` of them.
        """
        text = self._body_text(response)
        if "<" in text and ">" in text:
            text = html.unescape(self.MARKUP.sub(" ", text))
        numbers = {
            float(match.group(1).replace(",", "") + (match.group(2) or "")) for match in self.NUMBER.finditer(text)
        }
        if len(numbers) > DocumentNumbers.MAX_NUMBERS:
            self.logger.warning(
                "%s states %d numbers: the first %d kept.", response.url, len(numbers), DocumentNumbers.MAX_NUMBERS
            )
        return sorted(numbers)[: DocumentNumbers.MAX_NUMBERS]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request every readable document cited by the fiscal years of the companies checked, once each.

        Yields:
            Request: A request per company and document.
        """
        documents = self._documents()
        contact = self._secret(self.companies.sec_user_agent_env)
        self.logger.info("Reading %d documents cited by the researched figures.", len(documents))
        for (company, url), years in documents.items():
            headers = self._headers("text/html,text/plain,*/*")
            if urlparse(url).netloc == self.SEC_HOST:
                if contact is None:
                    self.logger.warning(
                        "%s is not set: SEC EDGAR may refuse %s.", self.companies.sec_user_agent_env, url
                    )
                headers["User-Agent"] = contact or self.USER_AGENT
            meta: Dict[str, JsonValue] = {
                CompanyMeta.FISCAL_YEARS.value: [*years],
                CompanyMeta.SOURCE.value: url,
            }
            yield self._company_request(url, headers, company, meta)

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether a host refused a request: a document gone (HTTP 404, 410) is not a refusal.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether the response is a refusal, retried by the engine.
        """
        if response.status in (404, 410):
            self.logger.warning("The cited document %s is gone (HTTP %s).", response.url, response.status)
            return False
        return await super().is_blocked(response)

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the numbers a cited document states (none when it could not be read).

        Args:
            response (Response): The document.

        Returns:
            Iterator[CompanyFact]: The numbers of the document, for the fiscal years citing it.
        """
        years = response.meta.get(CompanyMeta.FISCAL_YEARS)
        source = response.meta.get(CompanyMeta.SOURCE)
        numbers = self._numbers(response) if response.status == 200 else []
        try:
            fact = DocumentNumbers(
                company=self._company(response),
                fiscal_years=years if isinstance(years, list) else [],
                source_url=source if isinstance(source, str) else response.url,
                numbers=[*numbers],
            )
        except ValidationError as e:
            self.logger.error("The numbers of %s cannot be streamed: %s", response.url, e.errors()[0]["msg"])
            return
        self.logger.info(
            "%s states %d numbers (fiscal years %s of %s).",
            fact.source_url,
            len(numbers),
            fact.fiscal_years,
            fact.company,
        )
        yield fact
