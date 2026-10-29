from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.openalex_identity.enums import InstitutionField
from curated.company_names import CompanyNames
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.companies.identities.identity_candidate import IdentityCandidate
from models.curated.enums import IdentifierKind
from models.history.chronology import Chronology
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog


class OpenAlexIdentityCrawler(BaseCompanyCrawler):
    """Find the OpenAlex institutions of the companies: the top-level company entries named as the company.

    Attributes:
        URL (ClassVar[str]): The institutions search.
        EVIDENCE_URL (ClassVar[str]): The page of an institution, formatted with its identifier.
        PER_PAGE (ClassVar[int]): The institutions read per company.
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): The OpenAlex identity resolver.
        catalogue_url (ClassVar[str]): The OpenAlex API root.
        names (CompanyNames): Compares the names.
        labels (Dict[str, str]): The name of each company, from the chronology.
        key (Optional[str]): The first OpenAlex key of the catalogue's variables, `None` without any.
        mailto (Optional[str]): The contact sent when no key is set.

    Notes:
        - One search per company, among the institutions of type `company`: an institution whose name, other name
          or acronym is the company's, and which belongs to no other institution (its laboratories are covered by
          the lineage filter of the papers search), is a candidate.
        - A homonym shares a company's name (the papers of an Amazon rainforest institute were once read as
          Amazon's): an institution found is never confirmed at once, a person accepts or rejects it.
        - The institutions already in the catalogue, in any status, are left out.
    """

    URL: ClassVar[str] = "https://api.openalex.org/institutions"
    EVIDENCE_URL: ClassVar[str] = "https://openalex.org/{identifier}"
    PER_PAGE: ClassVar[int] = 10

    name = "openalex-identity"
    feed: ClassVar[CompanyFeed] = CompanyFeed.OPENALEX_IDENTITY
    catalogue_url: ClassVar[str] = "https://api.openalex.org/"

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
            companies (Optional[CompaniesCatalog]): The companies and their institutions,
                `data/curated/companies.json` by default.
            concepts (Optional[FinancialConcepts]): How the statement lines are read (unused here), by default the
                `concepts` block of `conf/settings.yaml`.
            markets (Optional[MarketsCatalog]): The listings (unused here), `data/curated/markets.json` by default.
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
        settings = self.companies.openalex
        self.download_delay = settings.delay_seconds
        self.names = CompanyNames(self.logger)
        named = chronology if chronology else self._bundled_chronology()
        self.labels: Dict[str, str] = {company.key: company.label for company in named.companies}
        self.key = next((key for key in (self._secret(variable) for variable in settings.key_envs) if key), None)
        self.mailto = self._secret(settings.mailto_env)

    ############################
    # Internal Helpers Methods #
    ############################

    def _url(self, label: str) -> str:
        """Build the search of the company institutions named as a company, with the key or the contact.

        Args:
            label (str): The name of the company.

        Returns:
            str: The URL.
        """
        query = {"search": label, "filter": "type:company", "per-page": str(self.PER_PAGE)}
        if self.key:
            query["api_key"] = self.key
        elif self.mailto:
            query["mailto"] = self.mailto
        return f"{self.URL}?{urlencode(query, safe=':')}"

    def _names_of(self, institution: Dict[str, JsonValue]) -> List[str]:
        """Get the names of an institution.

        Args:
            institution (Dict[str, JsonValue]): The institution.

        Returns:
            List[str]: Its name, other names and acronyms.
        """
        names = [institution.get(InstitutionField.DISPLAY_NAME)]
        for field in (InstitutionField.ALTERNATIVES, InstitutionField.ACRONYMS):
            values = institution.get(field)
            names += values if isinstance(values, list) else []
        return [name for name in names if isinstance(name, str) and name]

    def _candidate(self, company: str, institution: Dict[str, JsonValue]) -> Optional[IdentityCandidate]:
        """Read a candidate institution of a company.

        Args:
            company (str): The company key.
            institution (Dict[str, JsonValue]): The institution found.

        Returns:
            Optional[IdentityCandidate]: The institution, `None` when it is the company's already, belongs to
                another institution, is named otherwise or is invalid.
        """
        identifier = (self._as_text(institution.get(InstitutionField.ID)) or "").rstrip("/").rsplit("/", 1)[-1]
        entry = self.companies.entry(company)
        if not identifier or entry is None or identifier in entry.openalex.institutions:
            return None
        lineage = institution.get(InstitutionField.LINEAGE)
        parents = [str(item).rsplit("/", 1)[-1] for item in lineage] if isinstance(lineage, list) else []
        if any(parent != identifier for parent in parents):
            self.logger.debug("The OpenAlex institution %s belongs to another one: left out.", identifier)
            return None
        label = self.labels.get(company, company)
        named = next((name for name in self._names_of(institution) if self.names.match(label, name)), None)
        if named is None:
            return None
        display = self._as_text(institution.get(InstitutionField.DISPLAY_NAME)) or named
        country = self._as_text(institution.get(InstitutionField.COUNTRY)) or "no country"
        works = institution.get(InstitutionField.WORKS)
        try:
            return IdentityCandidate(
                company=company,
                identifier_kind=IdentifierKind.OPENALEX_INSTITUTION,
                value=identifier,
                label=display,
                evidence_url=self.EVIDENCE_URL.format(identifier=identifier),
                reason=f"its name {named} is the company's ({country}, {works if isinstance(works, int) else 0} works)",
            )
        except ValidationError as e:
            self.logger.warning("Invalid OpenAlex institution %s left out: %s", identifier, e.errors()[0]["msg"])
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Search the company institutions named as each company.

        Yields:
            Request: A search per company named in the chronology.
        """
        headers = self._headers("application/json")
        entries = [entry for entry in self.companies.entries(self.scope.companies) if entry.key in self.labels]
        if not self.key and not self.mailto:
            self.logger.warning("No OpenAlex key nor contact is set: the searches use the anonymous budget.")
        self.logger.info("Searching the OpenAlex institutions of %d companies.", len(entries))
        for entry in entries:
            yield self._company_request(self._url(self.labels[entry.key]), headers, entry.key)

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether OpenAlex refused the requests (its budget spent): the rest is left for the next run.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether the response is a refusal.
        """
        if response.status != 429:
            return await super().is_blocked(response)
        self.logger.warning("OpenAlex refused the institutions search (HTTP 429): stopping.")
        self.refusal = "OpenAlex refused the search (HTTP 429, its budget is spent): the next run reads the rest"
        self.pause()
        return True

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the candidate institutions of a company from a search.

        Args:
            response (Response): The search.

        Returns:
            Iterator[CompanyFact]: The candidate institutions.

        Raises:
            CatalogueFormatError: If the answer is not JSON.
        """
        if response.status != 200:
            self.logger.debug("Skipping the OpenAlex answer %s (HTTP %s).", response.url, response.status)
            return
        company = self._company(response)
        results = self._as_object(self._json_body(response)).get(InstitutionField.RESULTS)
        found = 0
        for institution in results if isinstance(results, list) else []:
            candidate = self._candidate(company, self._as_object(institution))
            if candidate is not None:
                found += 1
                self.logger.info(
                    "OpenAlex institution %s (%s) proposed for %s.", candidate.value, candidate.label, company
                )
                yield candidate
        if not found:
            self.logger.info("No new OpenAlex institution named as %s.", company)
