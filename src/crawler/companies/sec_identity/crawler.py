from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.enums import CompanyMeta
from crawler.companies.sec_identity.enums import SecIdentityField, SecIdentityStep
from curated.company_names import CompanyNames
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.companies.identities.identity_candidate import IdentityCandidate
from models.curated.enums import IdentifierKind
from models.history.chronology import Chronology
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog


class SecIdentityCrawler(BaseCompanyCrawler):
    """Find the SEC filers of the companies: the listed filers whose ticker or name is the company's.

    Attributes:
        TICKERS_URL (ClassVar[str]): The listed filers, with their ticker and exchange.
        SUBMISSIONS_URL (ClassVar[str]): The submissions of a filer, formatted with its 10 digits.
        EVIDENCE_URL (ClassVar[str]): The page of a filer on EDGAR, the evidence shown in the Catalogues manager.
        US_EXCHANGES (ClassVar[FrozenSet[str]]): The exchanges of a listing whose ticker is a SEC ticker.
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): The SEC identity resolver.
        catalogue_url (ClassVar[str]): The SEC host.
        download_delay (float): A quarter of a second between two requests (SEC allows ten a second).
        names (CompanyNames): Compares the names.
        labels (Dict[str, str]): The name of each company, from the chronology.

    Notes:
        - The tickers file lists the filers listed today: a filer whose ticker is a US listing of the company (an
          ordinary share or a depositary one), or whose name is the company's, is a candidate.
        - Each candidate's submissions are read: a filer stating the listed ticker the catalogue gives the company
          is verified (confirmed at once), a filer matched on its name only waits for a person to accept it.
        - The filers already in the catalogue, in any status, are left out. The former filers (delisted, merged)
          are not in the tickers file: they stay researched by hand.
        - SEC EDGAR asks for a user agent naming a contact, read from the environment variable of the catalogue.
    """

    TICKERS_URL: ClassVar[str] = "https://www.sec.gov/files/company_tickers_exchange.json"
    SUBMISSIONS_URL: ClassVar[str] = "https://data.sec.gov/submissions/CIK{cik}.json"
    EVIDENCE_URL: ClassVar[str] = "https://www.sec.gov/edgar/browse/?CIK={cik}"
    US_EXCHANGES: ClassVar[FrozenSet[str]] = frozenset(
        {"NASDAQ", "NYSE", "NYSEAMERICAN", "NYSEARCA", "NYSEMKT", "AMEX", "OTCMKTS", "BATS"}
    )

    name = "sec-identity"
    feed: ClassVar[CompanyFeed] = CompanyFeed.SEC_IDENTITY
    catalogue_url: ClassVar[str] = "https://www.sec.gov/"
    download_delay: float = 0.25

    def __init__(
        self,
        companies: Optional[CompaniesCatalog] = None,
        concepts: Optional[FinancialConcepts] = None,
        markets: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        chronology: Optional[Chronology] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            companies (Optional[CompaniesCatalog]): The companies and their filers, `data/curated/companies.json` by
                default.
            concepts (Optional[FinancialConcepts]): How the statement lines are read (unused here), by default the
                `concepts` block of `conf/settings.yaml`.
            markets (Optional[MarketsCatalog]): The listings, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The companies resolved, every one by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            chronology (Optional[Chronology]): The names of the companies, `data/curated/chronology.json` by
                default.

        Raises:
            CompaniesCatalogError: If a default catalogue cannot be loaded.
            MarketsCatalogError: If the default markets catalogue cannot be loaded.
        """
        super().__init__(
            companies=companies, concepts=concepts, markets=markets, scope=scope, crawldir=crawldir, interval=interval
        )
        self.names = CompanyNames(self.logger)
        named = chronology if chronology else self._bundled_chronology()
        self.labels: Dict[str, str] = {company.key: company.label for company in named.companies}

    ############################
    # Internal Helpers Methods #
    ############################

    def _sec_headers(self) -> Dict[str, str]:
        """Build the headers of a SEC request: the contact the SEC asks for.

        Returns:
            Dict[str, str]: The headers.
        """
        headers = self._headers("application/json")
        agent = self._secret(self.companies.sec_user_agent_env)
        if agent is None:
            self.logger.warning(
                "%s is not set: SEC EDGAR may refuse the requests (it asks for a contact).",
                self.companies.sec_user_agent_env,
            )
        headers["User-Agent"] = agent or self.USER_AGENT
        return headers

    def _step(self, response: Response) -> str:
        """Get what a response reads.

        Args:
            response (Response): The response.

        Returns:
            str: The step of its request, empty when it names none.
        """
        step = response.meta.get(CompanyMeta.STEP)
        return step if isinstance(step, str) else ""

    def _meta_text(self, response: Response, key: CompanyMeta) -> str:
        """Read a text of the request meta.

        Args:
            response (Response): The response.
            key (CompanyMeta): The meta key.

        Returns:
            str: The text, empty when missing.
        """
        value = response.meta.get(key)
        return value if isinstance(value, str) else ""

    def _rows(self, document: JsonValue) -> List[Tuple[str, str, str, str]]:
        """Read the rows of the tickers file.

        Args:
            document (JsonValue): The tickers file.

        Returns:
            List[Tuple[str, str, str, str]]: The filer (10 digits), its name, its ticker and its exchange, by row.
        """
        content = self._as_object(document)
        fields = content.get(SecIdentityField.FIELDS)
        data = content.get(SecIdentityField.DATA)
        if not isinstance(fields, list) or not isinstance(data, list):
            self.logger.warning("The SEC tickers file has no fields or data: no filer is read.")
            return []
        columns = {str(field): index for index, field in enumerate(fields)}
        wanted = [SecIdentityField.CIK, SecIdentityField.NAME, SecIdentityField.TICKER, SecIdentityField.EXCHANGE]
        if any(field.value not in columns for field in wanted):
            self.logger.warning("The SEC tickers file misses a column of %s.", [field.value for field in wanted])
            return []
        rows: List[Tuple[str, str, str, str]] = []
        for row in data:
            if not isinstance(row, list) or len(row) < len(columns):
                continue
            cik, name, ticker, exchange = (row[columns[field.value]] for field in wanted)
            if isinstance(cik, int) and isinstance(name, str) and isinstance(ticker, str):
                rows.append((f"{cik:010d}", name, ticker.upper(), str(exchange or "").upper()))
        self.logger.info("SEC tickers file read: %d listed filers.", len(rows))
        return rows

    def _tickers(self, company: str) -> Set[str]:
        """Get the US tickers of a company's listings.

        Args:
            company (str): The company key.

        Returns:
            Set[str]: The tickers of its listings on a US exchange.
        """
        tickers: Set[str] = set()
        for listing in self.markets.listings_of(company):
            exchange, _, symbol = listing.symbol.partition(":")
            if exchange.upper() in self.US_EXCHANGES and symbol:
                tickers.add(symbol.upper())
        return tickers

    def _lookups(self, response: Response) -> List[Request]:
        """Request the submissions of every candidate filer of the tickers file.

        Args:
            response (Response): The tickers file.

        Returns:
            List[Request]: A request per company and candidate filer.
        """
        rows = [(*row, self.names.key(row[1])) for row in self._rows(self._json_body(response))]
        headers = self._sec_headers()
        requests: List[Request] = []
        for entry in self.companies.entries(self.scope.companies):
            known, tickers = set(entry.sec_ciks), self._tickers(entry.key)
            label = self.names.key(self.labels.get(entry.key, ""))
            asked: Set[str] = set()
            for cik, name, ticker, _, key in rows:
                if cik in known or cik in asked:
                    continue
                if ticker in tickers:
                    reason, expected = f"its ticker {ticker} is a listing of the company", ticker
                elif label and key == label:
                    reason, expected = f"its name {name} is the company's", ""
                else:
                    continue
                asked.add(cik)
                meta: Dict[str, JsonValue] = {
                    CompanyMeta.STEP.value: SecIdentityStep.SUBMISSIONS.value,
                    CompanyMeta.FILER.value: cik,
                    CompanyMeta.REASON.value: reason,
                    CompanyMeta.TICKER.value: expected,
                }
                requests.append(self._company_request(self.SUBMISSIONS_URL.format(cik=cik), headers, entry.key, meta))
        self.logger.info("%d candidate SEC filers to check.", len(requests))
        return requests

    def _candidate(self, response: Response) -> Optional[IdentityCandidate]:
        """Read a candidate filer from its submissions.

        Args:
            response (Response): The submissions of the filer.

        Returns:
            Optional[IdentityCandidate]: The filer, verified when it states the listed ticker expected, `None` when
                the submissions are invalid.
        """
        document = self._as_object(self._json_body(response))
        cik = self._meta_text(response, CompanyMeta.FILER)
        expected = self._meta_text(response, CompanyMeta.TICKER)
        raw = document.get(SecIdentityField.TICKERS)
        stated = {ticker.upper() for ticker in raw if isinstance(ticker, str)} if isinstance(raw, list) else set()
        verified = bool(expected) and expected in stated
        if expected and not verified:
            self.logger.warning("The SEC filer %s does not state the ticker %s: it waits for a person.", cik, expected)
        try:
            return IdentityCandidate(
                company=self._company(response),
                identifier_kind=IdentifierKind.SEC_CIK,
                value=cik,
                label=self._as_text(document.get(SecIdentityField.NAME)) or cik,
                evidence_url=self.EVIDENCE_URL.format(cik=cik.lstrip("0") or "0"),
                reason=self._meta_text(response, CompanyMeta.REASON) or "a listed filer",
                verified=verified,
            )
        except ValidationError as e:
            self.logger.warning("Invalid SEC filer %s left out: %s", cik, e.errors()[0]["msg"])
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the tickers file: the listed filers.

        Yields:
            Request: The request of the tickers file.
        """
        entries = self.companies.entries(self.scope.companies)
        self.logger.info("Requesting the SEC tickers file for %d companies.", len(entries))
        yield self._company_request(
            self.TICKERS_URL, self._sec_headers(), "", {CompanyMeta.STEP.value: SecIdentityStep.TICKERS.value}
        )

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether SEC EDGAR refused a request: a filer without submissions (HTTP 404) is not a refusal.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether the response is a refusal, retried by the engine.
        """
        if response.status == 404:
            self.logger.info("No SEC document at %s (HTTP 404).", response.url)
            return False
        return await super().is_blocked(response)

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the candidate filer of a submissions document (the tickers file gives none itself).

        Args:
            response (Response): The document.

        Returns:
            Iterator[CompanyFact]: The candidate filer, verified or not.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        if response.status != 200 or self._step(response) != SecIdentityStep.SUBMISSIONS:
            self.logger.debug("No candidate in the SEC answer %s (HTTP %s).", response.url, response.status)
            return
        candidate = self._candidate(response)
        if candidate is not None:
            self.logger.info(
                "SEC filer %s (%s) proposed for %s%s.",
                candidate.value,
                candidate.label,
                candidate.company,
                ", verified" if candidate.verified else "",
            )
            yield candidate

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Request the submissions of the candidate filers of the tickers file.

        Args:
            response (Response): The document.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: A request per candidate filer, after the tickers file only.

        Raises:
            CatalogueFormatError: If the tickers file is not JSON.
        """
        if response.status != 200 or self._step(response) != SecIdentityStep.TICKERS:
            return iter(())
        return iter(self._lookups(response))
