from __future__ import annotations

# Standard Library Imports.
import re
from collections import Counter
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Pattern, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.edgar.enums import CompanyFactsField, XbrlUnit
from crawler.companies.enums import CompanyMeta
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concept import FinancialConcept
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed, FinancialMetric, FinancialNature, FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog


class EdgarFinancialsCrawler(BaseCompanyCrawler):
    """Crawl the financial statements the companies filed with the SEC (EDGAR XBRL `companyfacts`, 2009 onwards).

    Attributes:
        URL (ClassVar[str]): The `companyfacts` document, formatted with the 10-digit filer.
        FILINGS (ClassVar[Tuple[str, ...]]): The prefixes of the forms read: the quarterly and annual reports of the
            US filers (10-Q, 10-K) and of the foreign ones (20-F, 40-F), their amendments included.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency unit.
        SHARE_COUNTS (ClassVar[FrozenSet[FinancialMetric]]): The statement lines counting shares (read in `shares`).
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): SEC EDGAR.
        catalogue_url (ClassVar[str]): The EDGAR data host.
        download_delay (float): A quarter of a second between two filers (SEC allows ten requests a second).

    Notes:
        - One document per filer holds every fact the filer ever filed in XBRL, each period being repeated by the
          later filings comparing with it: every fact of the mapped concepts is streamed as filed (start, end,
          form, fiscal period, filing day), and `analytics.companies` keeps the latest filing of each period and
          derives the quarters the 10-Q only state year to date.
        - `companyfacts` holds the facts without dimension: the figures are the group's.
        - A 20-F files its amounts in the reporting currency and some again in US dollars (a convenience
          translation): only the most used currency of the document is read, so a period is never stated twice.
        - A filer without XBRL (before 2009, or filing no statement) answers HTTP 404: nothing is streamed.
        - SEC EDGAR asks for a user agent naming a contact, read from the environment variable of the catalogue.
    """

    URL: ClassVar[str] = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    FILINGS: ClassVar[Tuple[str, ...]] = ("10-Q", "10-K", "20-F", "40-F")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    SHARE_COUNTS: ClassVar[FrozenSet[FinancialMetric]] = frozenset(
        {FinancialMetric.SHARES_OUTSTANDING, FinancialMetric.DILUTED_SHARES}
    )
    name = "edgar-financials"
    feed: ClassVar[CompanyFeed] = CompanyFeed.EDGAR
    catalogue_url: ClassVar[str] = "https://data.sec.gov/"
    download_delay: float = 0.25

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
            companies (Optional[CompaniesCatalog]): Where each company is found, `data/curated/companies.json` by
                default.
            concepts (Optional[FinancialConcepts]): How the statement lines are read, by default
                the `concepts` block of `conf/settings.yaml`.
            markets (Optional[MarketsCatalog]): The listings, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The companies read, every one by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            CompaniesCatalogError: If a default catalogue cannot be loaded.
            MarketsCatalogError: If the default markets catalogue cannot be loaded.
        """
        super().__init__(
            companies=companies, concepts=concepts, markets=markets, scope=scope, crawldir=crawldir, interval=interval
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _concept_units(self, document: JsonValue, name: str) -> Dict[str, JsonValue]:
        """Get the facts of a concept, by unit.

        Args:
            document (JsonValue): The `companyfacts` document.
            name (str): The concept, `taxonomy:Name`.

        Returns:
            Dict[str, JsonValue]: Its facts by unit, empty when the filer does not report it.
        """
        taxonomy, _, concept = name.partition(":")
        facts = self._as_object(self._as_object(document).get(CompanyFactsField.FACTS))
        return self._as_object(
            self._as_object(self._as_object(facts.get(taxonomy)).get(concept)).get(CompanyFactsField.UNITS)
        )

    def _reporting_currency(self, document: JsonValue) -> Optional[str]:
        """Find the reporting currency of a filer: the currency unit of the most facts of the mapped concepts.

        Args:
            document (JsonValue): The `companyfacts` document.

        Returns:
            Optional[str]: The currency, `None` when no mapped concept states an amount.
        """
        counts: Counter[str] = Counter()
        for concept in self.concepts.concepts:
            for name in concept.concepts:
                for unit, facts in self._concept_units(document, name).items():
                    if self.CURRENCY.match(unit) and isinstance(facts, list):
                        counts[unit] += len(facts)
        return counts.most_common(1)[0][0] if counts else None

    def _unit_of(self, concept: FinancialConcept, currency: str) -> Tuple[str, Optional[str]]:
        """Get the unit a statement line is read in, and the currency it is stored with.

        Args:
            concept (FinancialConcept): The statement line.
            currency (str): The reporting currency.

        Returns:
            Tuple[str, Optional[str]]: The XBRL unit, and the currency (`None` for a number of shares).
        """
        if concept.metric in self.SHARE_COUNTS:
            return XbrlUnit.SHARES.value, None
        if concept.nature is FinancialNature.PER_SHARE:
            return f"{currency}{XbrlUnit.PER_SHARE.value}", currency
        return currency, currency

    def _facts_of(
        self, document: JsonValue, concept: FinancialConcept, name: str, currency: str
    ) -> List[Dict[str, JsonValue]]:
        """Get the facts of a concept in the unit of its statement line, from the quarterly and annual reports.

        Args:
            document (JsonValue): The `companyfacts` document.
            concept (FinancialConcept): The statement line.
            name (str): The concept, `taxonomy:Name`.
            currency (str): The reporting currency.

        Returns:
            List[Dict[str, JsonValue]]: The facts, as filed.
        """
        unit, _ = self._unit_of(concept, currency)
        found = self._concept_units(document, name).get(unit)
        facts = [self._as_object(fact) for fact in found] if isinstance(found, list) else []
        return [fact for fact in facts if str(fact.get(CompanyFactsField.FORM, "")).startswith(self.FILINGS)]

    def _fact(
        self,
        response: Response,
        concept: FinancialConcept,
        name: str,
        fact: Dict[str, JsonValue],
        currency: Optional[str],
    ) -> Optional[FinancialFact]:
        """Build the financial fact of a filed XBRL fact.

        Args:
            response (Response): The `companyfacts` document.
            concept (FinancialConcept): The statement line.
            name (str): The concept, `taxonomy:Name`.
            fact (Dict[str, JsonValue]): The filed fact.
            currency (Optional[str]): The currency it is stored with, `None` for shares.

        Returns:
            Optional[FinancialFact]: The fact, `None` when it does not validate (logged).
        """
        value = fact.get(CompanyFactsField.VALUE)
        if concept.negate and isinstance(value, (int, float)) and not isinstance(value, bool):
            value = -value
        filer = response.meta.get(CompanyMeta.FILER)
        try:
            return FinancialFact(
                company=self._company(response),
                source=FinancialSource.EDGAR,
                metric=concept.metric,
                concept=name,
                filer=filer if isinstance(filer, str) else None,
                start=fact.get(CompanyFactsField.START),
                end=fact.get(CompanyFactsField.END),
                value=value,
                currency=currency,
                form=fact.get(CompanyFactsField.FORM),
                fiscal_year=fact.get(CompanyFactsField.FISCAL_YEAR),
                fiscal_period=fact.get(CompanyFactsField.FISCAL_PERIOD),
                filed=fact.get(CompanyFactsField.FILED),
                source_url=response.url,
            )
        except ValidationError as e:
            self.logger.warning("Invalid %s fact in %s left out: %s", name, response.url, e.errors()[0]["msg"])
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the `companyfacts` document of every SEC filer of the companies read.

        Yields:
            Request: A request per filer.
        """
        headers = self._headers("application/json")
        agent = self._secret(self.companies.sec_user_agent_env)
        if agent is None:
            self.logger.warning(
                "%s is not set: SEC EDGAR may refuse the requests (it asks for a contact).",
                self.companies.sec_user_agent_env,
            )
        headers["User-Agent"] = agent or self.USER_AGENT
        entries = [entry for entry in self.companies.entries(self.scope.companies) if entry.sec_ciks]
        self.logger.info(
            "Requesting the SEC EDGAR facts of %d companies (%d filers).",
            len(entries),
            sum(len(entry.sec_ciks) for entry in entries),
        )
        for entry in entries:
            for cik in entry.sec_ciks:
                self.logger.debug("Requesting the SEC EDGAR facts of %s (filer %s).", entry.key, cik)
                yield self._company_request(
                    self.URL.format(cik=cik), headers, entry.key, {CompanyMeta.FILER.value: cik}
                )

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether SEC EDGAR refused a request: a filer without XBRL (HTTP 404) is not a refusal.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether the response is a refusal, retried by the engine.
        """
        if response.status == 404:
            self.logger.info("No XBRL statements for %s (HTTP 404).", response.url)
            return False
        return await super().is_blocked(response)

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the facts of the mapped concepts from a `companyfacts` document.

        Args:
            response (Response): The document.

        Returns:
            Iterator[CompanyFact]: A financial fact per filed fact of a mapped concept, in the reporting currency.

        Raises:
            CatalogueFormatError: If the document is not JSON.
        """
        if response.status != 200:
            self.logger.debug("Skipping the SEC EDGAR answer %s (HTTP %s).", response.url, response.status)
            return
        document = self._json_body(response)
        currency = self._reporting_currency(document)
        entity = self._as_text(self._as_object(document).get(CompanyFactsField.ENTITY))
        if currency is None:
            self.logger.warning("No mapped amount in the SEC EDGAR facts of %s (%s).", entity, response.url)
            return
        self.logger.info("SEC EDGAR facts of %s (%s) read in %s.", entity, self._company(response), currency)
        found = 0
        for concept in self.concepts.concepts:
            _, stored_currency = self._unit_of(concept, currency)
            for name in concept.concepts:
                for raw in self._facts_of(document, concept, name, currency):
                    fact = self._fact(response, concept, name, raw, stored_currency)
                    if fact is not None:
                        found += 1
                        yield fact
        if not found:
            self.logger.warning("No fact of the mapped concepts for %s in %s.", self._company(response), response.url)
