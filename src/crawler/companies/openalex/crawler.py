from __future__ import annotations

# Standard Library Imports.
import json
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.enums import CompanyMeta
from crawler.companies.openalex.enums import OpenAlexField, OpenAlexStep
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.catalog.openalex_affiliation import OpenAlexAffiliation
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.papers.researcher_record import ResearcherRecord
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog


class OpenAlexCrawler(BaseCompanyCrawler):
    """Crawl the research papers of the companies' institutions from OpenAlex, and their researchers' profiles.

    Attributes:
        API_URL (ClassVar[str]): The OpenAlex API root.
        WORK_FIELDS (ClassVar[str]): The fields asked for each work.
        AUTHOR_FIELDS (ClassVar[str]): The fields asked for each author.
        KEY_PARAMETER (ClassVar[str]): The query parameter carrying the API key.
        PAGE_LIMIT (ClassVar[int]): The most results OpenAlex serves by page number (a cursor reads beyond it, with a
            key only).
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): OpenAlex.
        catalogue_url (ClassVar[str]): The OpenAlex API root.
        keys (List[str]): The API keys read from their environment variables, rotated on HTTP 429.
        key_index (int): The key in use.
        mailto (Optional[str]): The contact sent when no key is set.
        read (Dict[str, int]): The papers read so far, by company.
        asked (Dict[str, Set[str]]): The researchers already asked for, by company.
        left_out (Dict[str, int]): The papers left out because none of their authors is a member, by company.

    Notes:
        - Per company: the papers per publication year (`group_by=publication_year`, OpenAlex's exact count), then
          every paper of its institutions (`authorships.institutions.lineage`, which matches their child
          laboratories) year by year, then the profiles of the authors who signed with one of its institutions, by
          batches.
        - A year is read by page number (no key needed, up to 10,000 papers). A larger year is read with a cursor,
          which OpenAlex only serves with an API key (HTTP 401 without one): without a key its first 10,000 papers
          are read and a warning says so.
        - The API keys are mega-trends' (`OPENALEX_API_KEY_1`, `OPENALEX_API_KEY_2`), sent as `api_key`, the next
          one used when OpenAlex answers HTTP 429 (a key's daily budget spent). Without a key, the requests share
          the machine's small free budget. `robots.txt` allows the API.
        - An author is a member of the company when one of their institutions in the paper belongs to the company's
          lineage and the affiliation text OpenAlex resolved to it matches none of the company's
          `exclude_affiliations` (OpenAlex resolves the Amazon Environmental Research Institute to Amazon). A paper
          without a member is left out, and only the members' profiles are asked for, with the evidence of their
          affiliation (last known institution, years at the company) that confirms them after the search.
    """

    API_URL: ClassVar[str] = "https://api.openalex.org"
    WORK_FIELDS: ClassVar[str] = (
        "id,doi,title,publication_year,publication_date,type,language,cited_by_count,fwci,open_access,"
        "primary_location,primary_topic,authorships"
    )
    AUTHOR_FIELDS: ClassVar[str] = (
        "id,display_name,orcid,works_count,cited_by_count,summary_stats,last_known_institutions,affiliations"
    )
    KEY_PARAMETER: ClassVar[str] = "api_key"
    PAGE_LIMIT: ClassVar[int] = 10000
    name = "openalex"
    feed: ClassVar[CompanyFeed] = CompanyFeed.OPENALEX
    catalogue_url: ClassVar[str] = "https://api.openalex.org/"

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
        settings = self.companies.openalex
        self.download_delay = settings.delay_seconds
        self.keys = [key for key in (self._secret(variable) for variable in settings.key_envs) if key]
        self.max_blocked_retries = max(len(self.keys), 1)
        self.key_index = 0
        self.mailto = self._secret(settings.mailto_env)
        self.read: Dict[str, int] = {}
        self.asked: Dict[str, Set[str]] = {}
        self.left_out: Dict[str, int] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _url(self, path: str, parameters: Dict[str, str]) -> str:
        """Build an API URL, with the key in use or the contact.

        Args:
            path (str): The endpoint, e.g. `/works`.
            parameters (Dict[str, str]): The query parameters.

        Returns:
            str: The URL.
        """
        query = dict(parameters)
        if self.keys:
            query[self.KEY_PARAMETER] = self.keys[self.key_index]
        elif self.mailto:
            query["mailto"] = self.mailto
        return f"{self.API_URL}{path}?{urlencode(query, safe=':|,*')}"

    def _lineage(self, entry: CompanyEntry) -> str:
        """Build the lineage filter of a company's institutions.

        Args:
            entry (CompanyEntry): The company.

        Returns:
            str: The filter, e.g. `authorships.institutions.lineage:I1|I2`.
        """
        return f"authorships.institutions.lineage:{'|'.join(entry.openalex.institutions)}"

    def _request(
        self, entry: CompanyEntry, path: str, parameters: Dict[str, str], step: OpenAlexStep, **meta: JsonValue
    ) -> Request:
        """Build a request of a company.

        Args:
            entry (CompanyEntry): The company.
            path (str): The endpoint.
            parameters (Dict[str, str]): The query parameters.
            step (OpenAlexStep): What it reads.
            **meta (JsonValue): The other request meta.

        Returns:
            Request: The request.
        """
        return self._company_request(
            self._url(path, parameters),
            self._headers("application/json"),
            entry.key,
            {CompanyMeta.STEP.value: step.value, **meta},
        )

    def _works_request(
        self, entry: CompanyEntry, year: int, expected: int, page: int = 1, cursor: Optional[str] = None
    ) -> Request:
        """Build the request of a page of a company's papers of a publication year.

        Args:
            entry (CompanyEntry): The company.
            year (int): The publication year.
            expected (int): The papers OpenAlex counts that year.
            page (int): The page, from 1 (read by page number).
            cursor (Optional[str]): The cursor of the page (`*` for the first), when read with a cursor.

        Returns:
            Request: The request.
        """
        parameters = {
            "filter": f"{self._lineage(entry)},publication_year:{year}",
            "per-page": str(self.companies.openalex.per_page),
            "select": self.WORK_FIELDS,
        }
        if cursor is None:
            parameters["page"] = str(page)
        else:
            parameters["cursor"] = cursor
        meta: Dict[str, JsonValue] = {
            CompanyMeta.YEAR.value: year,
            CompanyMeta.EXPECTED.value: expected,
            CompanyMeta.PAGE.value: page,
            CompanyMeta.CURSOR.value: cursor,
        }
        return self._request(entry, "/works", parameters, OpenAlexStep.WORKS, **meta)

    def _first_pages(self, entry: CompanyEntry, document: Dict[str, JsonValue]) -> List[Request]:
        """Request the first page of each publication year a count states.

        Args:
            entry (CompanyEntry): The company.
            document (Dict[str, JsonValue]): The decoded count (`group_by=publication_year`).

        Returns:
            List[Request]: A request per year with papers.
        """
        requests: List[Request] = []
        groups = document.get(OpenAlexField.GROUP_BY)
        for group in groups if isinstance(groups, list) else []:
            item = self._as_object(group)
            key, count = item.get(OpenAlexField.KEY), item.get(OpenAlexField.COUNT)
            if not (isinstance(key, (str, int)) and str(key).isdigit() and isinstance(count, int) and count > 0):
                continue
            year = int(key)
            if count <= self.PAGE_LIMIT:
                requests.append(self._works_request(entry, year, count))
            elif self.keys:
                requests.append(self._works_request(entry, year, count, cursor="*"))
            else:
                self.logger.warning(
                    "%s %d: %d papers, only %d readable without an OpenAlex key.",
                    entry.key,
                    year,
                    count,
                    self.PAGE_LIMIT,
                )
                requests.append(self._works_request(entry, year, count))
        return requests

    def _next_page(
        self, entry: CompanyEntry, response: Response, document: Dict[str, JsonValue], found: int
    ) -> Optional[Request]:
        """Request the next page of a year's papers, if any.

        Args:
            entry (CompanyEntry): The company.
            response (Response): The page read.
            document (Dict[str, JsonValue]): The decoded page.
            found (int): The papers it gave.

        Returns:
            Optional[Request]: The next page, `None` after the last one or at the limit of papers.
        """
        limit = self.companies.openalex.max_works
        if limit and self.read.get(entry.key, 0) >= limit:
            self.logger.info("%s: the limit of %d papers is reached.", entry.key, limit)
            return None
        meta = response.meta
        year, expected, page = meta.get(CompanyMeta.YEAR), meta.get(CompanyMeta.EXPECTED), meta.get(CompanyMeta.PAGE)
        if not (isinstance(year, int) and isinstance(expected, int) and isinstance(page, int)) or not found:
            return None
        if meta.get(CompanyMeta.CURSOR) is not None:
            cursor = self._as_object(document.get(OpenAlexField.META)).get(OpenAlexField.NEXT_CURSOR)
            return (
                self._works_request(entry, year, expected, page + 1, cursor=cursor)
                if isinstance(cursor, str) and cursor
                else None
            )
        per_page = self.companies.openalex.per_page
        if page * per_page >= min(expected, self.PAGE_LIMIT):
            return None
        return self._works_request(entry, year, expected, page + 1)

    def _redacted(self, url: str) -> str:
        """Hide the API key of a URL, for the logs.

        Args:
            url (str): The URL.

        Returns:
            str: The URL, its key replaced by `***`.
        """
        parts = urlsplit(url)
        query = [(key, "***" if key == self.KEY_PARAMETER else value) for key, value in parse_qsl(parts.query)]
        return urlunsplit(parts._replace(query=urlencode(query, safe=":|,*")))

    def _document(self, response: Response) -> Dict[str, JsonValue]:
        """Decode an answer.

        Args:
            response (Response): The answer.

        Returns:
            Dict[str, JsonValue]: The decoded answer, empty when it is not JSON (logged).
        """
        try:
            return self._as_object(json.loads(self._body_text(response)))
        except ValueError:
            self.logger.warning("The OpenAlex answer %s is not JSON.", self._redacted(response.url))
            return {}

    def _counts(self, response: Response, document: Dict[str, JsonValue]) -> Iterator[CompanyFact]:
        """Read the papers per publication year.

        Args:
            response (Response): The answer.
            document (Dict[str, JsonValue]): The decoded answer.

        Returns:
            Iterator[CompanyFact]: A count per year.
        """
        groups = document.get(OpenAlexField.GROUP_BY)
        for group in groups if isinstance(groups, list) else []:
            item = self._as_object(group)
            try:
                yield PaperYearCount(
                    company=self._company(response),
                    year=item.get(OpenAlexField.KEY),
                    papers=item.get(OpenAlexField.COUNT),
                    source_url=self._redacted(response.url),
                )
            except ValidationError as e:
                self.logger.debug("OpenAlex group left out: %s", e.errors()[0]["msg"])

    def _short(self, value: JsonValue) -> str:
        """Shorten an OpenAlex identifier.

        Args:
            value (JsonValue): The identifier, often a full URL.

        Returns:
            str: Its last part, e.g. `I1311688040`, empty when it is not a text.
        """
        return value.rsplit("/", 1)[-1] if isinstance(value, str) else ""

    def _belongs(self, institution: Dict[str, JsonValue], affiliation: OpenAlexAffiliation) -> bool:
        """Tell whether an institution belongs to the company: itself or one of its parents is a company's.

        Args:
            institution (Dict[str, JsonValue]): The institution, with its lineage.
            affiliation (OpenAlexAffiliation): The company's institutions.

        Returns:
            bool: Whether its lineage meets the company's institutions.
        """
        lineage = institution.get(OpenAlexField.LINEAGE)
        ids = {self._short(item) for item in lineage} if isinstance(lineage, list) else set()
        ids.add(self._short(institution.get(OpenAlexField.ID)))
        return bool(ids.intersection(affiliation.institutions))

    def _member(self, authorship: Dict[str, JsonValue], ids: List[str], affiliation: OpenAlexAffiliation) -> bool:
        """Tell whether an author signed a paper as a member of the company.

        Args:
            authorship (Dict[str, JsonValue]): The authorship.
            ids (List[str]): Its institutions belonging to the company.
            affiliation (OpenAlexAffiliation): The company's institutions and the homonyms' patterns.

        Returns:
            bool: Whether one of the company's institutions comes from an affiliation text naming the company (a
                paper without affiliation texts is trusted, unless the company's texts must match a pattern).
        """
        if not ids:
            return False
        raw = authorship.get(OpenAlexField.AFFILIATIONS)
        texts: List[str] = []
        for item in raw if isinstance(raw, list) else []:
            entry = self._as_object(item)
            resolved = entry.get(OpenAlexField.INSTITUTION_IDS)
            names = {self._short(identifier) for identifier in resolved} if isinstance(resolved, list) else set()
            text = self._as_text(entry.get(OpenAlexField.RAW_AFFILIATION))
            if text and names.intersection(ids):
                texts.append(text)
        if not texts:
            return not affiliation.include_affiliations
        return any(not affiliation.excludes(text) for text in texts)

    def _authorships(self, work: Dict[str, JsonValue], affiliation: OpenAlexAffiliation) -> List[Dict[str, JsonValue]]:
        """Read the authors of a work, marking the members of the company.

        Args:
            work (Dict[str, JsonValue]): The work.
            affiliation (OpenAlexAffiliation): The company's institutions and the homonyms' patterns.

        Returns:
            List[Dict[str, JsonValue]]: The authorships, as `PaperAuthorship` fields.
        """
        authorships: List[Dict[str, JsonValue]] = []
        raw = work.get(OpenAlexField.AUTHORSHIPS)
        for position, item in enumerate(raw if isinstance(raw, list) else []):
            authorship = self._as_object(item)
            author = self._as_object(authorship.get(OpenAlexField.AUTHOR))
            listed = authorship.get(OpenAlexField.INSTITUTIONS)
            institutions = [
                self._as_object(institution) for institution in (listed if isinstance(listed, list) else [])
            ]
            ids = [
                identifier
                for identifier in (self._short(item.get(OpenAlexField.ID)) for item in institutions)
                if identifier
            ]
            company = [
                self._short(institution.get(OpenAlexField.ID))
                for institution in institutions
                if self._belongs(institution, affiliation)
            ]
            name = self._as_text(author.get(OpenAlexField.DISPLAY_NAME))
            if not name:
                continue
            authorships.append(
                {
                    "position": position,
                    "author_id": self._as_text(author.get(OpenAlexField.ID)),
                    "name": name,
                    "orcid": self._as_text(author.get(OpenAlexField.ORCID)),
                    "institutions": list(ids),
                    "company_affiliated": self._member(authorship, company, affiliation),
                }
            )
        return authorships

    def _paper(
        self, response: Response, work: Dict[str, JsonValue], affiliation: OpenAlexAffiliation
    ) -> Optional[PaperRecord]:
        """Build the record of a work.

        Args:
            response (Response): The page.
            work (Dict[str, JsonValue]): The work.
            affiliation (OpenAlexAffiliation): The company's institutions and the homonyms' patterns.

        Returns:
            Optional[PaperRecord]: The paper, `None` when it does not validate (logged).
        """
        location = self._as_object(work.get(OpenAlexField.PRIMARY_LOCATION))
        try:
            return PaperRecord(
                openalex_id=work.get(OpenAlexField.ID),
                company=self._company(response),
                doi=work.get(OpenAlexField.DOI),
                title=work.get(OpenAlexField.TITLE),
                publication_year=work.get(OpenAlexField.YEAR),
                publication_date=work.get(OpenAlexField.DATE),
                type=work.get(OpenAlexField.TYPE),
                venue=self._as_object(location.get(OpenAlexField.SOURCE)).get(OpenAlexField.DISPLAY_NAME),
                language=work.get(OpenAlexField.LANGUAGE),
                cited_by_count=work.get(OpenAlexField.CITED_BY),
                fwci=work.get(OpenAlexField.FWCI),
                is_oa=self._as_object(work.get(OpenAlexField.OPEN_ACCESS)).get(OpenAlexField.IS_OA),
                topic=self._as_object(work.get(OpenAlexField.PRIMARY_TOPIC)).get(OpenAlexField.DISPLAY_NAME),
                authorships=self._authorships(work, affiliation),
                source_url=self._redacted(response.url),
            )
        except ValidationError as e:
            self.logger.warning("OpenAlex work %s left out: %s", work.get(OpenAlexField.ID), e.errors()[0]["msg"])
            return None

    def _evidence(self, author: Dict[str, JsonValue], affiliation: OpenAlexAffiliation) -> Tuple[bool, int]:
        """Read the evidence of an author's membership of the company in their profile.

        Args:
            author (Dict[str, JsonValue]): The author's profile.
            affiliation (OpenAlexAffiliation): The company's institutions.

        Returns:
            Tuple[bool, int]: Whether one of their last known institutions is the company's, then the years their
                profile lists at the company.
        """
        last = author.get(OpenAlexField.LAST_INSTITUTIONS)
        current = any(
            self._belongs(self._as_object(institution), affiliation)
            for institution in (last if isinstance(last, list) else [])
        )
        years: Set[int] = set()
        listed = author.get(OpenAlexField.AFFILIATIONS)
        for item in listed if isinstance(listed, list) else []:
            entry = self._as_object(item)
            if self._belongs(self._as_object(entry.get(OpenAlexField.INSTITUTION)), affiliation):
                spans = entry.get(OpenAlexField.YEARS)
                years.update(year for year in (spans if isinstance(spans, list) else []) if isinstance(year, int))
        return current, len(years)

    def _researcher(
        self, response: Response, author: Dict[str, JsonValue], affiliation: OpenAlexAffiliation
    ) -> Optional[ResearcherRecord]:
        """Build the profile of an author, with the evidence of their membership.

        Args:
            response (Response): The page.
            author (Dict[str, JsonValue]): The author.
            affiliation (OpenAlexAffiliation): The company's institutions.

        Returns:
            Optional[ResearcherRecord]: The profile, `None` when it does not validate (logged).
        """
        last = author.get(OpenAlexField.LAST_INSTITUTIONS)
        first_last = self._as_object(last[0]) if isinstance(last, list) and last else {}
        current, years = self._evidence(author, affiliation)
        try:
            return ResearcherRecord(
                author_id=author.get(OpenAlexField.ID),
                company=self._company(response),
                name=author.get(OpenAlexField.DISPLAY_NAME),
                orcid=author.get(OpenAlexField.ORCID),
                works_count=author.get(OpenAlexField.WORKS_COUNT),
                cited_by_count=author.get(OpenAlexField.CITED_BY),
                h_index=self._as_object(author.get(OpenAlexField.SUMMARY)).get(OpenAlexField.H_INDEX),
                institution=first_last.get(OpenAlexField.DISPLAY_NAME),
                current_affiliation=current,
                affiliation_years=years,
                source_url=self._redacted(response.url),
            )
        except ValidationError as e:
            self.logger.warning("OpenAlex author %s left out: %s", author.get(OpenAlexField.ID), e.errors()[0]["msg"])
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Count the papers of every company read with institutions, per publication year.

        Yields:
            Request: The count of each company (its years' pages follow).
        """
        if not self.keys:
            self.logger.warning("No OpenAlex key set: the requests share the machine's small free daily budget.")
        entries = [entry for entry in self.companies.entries(self.scope.companies) if entry.openalex.institutions]
        self.logger.info("Reading the papers of %d companies from OpenAlex (%d keys).", len(entries), len(self.keys))
        for entry in entries:
            yield self._request(
                entry, "/works", {"filter": self._lineage(entry), "group_by": "publication_year"}, OpenAlexStep.COUNT
            )

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether OpenAlex refused the request (a key's budget spent), moving to the next key.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether it is a refusal, retried with the next key while one is left.
        """
        if response.status != 429:
            return await super().is_blocked(response)
        if self.key_index + 1 < len(self.keys):
            self.key_index += 1
            self.logger.warning(
                "OpenAlex refused key %d (HTTP 429): moving to key %d.", self.key_index, self.key_index + 1
            )
        else:
            self.logger.warning(
                "OpenAlex refused the last key (HTTP 429): stopping, the rest is left for the next run."
            )
            self.refusal = (
                "OpenAlex refused the search (HTTP 429, the daily budget of the machine or of its keys is spent): "
                "what was read is kept, the next search reads the rest"
            )
            self.pause()
        return True

    async def retry_blocked_request(self, request: Request, response: Response) -> Request:
        """Send a refused request again with the key in use.

        Args:
            request (Request): The copy of the refused request.
            response (Response): The refusal.

        Returns:
            Request: The request, its key replaced.
        """
        if self.keys:
            parts = urlsplit(request.url)
            query = [(key, value) for key, value in parse_qsl(parts.query) if key != self.KEY_PARAMETER]
            query.append((self.KEY_PARAMETER, self.keys[self.key_index]))
            request.url = urlunsplit(parts._replace(query=urlencode(query, safe=":|,*")))
        self.logger.debug("Retrying %s after HTTP %s.", self._redacted(request.url), response.status)
        return request

    async def on_close(self) -> None:
        """Log the papers left out because none of their authors is a member of the company."""
        await super().on_close()
        for company, count in sorted(self.left_out.items()):
            self.logger.info(
                "%s: %d of %d papers left out, no author signed as a member (homonym institutions).",
                company,
                count,
                self.read.get(company, 0),
            )

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the counts, the papers or the profiles of an answer.

        Args:
            response (Response): The answer.

        Returns:
            Iterator[CompanyFact]: The facts of the answer.
        """
        if response.status != 200:
            self.logger.warning("OpenAlex answered %s with HTTP %s.", self._redacted(response.url), response.status)
            return
        document = self._document(response)
        step = response.meta.get(CompanyMeta.STEP)
        entry = self.companies.entry(self._company(response))
        if entry is None:
            return
        if step == OpenAlexStep.COUNT:
            yield from self._counts(response, document)
            return
        results = document.get(OpenAlexField.RESULTS)
        items = [self._as_object(item) for item in (results if isinstance(results, list) else [])]
        if step == OpenAlexStep.AUTHORS:
            for author in items:
                researcher = self._researcher(response, author, entry.openalex)
                if researcher is not None:
                    yield researcher
            return
        for work in items:
            paper = self._paper(response, work, entry.openalex)
            if paper is None:
                continue
            self.read[entry.key] = self.read.get(entry.key, 0) + 1
            if not any(authorship.company_affiliated for authorship in paper.authorships):
                self.left_out[entry.key] = self.left_out.get(entry.key, 0) + 1
                self.rejected.setdefault(entry.key, set()).add(paper.openalex_id)
                self.logger.debug("%s: %s left out, none of its authors is a member.", entry.key, paper.openalex_id)
                continue
            yield paper

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Request the years' first pages after a count, else the next page and the new company researchers of a page.

        Args:
            response (Response): The answer.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: The pages of the years, or the next page then the batches of new researchers.
        """
        entry = self.companies.entry(self._company(response))
        step = response.meta.get(CompanyMeta.STEP)
        if entry is None or response.status != 200 or step == OpenAlexStep.AUTHORS:
            return iter(())
        document = self._document(response)
        if step == OpenAlexStep.COUNT:
            return iter(self._first_pages(entry, document))
        requests: List[Request] = []
        following = self._next_page(entry, response, document, found)
        if following is not None:
            requests.append(following)
        asked = self.asked.setdefault(entry.key, set())
        results = document.get(OpenAlexField.RESULTS)
        new: List[str] = []
        for work in results if isinstance(results, list) else []:
            for authorship in self._authorships(self._as_object(work), entry.openalex):
                author = authorship.get("author_id")
                if authorship.get("company_affiliated") and isinstance(author, str):
                    identifier = author.rsplit("/", 1)[-1]
                    if identifier not in asked:
                        asked.add(identifier)
                        new.append(identifier)
        batch = self.companies.openalex.author_batch
        for start in range(0, len(new), batch):
            ids = "|".join(new[start : start + batch])
            parameters = {"filter": f"id:{ids}", "per-page": str(batch), "select": self.AUTHOR_FIELDS}
            requests.append(self._request(entry, "/authors", parameters, OpenAlexStep.AUTHORS))
        return iter(requests)
