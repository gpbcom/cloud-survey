from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Pattern, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.edgar_schedules.enums import ScheduleHeader, ScheduleStep, SubmissionsField
from crawler.companies.enums import CompanyMeta
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.concepts.schedules.schedule_tag import ScheduleTag
from models.companies.enums import CompanyFeed, FinancialNature, FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

type Filing = Tuple[str, str, date]


class EdgarSchedulesCrawler(BaseCompanyCrawler):
    """Crawl the financial data schedules (EX-27) the companies filed with the SEC from 1993 to 2001.

    Attributes:
        SUBMISSIONS_URL (ClassVar[str]): A `submissions` document of a filer, formatted with its name.
        FILING_URL (ClassVar[str]): The full text of a filing, formatted with the filer and the accession number.
        FIRST_DAY (ClassVar[date]): The first filing day read (EDGAR's electronic filings).
        LAST_DAY (ClassVar[date]): The last filing day read (the schedules were abolished in 2001).
        FILINGS (ClassVar[Tuple[str, ...]]): The prefixes of the forms read: the annual and quarterly reports of
            the US filers (10-K, 10-K405, 10-KSB, 10-Q and their amendments). The foreign filers' 20-F had no schedule.
        PERIODS (ClassVar[Dict[str, str]]): The fiscal period of each period type, e.g. `9-MOS` → `9M`.
        CURRENCIES (ClassVar[Dict[str, str]]): The currency of each way a schedule writes it.
        DOCUMENT (ClassVar[Pattern[str]]): A document of the full text.
        TYPE (ClassVar[Pattern[str]]): The type of a document, e.g. `EX-27`.
        HEADER (ClassVar[Pattern[str]]): A header field of the full text, e.g. `FILED AS OF DATE: 19970917`.
        TAG (ClassVar[Pattern[str]]): A tagged line of a schedule, `<TAG> value…`.
        LEGEND_END (ClassVar[str]): The tag closing the legend (free text) of a schedule.
        SKIPPED (ClassVar[FrozenSet[str]]): The tags framing a document, never values.
        META (ClassVar[FrozenSet[str]]): The tags stating one value for every column (the article, the multiplier).
        AMOUNT (ClassVar[Pattern[str]]): A number as a schedule writes it: `1,234`, `(1,234)`, `-1,234`, `.95`.
        DAY_FORMAT (ClassVar[str]): The format of a day, e.g. `JUN-28-1997`.
        HEADER_DAY_FORMAT (ClassVar[str]): The format of a header day, e.g. `19970917`.
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): The SEC financial data schedules.
        catalogue_url (ClassVar[str]): The EDGAR data host (the `submissions` documents).
        complement_urls (ClassVar[Tuple[str, ...]]): The EDGAR archive host (the full texts).
        download_delay (float): A quarter of a second between two requests (SEC allows ten requests a second).

    Notes:
        - The `submissions` document of a filer lists its filings (and pages of the older ones): the full text of
          each annual and quarterly report filed from 1993 to 2001 is read, and every value of a mapped tag of an
          article 5 schedule is streamed as filed (the tag, the period, the form, the filing day). `analytics`
          keeps the latest filing of each period and derives the quarters the 10-Q only state year to date.
        - A flow carries the period start the schedule states. A balance carries its day only.
        - The amounts are multiplied by the schedule's multiplier, the per-share figures are not.
        - SEC EDGAR's archive refuses the requests whose user agent names no contact (HTTP 403): it is read from
          the environment variable of the catalogue.
        - A schedule is a table: the `<S>` line opens it with a `<C>` per column, each tagged line then gives a value
          per column (a filing restating earlier periods holds several columns). A schedule without that line has
          one column. The tags before the table (`<ARTICLE>`, `<MULTIPLIER>`, `<CURRENCY>`) hold for every column.
    """

    SUBMISSIONS_URL: ClassVar[str] = "https://data.sec.gov/submissions/{name}"
    FILING_URL: ClassVar[str] = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"
    FIRST_DAY: ClassVar[date] = date(1993, 1, 1)
    LAST_DAY: ClassVar[date] = date(2001, 12, 31)
    FILINGS: ClassVar[Tuple[str, ...]] = ("10-K", "10-Q")
    PERIODS: ClassVar[Dict[str, str]] = {"YEAR": "FY", "12-MOS": "FY", "3-MOS": "3M", "6-MOS": "6M", "9-MOS": "9M"}
    CURRENCIES: ClassVar[Dict[str, str]] = {
        "U.S. DOLLARS": "USD",
        "US DOLLARS": "USD",
        "U.S. DOLLAR": "USD",
        "US DOLLAR": "USD",
        "DOLLARS": "USD",
        "USD": "USD",
    }
    DOCUMENT: ClassVar[Pattern[str]] = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
    TYPE: ClassVar[Pattern[str]] = re.compile(r"<TYPE>\s*([^\s<]+)", re.IGNORECASE)
    HEADER: ClassVar[Pattern[str]] = re.compile(r"^\s*([A-Z ]+?):\s*(\S+)\s*$", re.MULTILINE)
    TAG: ClassVar[Pattern[str]] = re.compile(r"^\s*<([A-Z0-9&][A-Z0-9&\-]*)>[ \t]*(.*?)\s*$")
    LEGEND_END: ClassVar[str] = "</LEGEND>"
    SKIPPED: ClassVar[FrozenSet[str]] = frozenset(
        {"TYPE", "SEQUENCE", "DESCRIPTION", "FILENAME", "TEXT", "TABLE", "PAGE", "LEGEND", "S", "C"}
    )
    META: ClassVar[FrozenSet[str]] = frozenset(
        {"ARTICLE", "MULTIPLIER", "CURRENCY", "EXCHANGE-RATE", "NAME", "CIK", "RESTATED", "SERIES", "NUMBER"}
    )
    AMOUNT: ClassVar[Pattern[str]] = re.compile(r"^\(?-?[\d,]*\.?\d+\)?$")
    DAY_FORMAT: ClassVar[str] = "%b-%d-%Y"
    HEADER_DAY_FORMAT: ClassVar[str] = "%Y%m%d"
    name = "edgar-schedules"
    feed: ClassVar[CompanyFeed] = CompanyFeed.EDGAR_SCHEDULES
    catalogue_url: ClassVar[str] = "https://data.sec.gov/"
    complement_urls: ClassVar[Tuple[str, ...]] = ("https://www.sec.gov/",)
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

    def _documents(self, text: str) -> List[str]:
        """Get the schedule documents of a full text.

        Args:
            text (str): The full text of a filing.

        Returns:
            List[str]: The text of each EX-27 document (a filing may hold several, e.g. restated periods).
        """
        documents = []
        for document in self.DOCUMENT.findall(text):
            kind = self.TYPE.search(document)
            if kind and kind.group(1).upper().startswith(ScheduleHeader.SCHEDULE_TYPE.value):
                documents.append(document)
        self.logger.debug("%d financial data schedules in the full text.", len(documents))
        return documents

    def _columns_of(self, document: str) -> List[Dict[str, str]]:
        """Read the columns of a schedule document.

        Args:
            document (str): The text of an EX-27 document.

        Returns:
            List[Dict[str, str]]: The raw value of each tag, per column, the meta tags copied into each column.
        """
        meta: Dict[str, str] = {}
        columns: List[Dict[str, str]] = []
        width = 0
        legend = False
        for line in document.splitlines():
            if legend:
                legend = self.LEGEND_END not in line.upper()
                continue
            stripped = line.strip()
            if stripped.upper().startswith(ScheduleHeader.COLUMNS.value):
                width = max(1, stripped.upper().count(ScheduleHeader.COLUMN.value))
                columns = [{} for _ in range(width)]
                continue
            match = self.TAG.match(line)
            if match is None:
                continue
            tag, value = match.group(1).upper(), match.group(2)
            if tag == "LEGEND":
                legend = self.LEGEND_END not in line.upper()
                continue
            if tag in self.SKIPPED or not value:
                continue
            if tag in self.META or not width:
                meta[tag] = value
                continue
            tokens = value.split()
            if len(tokens) == width:
                for column, token in zip(columns, tokens, strict=True):
                    column[tag] = token
            else:
                self.logger.debug("Schedule line %s has %d values for %d columns: left out.", tag, len(tokens), width)
        if not width:
            columns = [{tag: value for tag, value in meta.items() if tag not in self.META}]
        return [{**{tag: value for tag, value in meta.items() if tag in self.META}, **column} for column in columns]

    def _schedule_header(self, text: str) -> Dict[str, str]:
        """Read the header fields of a full text (the filing day, the form).

        Args:
            text (str): The full text of a filing.

        Returns:
            Dict[str, str]: The value of each header field, by its name, e.g. `FILED AS OF DATE`.
        """
        head = text[: text.upper().find("<DOCUMENT>")] if "<DOCUMENT>" in text.upper() else text[:5000]
        fields = {name.strip().upper(): value for name, value in self.HEADER.findall(head)}
        if ScheduleHeader.FILED.value not in fields:
            self.logger.warning("The full text states no filing day.")
        return fields

    def _schedule_columns(self, text: str) -> List[Dict[str, str]]:
        """Read every column of every schedule of a full text.

        Args:
            text (str): The full text of a filing.

        Returns:
            List[Dict[str, str]]: The raw values of each column, by tag (`PERIOD-END`, `TOTAL-REVENUES`…).
        """
        columns = [column for document in self._documents(text) for column in self._columns_of(document)]
        if not columns:
            self.logger.info("No financial data schedule column in the full text.")
        return columns

    def _amount(self, raw: str) -> Optional[float]:
        """Read a number as a schedule writes it.

        Args:
            raw (str): The raw value, e.g. `3,060,512`, `(1,234)`, `-12`, `.95`.

        Returns:
            Optional[float]: The number, signed, `None` when it is not a number (logged at debug).
        """
        text = raw.strip()
        if not self.AMOUNT.match(text):
            self.logger.debug("Schedule value %r is not a number.", raw)
            return None
        negative = text.startswith("(") or text.startswith("-") or text.startswith("(-")
        number = float(text.strip("()").lstrip("-").replace(",", ""))
        return -number if negative else number

    def _day(self, raw: Optional[str]) -> Optional[date]:
        """Read a day as a schedule writes it.

        Args:
            raw (Optional[str]): The raw day, e.g. `JUN-28-1997`.

        Returns:
            Optional[date]: The day, `None` when missing or malformed (logged).
        """
        if not raw:
            return None
        try:
            return datetime.strptime(raw.strip().title(), self.DAY_FORMAT).date()
        except ValueError:
            self.logger.warning("Schedule day %r is malformed.", raw)
            return None

    def _header_day(self, raw: Optional[str]) -> Optional[date]:
        """Read a day of the full text's header.

        Args:
            raw (Optional[str]): The raw day, e.g. `19970917`.

        Returns:
            Optional[date]: The day, `None` when missing or malformed (logged).
        """
        if not raw:
            return None
        try:
            return datetime.strptime(raw.strip(), self.HEADER_DAY_FORMAT).date()
        except ValueError:
            self.logger.error("Header day %r of the full text is malformed.", raw)
            return None

    def _sec_headers(self, accept: str) -> Dict[str, str]:
        """Build the headers of a request to SEC EDGAR: the user agent naming a contact, from the environment.

        Args:
            accept (str): The media type asked for.

        Returns:
            Dict[str, str]: The headers.
        """
        headers = self._headers(accept)
        headers["User-Agent"] = self._secret(self.companies.sec_user_agent_env) or self.USER_AGENT
        return headers

    def _request(self, url: str, company: str, filer: str, step: ScheduleStep) -> Request:
        """Build a request of the crawl.

        Args:
            url (str): The requested URL.
            company (str): The company the document is read for.
            filer (str): The SEC filer (10 digits).
            step (ScheduleStep): What the document is.

        Returns:
            Request: The request.
        """
        accept = "text/plain" if step is ScheduleStep.FILING else "application/json"
        meta: Dict[str, JsonValue] = {CompanyMeta.FILER.value: filer, CompanyMeta.STEP.value: step.value}
        return self._company_request(url, self._sec_headers(accept), company, meta)

    def _step(self, response: Response) -> Optional[ScheduleStep]:
        """Get what a document is.

        Args:
            response (Response): The document.

        Returns:
            Optional[ScheduleStep]: Its step, `None` when the request named none.
        """
        step = response.meta.get(CompanyMeta.STEP)
        return ScheduleStep(step) if step in {item.value for item in ScheduleStep} else None

    def _filer(self, response: Response) -> str:
        """Get the SEC filer a document was read for.

        Args:
            response (Response): The document.

        Returns:
            str: The filer, 10 digits, empty when the request named none.
        """
        filer = response.meta.get(CompanyMeta.FILER)
        return filer if isinstance(filer, str) else ""

    def _column(self, table: Dict[str, JsonValue], field: SubmissionsField) -> List[JsonValue]:
        """Get a column of the filings of a `submissions` document.

        Args:
            table (Dict[str, JsonValue]): The filings, by column.
            field (SubmissionsField): The column.

        Returns:
            List[JsonValue]: Its values, empty when missing.
        """
        values = table.get(field.value)
        return values if isinstance(values, list) else []

    def _filings(self, table: Dict[str, JsonValue]) -> Iterator[Filing]:
        """Get the reports of a filings table filed from 1993 to 2001.

        Args:
            table (Dict[str, JsonValue]): The filings, by column.

        Returns:
            Iterator[Filing]: The accession number, the form and the filing day of each report read.
        """
        accessions = self._column(table, SubmissionsField.ACCESSION)
        forms = self._column(table, SubmissionsField.FORM)
        days = self._column(table, SubmissionsField.FILING_DATE)
        for accession, form, raw_day in zip(accessions, forms, days, strict=False):
            if not (isinstance(accession, str) and isinstance(form, str) and isinstance(raw_day, str)):
                continue
            try:
                day = date.fromisoformat(raw_day)
            except ValueError:
                self.logger.warning("Filing %s has a malformed day %r: left out.", accession, raw_day)
                continue
            if form.startswith(self.FILINGS) and self.FIRST_DAY <= day <= self.LAST_DAY:
                yield accession, form, day

    def _pages(self, filings: Dict[str, JsonValue]) -> Iterator[str]:
        """Get the pages of older filings that may hold reports filed until 2001.

        Args:
            filings (Dict[str, JsonValue]): The `filings` part of a main `submissions` document.

        Returns:
            Iterator[str]: The document name of each page.
        """
        pages = filings.get(SubmissionsField.FILES.value)
        for page in pages if isinstance(pages, list) else []:
            entry = self._as_object(page)
            name = self._as_text(entry.get(SubmissionsField.NAME))
            first = self._as_text(entry.get(SubmissionsField.FILING_FROM)) or ""
            if name and first[:10] <= self.LAST_DAY.isoformat():
                yield name

    def _value(self, tag: ScheduleTag, raw: str, multiplier: float) -> Optional[float]:
        """Read the value of a mapped tag.

        Args:
            tag (ScheduleTag): The tag's definition.
            raw (str): Its raw value.
            multiplier (float): The schedule's multiplier.

        Returns:
            Optional[float]: The value, multiplied unless per share, `None` when not a number.
        """
        number = self._amount(raw)
        if number is None:
            return None
        return number if tag.per_share else number * multiplier

    def _currency(self, column: Dict[str, str]) -> Optional[str]:
        """Read the currency of a schedule column (US dollars when not stated).

        Args:
            column (Dict[str, str]): The column's raw values.

        Returns:
            Optional[str]: The currency, `None` when the schedule names one that is not known (logged).
        """
        raw = column.get(ScheduleHeader.CURRENCY.value)
        if not raw:
            return "USD"
        currency = self.CURRENCIES.get(" ".join(raw.upper().split()))
        if currency is None:
            self.logger.warning("Schedule currency %r is not known: the column is left out.", raw)
        return currency

    def _column_facts(
        self, response: Response, column: Dict[str, str], form: Optional[str], filed: Optional[date]
    ) -> Iterator[FinancialFact]:
        """Build the facts of a schedule column.

        Args:
            response (Response): The full text.
            column (Dict[str, str]): The column's raw values, by tag.
            form (Optional[str]): The form of the filing.
            filed (Optional[date]): The filing day.

        Returns:
            Iterator[FinancialFact]: A fact per mapped tag whose value is a number.
        """
        article = column.get(ScheduleHeader.ARTICLE.value, "").strip()
        if not article.isdigit() or int(article) not in self.concepts.fds.articles:
            self.logger.info("Schedule of article %r in %s left out (not read).", article, response.url)
            return
        end = self._day(column.get(ScheduleHeader.PERIOD_END.value))
        currency = self._currency(column)
        if end is None or currency is None:
            self.logger.warning("Schedule column of %s without period end or currency: left out.", response.url)
            return
        multiplier = self._amount(column.get(ScheduleHeader.MULTIPLIER.value, "1")) or 1.0
        start = self._day(column.get(ScheduleHeader.PERIOD_START.value))
        period = self.PERIODS.get(column.get(ScheduleHeader.PERIOD_TYPE.value, "").strip().upper())
        for raw_tag, raw in column.items():
            tag = self.concepts.fds.find(raw_tag)
            value = self._value(tag, raw, multiplier) if tag else None
            if tag is None or value is None:
                continue
            balance = self.concepts.nature(tag.metric) is FinancialNature.BALANCE
            try:
                yield FinancialFact(
                    company=self._company(response),
                    source=FinancialSource.EDGAR_FDS,
                    metric=tag.metric,
                    concept=f"fds:{tag.tag}",
                    filer=self._filer(response) or None,
                    start=None if balance else start,
                    end=end,
                    value=value,
                    currency=currency,
                    form=form,
                    fiscal_period=period,
                    filed=filed,
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid %s value in %s left out: %s", tag.tag, response.url, e.errors()[0]["msg"])

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the `submissions` document of every SEC filer of the companies read.

        Yields:
            Request: A request per filer.
        """
        if self._secret(self.companies.sec_user_agent_env) is None:
            self.logger.warning(
                "%s is not set: SEC EDGAR's archive refuses the full texts (it asks for a contact).",
                self.companies.sec_user_agent_env,
            )
        entries = [entry for entry in self.companies.entries(self.scope.companies) if entry.sec_ciks]
        self.logger.info("Requesting the SEC filings of %d companies for their data schedules.", len(entries))
        for entry in entries:
            for cik in entry.sec_ciks:
                self.logger.debug("Requesting the SEC filings of %s (filer %s).", entry.key, cik)
                url = self.SUBMISSIONS_URL.format(name=f"CIK{cik}.json")
                yield self._request(url, entry.key, cik, ScheduleStep.SUBMISSIONS)

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether SEC EDGAR refused a request: a missing document (HTTP 404) is not a refusal.

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
        """Extract the facts of the data schedules of a filing's full text (a `submissions` document has none).

        Args:
            response (Response): The document.

        Returns:
            Iterator[CompanyFact]: A financial fact per mapped value of an article 5 schedule.
        """
        if response.status != 200 or self._step(response) is not ScheduleStep.FILING:
            return
        text = self._body_text(response)
        header = self._schedule_header(text)
        filed = self._header_day(header.get(ScheduleHeader.FILED.value))
        form = header.get(ScheduleHeader.FORM.value)
        found = 0
        for column in self._schedule_columns(text):
            for fact in self._column_facts(response, column, form, filed):
                found += 1
                yield fact
        self.logger.debug("%d schedule facts of %s in %s.", found, self._company(response), response.url)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Request the pages of older filings and the full texts of the reports filed from 1993 to 2001.

        Args:
            response (Response): The document.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: The requests a `submissions` document or page leads to, none for a full text.

        Raises:
            CatalogueFormatError: If a `submissions` document is not JSON.
        """
        step = self._step(response)
        if response.status != 200 or step not in (ScheduleStep.SUBMISSIONS, ScheduleStep.SUBMISSIONS_PAGE):
            return
        company, filer = self._company(response), self._filer(response)
        document = self._as_object(self._json_body(response))
        table = document
        if step is ScheduleStep.SUBMISSIONS:
            filings = self._as_object(document.get(SubmissionsField.FILINGS))
            table = self._as_object(filings.get(SubmissionsField.RECENT))
            for page in self._pages(filings):
                self.logger.debug("Requesting the older filings page %s of %s.", page, company)
                yield self._request(
                    self.SUBMISSIONS_URL.format(name=page), company, filer, ScheduleStep.SUBMISSIONS_PAGE
                )
        reports = list(self._filings(table))
        self.logger.info(
            "%d reports of %s (filer %s) filed from 1993 to 2001 in %s.", len(reports), company, filer, response.url
        )
        for accession, _, _ in reports:
            url = self.FILING_URL.format(cik=int(filer), accession=accession)
            yield self._request(url, company, filer, ScheduleStep.FILING)
