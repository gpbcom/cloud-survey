from __future__ import annotations

# Standard Library Imports.
import csv
import io
import json
import os
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Pattern, Sequence, Tuple, Union
from urllib.parse import quote, quote_plus

# Third Party Imports.
from playwright.async_api import Page, Route
from pydantic import JsonValue, ValidationError
from scrapling.fetchers import AsyncDynamicSession
from scrapling.parser import Selector
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.enums import CompanyMeta
from crawler.companies.google_patents.enums import (
    CitationRow,
    PatentPageProperty,
    PatentsExportColumn,
    PatentsSearchField,
    PatentsStep,
)
from crawler.enums import HtmlAttribute
from crawler.exception import UnknownCrawlerTargetError
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed, PatentCitationKind, PatentWindowStatus
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.markets.crawl_scope import CrawlScope
from models.markets.markets_catalog import MarketsCatalog

type WindowKey = Tuple[str, str, date, date, Optional[str]]


class GooglePatentsCrawler(BaseCompanyCrawler):
    """Crawl the companies' patents on Google Patents: their assignees' publications, then each publication's page.

    Attributes:
        SEARCH_URL (ClassVar[str]): The search endpoint the Google Patents page calls.
        PAGE_URL (ClassVar[str]): The Google Patents search page, the one a person reads.
        XHR_PATTERN (ClassVar[str]): The requests of the search page read back (its searches and its export).
        DOWNLOAD_MARK (ClassVar[str]): The mark of an export among them.
        FETCH_SCRIPT (ClassVar[str]): The script the search page runs to export a window, as its Download link does.
        REFUSAL_CODES (ClassVar[Tuple[int, ...]]): The statuses Google refuses a client with.
        REFUSAL_MARKERS (ClassVar[Tuple[bytes, ...]]): The marks of the `Sorry` page refusing a client.
        COUNT_SIZE (ClassVar[int]): The results asked by a count (only the total is read).
        PUBLICATION_URL (ClassVar[str]): A publication page, formatted with the publication number.
        GRANTED_KINDS (ClassVar[Pattern[str]]): The kind codes of a granted patent (the US `B1`, `B2`, the EP `B1`).
        CITATION_KINDS (ClassVar[Dict[CitationRow, PatentCitationKind]]): The citation kind of each table of a page.
        SOURCES (ClassVar[Tuple[CompanyFeed, ...]]): The sources the crawler reads: the search, the pages.
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): Google Patents search, the default source.
        catalogue_url (ClassVar[str]): The Google Patents root.
        robots_txt_obey (bool): Off for the search (Google's `robots.txt` disallows `/xhr/`, read on the user's
            decision), on for the pages (`/patent/` is allowed).
        max_blocked_retries (int): No refused request is retried (a retry prolongs the refusal).
        browser (bool): Whether Google Patents is read in a visible browser (`patents.browser`).
        source (CompanyFeed): What this run reads: the search (`google-patents`) or the publication pages
            (`google-patents-pages`).
        queue (List[str]): The publications whose page to read, in their order (the storage picks them, the pages
            only).
        window_cap (int): The most publications a window may count to be read in one export.
        split_countries (List[str]): The patent offices a single day is split by.
        refresh_after (date): The windows ending after this day are searched again, even when stored complete.
        known (Dict[WindowKey, PatentWindow]): The stored windows, by company, search, dates and office.
        refusals (int): The refusals met in this run.
        assignees (Counter[Tuple[str, str]]): The publications of each assignee name the exports returned, by company.

    Notes:
        - A window is an assignee search over a span of priority dates (`dups=language`: one row per publication,
          each language version of a publication office being one). It is first counted (a JSON search asking 10
          results), then read in one CSV export when it counts at most the window cap, else halved, a single day
          being split by patent office. An export reading fewer rows than counted is halved again when it can be.
        - Google's `after:` and `before:` are asked one day wider on each side, so a window never misses its edge
          days whether Google reads them inclusive or not. The publications read twice are kept once.
        - Each window searched is streamed (`PatentWindow`), so the next run skips the complete ones (except the
          recent ones, searched again for the new publications) and resumes the others.
        - Google refuses a client after a few quick searches (HTTP 503, its `Sorry` page) for hours: the requests
          are paced, and the crawl stops at the refusal limit of the catalogue, its remaining windows left for the
          next run. Nothing is done to get around a refusal.
        - The assignee names returned are counted and logged at the end, to refine the searches of the catalogue
          (`analytics.companies` leaves out the homonyms its exclusion patterns name).
        - With `patents.browser` (the default), Google Patents is read in a visible Chromium window (plain
          Playwright, no stealth): a count opens the search page and reads the search it runs, an export opens it
          with that search blocked and runs the CSV export its Download link runs. Each still costs one search of
          Google, at the same pace.
        - A window spans priority dates `[after, before)`. It is halved at its middle day, so the halves of a window
          are always the same and a stored split window gives its halves without being counted again. A single day
          counting too many publications is split by patent office (the configured ones): what the other offices
          publish that day is then left out, and such a window is recorded incomplete.
        - The pages (`google-patents-pages`, robots-allowed) are read one per publication, in the order of the
          queue (one per family first, granted patents before applications, the most recent first), up to the page
          budget of the run (`CRAWLER_PATENT_PAGES`, else the catalogue's). A publication read is never read again.
          The citations are the rows of the page's tables (what it cites, what cites it, the same for its family,
          the examiner's marked), the rest the page's microdata (`itemprop`). A missing part is left empty.
    """

    SEARCH_URL: ClassVar[str] = "https://patents.google.com/xhr/query"
    REFUSAL_CODES: ClassVar[Tuple[int, ...]] = (429, 503)
    REFUSAL_MARKERS: ClassVar[Tuple[bytes, ...]] = (b"<title>Sorry...</title>", b"/sorry/index")
    COUNT_SIZE: ClassVar[int] = 10
    PAGE_URL: ClassVar[str] = "https://patents.google.com/"
    XHR_PATTERN: ClassVar[str] = r"/xhr/query"
    DOWNLOAD_MARK: ClassVar[str] = "download=true"
    FETCH_SCRIPT: ClassVar[str] = "url => fetch(url, {credentials: 'same-origin'}).then(answer => answer.text())"
    PUBLICATION_URL: ClassVar[str] = "https://patents.google.com/patent/{number}/en"
    GRANTED_KINDS: ClassVar[Pattern[str]] = re.compile(r"(?:B\d?|C\d?|E)$")
    CITATION_KINDS: ClassVar[Dict[CitationRow, PatentCitationKind]] = {
        CitationRow.CITES: PatentCitationKind.CITES,
        CitationRow.CITES_ORIGINAL: PatentCitationKind.CITES,
        CitationRow.CITED_BY: PatentCitationKind.CITED_BY,
        CitationRow.CITED_BY_ORIGINAL: PatentCitationKind.CITED_BY,
        CitationRow.FAMILY_CITES: PatentCitationKind.FAMILY_CITES,
        CitationRow.FAMILY_CITED_BY: PatentCitationKind.FAMILY_CITED_BY,
    }
    SOURCES: ClassVar[Tuple[CompanyFeed, ...]] = (CompanyFeed.GOOGLE_PATENTS, CompanyFeed.GOOGLE_PATENT_PAGES)
    name = "google-patents"
    feed: ClassVar[CompanyFeed] = CompanyFeed.GOOGLE_PATENTS
    catalogue_url: ClassVar[str] = "https://patents.google.com/"
    robots_txt_obey: bool = False
    max_blocked_retries: int = 0

    def __init__(
        self,
        companies: Optional[CompaniesCatalog] = None,
        concepts: Optional[FinancialConcepts] = None,
        markets: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        known: Optional[Sequence[PatentWindow]] = None,
        queue: Optional[Sequence[str]] = None,
        source: CompanyFeed = CompanyFeed.GOOGLE_PATENTS,
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
            known (Optional[Sequence[PatentWindow]]): The windows stored by the former runs, none by default (the
                search only).
            queue (Optional[Sequence[str]]): The publications whose page to read, in their order, none by default
                (the pages only).
            source (CompanyFeed): The search (`google-patents`, the default) or the pages (`google-patents-pages`).
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            UnknownCrawlerTargetError: If the source is not a Google Patents one.
            CompaniesCatalogError: If a default catalogue cannot be loaded.
            MarketsCatalogError: If the default markets catalogue cannot be loaded.
        """
        super().__init__(
            companies=companies, concepts=concepts, markets=markets, scope=scope, crawldir=crawldir, interval=interval
        )
        if source not in self.SOURCES:
            self.logger.error("Google Patents does not read the source %s.", source.value)
            raise UnknownCrawlerTargetError(source.value)
        settings = self.companies.patents
        self.download_delay = settings.delay_seconds
        self.source = source
        self.robots_txt_obey = source is CompanyFeed.GOOGLE_PATENT_PAGES
        self.queue = list(queue or ())
        self.window_cap = settings.window_cap
        self.split_countries = list(settings.split_countries)
        self.refresh_after = self._today() - timedelta(days=365 * settings.refresh_years)
        self.known: Dict[WindowKey, PatentWindow] = {self._key(window): window for window in known or ()}
        self.refusals = 0
        self.assignees: Counter[Tuple[str, str]] = Counter()
        self.browser = settings.browser
        self.logger.debug(
            "Google Patents %s ready: cap %d, %d stored windows, %d pages queued.",
            source.value,
            self.window_cap,
            len(self.known),
            len(self.queue),
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _today(self) -> date:
        """Get today's date.

        Returns:
            date: Today, in UTC.
        """
        return datetime.now(UTC).date()

    def _key(self, window: PatentWindow) -> WindowKey:
        """Get the key of a window.

        Args:
            window (PatentWindow): The window.

        Returns:
            WindowKey: Its company, search, dates and office.
        """
        return window.company, window.query, window.after, window.before, window.country

    def _children(self, window: PatentWindow) -> List[PatentWindow]:
        """Split a window: its two halves, or a single day by patent office.

        Args:
            window (PatentWindow): The window counting too many publications.

        Returns:
            List[PatentWindow]: The windows replacing it, none when it cannot be split (one day of one office).
        """
        base = {"company": window.company, "query": window.query, "expected": 0}
        if window.days() > 1:
            middle = window.after + timedelta(days=window.days() // 2)
            return [
                PatentWindow(**base, after=window.after, before=middle, country=window.country),
                PatentWindow(**base, after=middle, before=window.before, country=window.country),
            ]
        if window.country is None:
            return [
                PatentWindow(**base, after=window.after, before=window.before, country=country)
                for country in self.split_countries
            ]
        return []

    def _can_split(self, window: PatentWindow) -> bool:
        """Tell whether a window can be split.

        Args:
            window (PatentWindow): The window.

        Returns:
            bool: Whether it spans several days, or is a single day of every office.
        """
        return window.days() > 1 or (window.country is None and bool(self.split_countries))

    def _plan(self, windows: Sequence[PatentWindow]) -> List[PatentWindow]:
        """Get the windows to count: a stored split one replaced by its halves, a stored complete one left out.

        Args:
            windows (Sequence[PatentWindow]): The windows to search.

        Returns:
            List[PatentWindow]: The windows to count, in date order.

        Notes:
            A stored complete window ending after the refresh day
            is counted again (new publications appear for
            about 18 months after their priority date).
        """
        planned: List[PatentWindow] = []
        stack = list(reversed(windows))
        skipped = 0
        while stack:
            window = stack.pop()
            stored = self.known.get(self._key(window))
            if stored is not None and stored.status is PatentWindowStatus.SPLIT:
                stack.extend(reversed(self._children(window)))
            elif (
                stored is not None
                and stored.status is PatentWindowStatus.COMPLETE
                and window.before <= self.refresh_after
            ):
                skipped += 1
            else:
                planned.append(window)
        self.logger.debug("%d windows to count, %d stored complete windows skipped.", len(planned), skipped)
        return planned

    def _browser_id(self) -> str:
        """Get the identifier of the visible browser session.

        Returns:
            str: The session identifier, `google-patents-chromium`.
        """
        return f"{self.name}-chromium"

    def _terms(self, window: PatentWindow) -> str:
        """Write the search terms of a window, as the search page puts them in its address.

        Args:
            window (PatentWindow): The window.

        Returns:
            str: The terms, e.g. `assignee=Nvidia+Corp&after=priority:20181231&before=priority:20190201&dups=language`.
        """
        after = (window.after - timedelta(days=1)).strftime("%Y%m%d")
        before = window.before.strftime("%Y%m%d")
        terms = f"assignee={quote_plus(window.query)}&after=priority:{after}&before=priority:{before}&dups=language"
        return f"{terms}&country={window.country}" if window.country else terms

    async def _only_exports(self, route: Route) -> None:
        """Let the export through and block the search the page runs by itself (it would cost a search).

        Args:
            route (Route): The request of the page.
        """
        if self.DOWNLOAD_MARK in route.request.url:
            await route.continue_()
        else:
            await route.abort()

    async def _block_search(self, page: Page) -> None:
        """Block the search the page runs by itself before it opens (an export only).

        Args:
            page (Page): The browser page.
        """
        await page.route(f"**{self.XHR_PATTERN}*", self._only_exports)

    async def _export(self, url: str, page: Page) -> None:
        """Run the CSV export of a window in the page, as its Download link does.

        Args:
            url (str): The export URL.
            page (Page): The browser page.
        """
        await page.evaluate(self.FETCH_SCRIPT, url)

    def _search_url(self, window: PatentWindow, step: PatentsStep) -> str:
        """Build the search URL of a window: the search terms are themselves a query, encoded in `url=`.

        Args:
            window (PatentWindow): The window.
            step (PatentsStep): A count (JSON, 10 results) or an export (CSV).

        Returns:
            str: The URL.
        """
        terms = self._terms(window)
        if step is PatentsStep.COUNT:
            return f"{self.SEARCH_URL}?url={quote(terms + f'&num={self.COUNT_SIZE}', safe='')}&exp="
        return f"{self.SEARCH_URL}?url={quote(terms, safe='')}&exp=&download=true"

    def _window_request(self, window: PatentWindow, step: PatentsStep, expected: int = 0) -> Request:
        """Build the request counting or exporting a window.

        Args:
            window (PatentWindow): The window.
            step (PatentsStep): A count or an export.
            expected (int): The publications the count found (an export only).

        Returns:
            Request: The request, the window in its meta: an HTTP request, or the search page in the visible browser
                (`patents.browser`).
        """
        meta: Dict[str, JsonValue] = {
            CompanyMeta.QUERY.value: window.query,
            CompanyMeta.AFTER.value: window.after.isoformat(),
            CompanyMeta.BEFORE.value: window.before.isoformat(),
            CompanyMeta.COUNTRY.value: window.country or "",
            CompanyMeta.STEP.value: step.value,
            CompanyMeta.EXPECTED.value: expected,
        }
        if not self.browser:
            accept = "application/json" if step is PatentsStep.COUNT else "text/csv"
            return self._company_request(self._search_url(window, step), self._headers(accept), window.company, meta)
        page = f"{self.PAGE_URL}?{self._terms(window)}&num={self.COUNT_SIZE}"
        browser_meta: Dict[str, JsonValue] = {CompanyMeta.COMPANY.value: window.company, **meta}
        if step is PatentsStep.COUNT:
            return Request(
                page, sid=self._browser_id(), priority=self.PRIMARY_PRIORITY, meta=browser_meta, dont_filter=True
            )
        export = self._search_url(window, step)
        return Request(
            page,
            sid=self._browser_id(),
            priority=self.PRIMARY_PRIORITY,
            meta=browser_meta,
            dont_filter=True,
            page_setup=self._block_search,
            page_action=lambda opened: self._export(export, opened),
        )

    def _payload(self, response: Response, step: PatentsStep) -> str:
        """Read the answer of a count or an export: the body of an HTTP request, or the search the page ran.

        Args:
            response (Response): The response.
            step (PatentsStep): A count or an export.

        Returns:
            str: The JSON search or the CSV export, as text (the page itself when nothing was captured).
        """
        export = step is PatentsStep.EXPORT
        for captured in response.captured_xhr:
            if (self.DOWNLOAD_MARK in captured.url) == export:
                return self._body_text(captured)
        return self._body_text(response)

    def _window(self, response: Response) -> Optional[PatentWindow]:
        """Read back the window of a response.

        Args:
            response (Response): The response.

        Returns:
            Optional[PatentWindow]: The window, `None` when the request named none.
        """
        meta = response.meta
        try:
            return PatentWindow(
                company=self._company(response),
                query=meta.get(CompanyMeta.QUERY),
                after=meta.get(CompanyMeta.AFTER),
                before=meta.get(CompanyMeta.BEFORE),
                country=meta.get(CompanyMeta.COUNTRY) or None,
                expected=meta.get(CompanyMeta.EXPECTED, 0),
            )
        except ValidationError as e:
            self.logger.warning("No window in the request of %s: %s", response.url, e.errors()[0]["msg"])
            return None

    def _total(self, response: Response) -> Optional[int]:
        """Read the number of publications of a count.

        Args:
            response (Response): The JSON search answer.

        Returns:
            Optional[int]: The total, `None` when the answer is not a search answer.
        """
        try:
            document = json.loads(self._payload(response, PatentsStep.COUNT))
        except ValueError:
            self.logger.warning("The Google Patents count %s is not JSON.", response.url)
            return None
        results = self._as_object(self._as_object(document).get(PatentsSearchField.RESULTS))
        total = results.get(PatentsSearchField.TOTAL)
        return total if isinstance(total, int) and not isinstance(total, bool) else None

    def _rows(self, response: Response) -> List[Dict[str, str]]:
        """Read the rows of a CSV export, keyed by the column names of its second line.

        Args:
            response (Response): The CSV export.

        Returns:
            List[Dict[str, str]]: The rows (the first line, the search URL, and the header are left out).
        """
        lines = list(csv.reader(io.StringIO(self._payload(response, PatentsStep.EXPORT))))
        header = next((index for index, line in enumerate(lines[:3]) if PatentsExportColumn.LINK in line), None)
        if header is None:
            self.logger.warning("The Google Patents export %s has no header line.", response.url)
            return []
        columns = lines[header]
        return [dict(zip(columns, line, strict=False)) for line in lines[header + 1 :] if line]

    def _record(self, window: PatentWindow, row: Dict[str, str]) -> Optional[PatentRecord]:
        """Build the record of an export row.

        Args:
            window (PatentWindow): The window exported.
            row (Dict[str, str]): The row.

        Returns:
            Optional[PatentRecord]: The publication, `None` when the row is not valid (logged).
        """
        link = row.get(PatentsExportColumn.LINK, "")
        number = (
            link.split("/patent/", 1)[1].split("/", 1)[0] if "/patent/" in link else row.get(PatentsExportColumn.ID, "")
        )
        try:
            return PatentRecord(
                company=window.company,
                query=window.query,
                publication_number=number,
                title=row.get(PatentsExportColumn.TITLE),
                assignee=row.get(PatentsExportColumn.ASSIGNEE),
                inventors=row.get(PatentsExportColumn.INVENTORS, ""),
                priority_date=row.get(PatentsExportColumn.PRIORITY),
                filing_date=row.get(PatentsExportColumn.FILING),
                publication_date=row.get(PatentsExportColumn.PUBLICATION),
                grant_date=row.get(PatentsExportColumn.GRANT),
                source_url=link or f"https://patents.google.com/patent/{number}/en",
            )
        except ValidationError as e:
            self.logger.warning("Invalid export row %s left out: %s", number, e.errors()[0]["msg"])
            return None

    def _settled(self, window: PatentWindow, status: PatentWindowStatus, expected: int, fetched: int) -> PatentWindow:
        """Get a window with what its search found.

        Args:
            window (PatentWindow): The window.
            status (PatentWindowStatus): Its state.
            expected (int): The publications counted.
            fetched (int): The publications read.

        Returns:
            PatentWindow: The window, settled.
        """
        return window.model_copy(update={"status": status, "expected": expected, "fetched": fetched})

    def _counted(self, response: Response, window: PatentWindow) -> Iterator[CompanyFact]:
        """Handle a count: settle an empty window, or a window too large to be exported (its halves follow).

        Args:
            response (Response): The count.
            window (PatentWindow): The window counted.

        Returns:
            Iterator[CompanyFact]: The settled window when it is empty or split, nothing when it is exported next.
        """
        total = self._total(response)
        if total is None:
            return
        self.logger.debug(
            "%s %s %s..%s %s: %d publications.",
            window.company,
            window.query,
            window.after,
            window.before,
            window.country or "",
            total,
        )
        if total == 0:
            yield self._settled(window, PatentWindowStatus.COMPLETE, 0, 0)
        elif total > self.window_cap and self._can_split(window):
            yield self._settled(window, PatentWindowStatus.SPLIT, total, 0)

    def _exported(self, response: Response, window: PatentWindow) -> Iterator[CompanyFact]:
        """Handle an export: stream its publications, then the window settled.

        Args:
            response (Response): The CSV export.
            window (PatentWindow): The window exported (its count in `expected`).

        Returns:
            Iterator[CompanyFact]: The publications, then the window.
        """
        seen: Dict[str, PatentRecord] = {}
        for row in self._rows(response):
            record = self._record(window, row)
            if record is not None:
                seen.setdefault(record.publication_number, record)
        for record in seen.values():
            self.assignees[(window.company, record.assignee or "?")] += 1
        yield from seen.values()
        fetched, expected = len(seen), window.expected
        if fetched >= expected:
            yield self._settled(window, PatentWindowStatus.COMPLETE, expected, fetched)
        elif self._can_split(window):
            self.logger.info(
                "%s %s..%s: the export read %d of %d publications, halving it.",
                window.company,
                window.after,
                window.before,
                fetched,
                expected,
            )
            yield self._settled(window, PatentWindowStatus.SPLIT, expected, fetched)
        else:
            self.logger.warning(
                "%s %s %s %s: only %d of %d publications read.",
                window.company,
                window.query,
                window.after,
                window.country or "",
                fetched,
                expected,
            )
            yield self._settled(window, PatentWindowStatus.INCOMPLETE, expected, fetched)

    def _texts(self, scope: Selector, selector: str) -> List[str]:
        """Read the texts of the elements of a selector.

        Args:
            scope (Selector): Where they are searched.
            selector (str): The CSS selector.

        Returns:
            List[str]: Their texts, spaces collapsed, blanks left out, each once.
        """
        texts = [
            self._clean_text(str(element.get_all_text(separator=" ", strip=True))) for element in scope.css(selector)
        ]
        return [*dict.fromkeys(text for text in texts if text)]

    def _first(self, scope: Selector, selector: str) -> Optional[str]:
        """Read the first element of a selector: its `datetime` or `content` attribute, else its text.

        Args:
            scope (Selector): Where it is searched.
            selector (str): The CSS selector.

        Returns:
            Optional[str]: The value, `None` when no element matches or it is blank.
        """
        element = scope.css(selector).first
        if element is None:
            return None
        value = element.attrib.get(HtmlAttribute.DATETIME) or element.attrib.get(HtmlAttribute.CONTENT)
        text = self._clean_text(str(value) if value else str(element.get_all_text(separator=" ", strip=True)))
        return text or None

    def _cpc(self, response: Response) -> List[str]:
        """Read the CPC classes: the most specific code of each classification path (an entry holding no nested one).

        Args:
            response (Response): The publication page.

        Returns:
            List[str]: The codes, each once.
        """
        codes: List[str] = []
        for item in response.css(f'[itemprop="{PatentPageProperty.CLASSIFICATIONS}"]'):
            leaf = item.css(f'meta[itemprop="{PatentPageProperty.LEAF}"]').first
            nested = item.css(f'[itemprop="{PatentPageProperty.CLASSIFICATIONS}"]')  # the entry itself included
            code = item.css(f'[itemprop="{PatentPageProperty.CODE}"]').first
            if leaf is None or code is None or len(nested) > 1:
                continue
            text = self._clean_text(str(code.get_all_text(strip=True))).replace(" ", "")
            if text and text not in codes:
                codes.append(text)
        return codes

    def _citations(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the rows of the citation tables.

        Args:
            response (Response): The publication page.

        Returns:
            List[Dict[str, JsonValue]]: A citation per row, each other publication once per kind.
        """
        citations: Dict[Tuple[str, str], Dict[str, JsonValue]] = {}
        for table, kind in self.CITATION_KINDS.items():
            for row in response.css(f'tr[itemprop="{table}"]'):
                number = self._first(row, f'[itemprop="{PatentPageProperty.PUBLICATION_NUMBER}"]')
                if number is None:
                    continue
                assignees = self._texts(row, f'[itemprop="{PatentPageProperty.ASSIGNEE_ORIGINAL}"]')
                citations.setdefault(
                    (number, kind.value),
                    {
                        "publication_number": number,
                        "kind": kind.value,
                        "examiner": bool(row.css(f'[itemprop="{PatentPageProperty.EXAMINER_CITED}"]')),
                        "priority_date": self._first(row, f'[itemprop="{PatentPageProperty.PRIORITY_DATE}"]'),
                        "publication_date": self._first(row, f'[itemprop="{PatentPageProperty.PUBLICATION_DATE}"]'),
                        "assignee": assignees[0] if assignees else None,
                        "title": self._first(row, f'[itemprop="{PatentPageProperty.TITLE}"]'),
                    },
                )
        return list(citations.values())

    def _grant_date(self, response: Response, number: str, published: Optional[str]) -> Optional[str]:
        """Find the grant date: the legal event of the grant, else the publication date of a granted kind code.

        Args:
            response (Response): The publication page.
            number (str): The publication.
            published (Optional[str]): Its publication date.

        Returns:
            Optional[str]: The grant date, `None` for an application.
        """
        for event in response.css(f'[itemprop="{PatentPageProperty.EVENTS}"]'):
            kind = self._first(event, f'[itemprop="{PatentPageProperty.TYPE}"]') or ""
            if "grant" in kind.casefold():
                return self._first(event, f'[itemprop="{PatentPageProperty.DATE}"]')
        return published if self.GRANTED_KINDS.search(number) else None

    def _claims(self, response: Response) -> Optional[int]:
        """Read the number of claims of the claims section's heading.

        Args:
            response (Response): The publication page.

        Returns:
            Optional[int]: The number, `None` when not stated.
        """
        count = self._first(
            response, f'[itemprop="{PatentPageProperty.CLAIMS}"] [itemprop="{PatentPageProperty.COUNT}"]'
        )
        return int(count) if count and count.isdigit() else None

    def _page_request(self, number: str) -> Request:
        """Build the request of a publication page: an HTTP request, or the page in the visible browser.

        Args:
            number (str): The publication.

        Returns:
            Request: The request, the publication in its meta.
        """
        url = self.PUBLICATION_URL.format(number=number)
        meta: Dict[str, JsonValue] = {CompanyMeta.PUBLICATION.value: number}
        if not self.browser:
            return self._company_request(url, self._headers("text/html"), "", meta)
        return Request(
            url,
            sid=self._browser_id(),
            priority=self.PRIMARY_PRIORITY,
            meta={CompanyMeta.COMPANY.value: "", **meta},
            dont_filter=True,
        )

    def _page_requests(self) -> List[Request]:
        """Build the requests of the publication pages of the queue, up to the page budget of the run.

        Returns:
            List[Request]: A request per publication, in the order of the queue.
        """
        settings = self.companies.patents
        raw = (os.getenv(settings.page_budget_env) or "").strip()
        budget = int(raw) if raw.isdigit() else settings.page_budget
        pages = self.queue[:budget]
        self.logger.info("Reading %d publication pages (budget %d, %d waiting).", len(pages), budget, len(self.queue))
        return [self._page_request(number) for number in pages]

    def _detail(self, response: Response) -> Iterator[CompanyFact]:
        """Extract what a publication page states.

        Args:
            response (Response): The publication page.

        Returns:
            Iterator[CompanyFact]: The publication's detail.
        """
        number = str(response.meta.get(CompanyMeta.PUBLICATION, ""))
        if response.status != 200:
            self.logger.warning("No page for the publication %s (HTTP %s).", number, response.status)
            return
        published = self._first(response, f'time[itemprop="{PatentPageProperty.PUBLICATION_DATE}"]')
        title = self._first(
            response, f'h1 [itemprop="{PatentPageProperty.TITLE}"], span[itemprop="{PatentPageProperty.TITLE}"]'
        )
        abstract = self._first(response, f'section[itemprop="{PatentPageProperty.ABSTRACT}"] div.abstract')
        try:
            detail = PatentDetail(
                publication_number=number,
                family_id=self._first(response, f'[itemprop="{PatentPageProperty.FAMILY_ID}"]'),
                title=title,
                abstract=abstract,
                assignees_original=self._texts(response, f'dd[itemprop="{PatentPageProperty.ASSIGNEE_ORIGINAL}"]'),
                assignees_current=self._texts(response, f'dd[itemprop="{PatentPageProperty.ASSIGNEE_CURRENT}"]'),
                inventors=self._texts(response, f'dd[itemprop="{PatentPageProperty.INVENTOR}"]'),
                cpc=self._cpc(response),
                claims=self._claims(response),
                priority_date=self._first(response, f'time[itemprop="{PatentPageProperty.PRIORITY_DATE}"]'),
                filing_date=self._first(response, f'time[itemprop="{PatentPageProperty.FILING_DATE}"]'),
                publication_date=published,
                grant_date=self._grant_date(response, number, published),
                citations=self._citations(response),
                source_url=response.url,
            )
        except ValidationError as e:
            self.logger.warning("The page of %s did not validate: %s", number, e.errors()[0]["msg"])
            return
        self.logger.debug(
            "%s: family %s, %d citations, %d classes.", number, detail.family_id, len(detail.citations), len(detail.cpc)
        )
        yield detail

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the HTTP session and the visible Chromium session.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.

        Notes:
            Scrapling configures the sessions before the catalogue is read: the browser session is always added,
            and only starts with its first request (with `patents.browser`, never otherwise).
        """
        super().configure_sessions(manager)
        self.logger.debug("Configuring the visible Chromium session %s.", self._browser_id())
        manager.add(
            self._browser_id(),
            AsyncDynamicSession(
                headless=False,
                capture_xhr=self.XHR_PATTERN,
                network_idle=True,
                timeout=120000,
                wait=1000,
                retries=1,
            ),
            lazy=True,
        )

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Count the windows of every assignee search of the companies read, or request the pages of the queue.

        Yields:
            Request: A count per window to search (the stored complete ones skipped), or a request per publication
                page (the pages source).
        """
        if self.source is CompanyFeed.GOOGLE_PATENT_PAGES:
            for request in self._page_requests():
                yield request
            return
        tomorrow = self._today() + timedelta(days=1)
        roots = [
            PatentWindow(company=entry.key, query=query, after=entry.patents.since, before=tomorrow, expected=0)
            for entry in self.companies.entries(self.scope.companies)
            if entry.patents is not None
            for query in entry.patents.assignees
        ]
        windows = self._plan(roots)
        self.logger.info(
            "Searching Google Patents: %d assignee searches, %d windows to count.", len(roots), len(windows)
        )
        for window in windows:
            yield self._window_request(window, PatentsStep.COUNT)

    async def is_blocked(self, response: Response) -> bool:
        """Tell whether Google refused the request, and stop the crawl at the refusal limit.

        Args:
            response (Response): The response.

        Returns:
            bool: Whether it is a refusal (never retried). A missing page (HTTP 404) is not one.
        """
        answers = [response, *response.captured_xhr]
        refused = "/sorry/" in response.url or any(
            answer.status in self.REFUSAL_CODES or any(marker in answer.body[:4000] for marker in self.REFUSAL_MARKERS)
            for answer in answers
        )
        if not refused:
            return await super().is_blocked(response)
        self.refusals += 1
        limit = self.companies.patents.max_blocks
        self.logger.warning(
            "Google Patents refused %s (HTTP %s), refusal %d of %d.",
            response.url,
            response.status,
            self.refusals,
            limit,
        )
        if self.refusals >= limit:
            pages = self.source is CompanyFeed.GOOGLE_PATENT_PAGES
            left = "publications" if pages else "windows"
            self.logger.warning(
                "Google Patents refuses the requests: stopping, the other %s are left for the next run.", left
            )
            self.refusal = (
                f"Google Patents refused the {'publication pages' if pages else 'search'} (HTTP {response.status}): "
                "what was read is kept and the next search resumes from it, once Google lifts the refusal (usually "
                "within an hour)"
            )
            self.pause()
        return True

    async def on_close(self) -> None:
        """Log the assignee names the searches returned, the way to refine the searches of the catalogue."""
        await super().on_close()
        for company in sorted({company for company, _ in self.assignees}):
            names = sorted(
                ((count, name) for (key, name), count in self.assignees.items() if key == company), reverse=True
            )
            self.logger.info(
                "%s assignees returned: %s", company, ", ".join(f"{name} ({count})" for count, name in names[:15])
            )

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the facts of a count (a settled window), an export (its publications, then the window) or a page.

        Args:
            response (Response): The count, the export or the publication page.

        Returns:
            Iterator[CompanyFact]: The publications and the settled windows, or the detail of a publication.
        """
        if response.meta.get(CompanyMeta.PUBLICATION):
            yield from self._detail(response)
            return
        window = self._window(response)
        if window is None:
            return
        if response.meta.get(CompanyMeta.STEP) == PatentsStep.EXPORT:
            yield from self._exported(response, window)
        else:
            yield from self._counted(response, window)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Export a window counted small enough, or count the halves of a window too large.

        Args:
            response (Response): The count, the export or the publication page.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: The export of the window, or the counts of its halves, or nothing (a page has no
                follow-up).
        """
        if response.meta.get(CompanyMeta.PUBLICATION):
            return iter(())
        window = self._window(response)
        if window is None:
            return iter(())
        step = response.meta.get(CompanyMeta.STEP)
        if step == PatentsStep.EXPORT:
            fetched = found - 1
            if fetched >= window.expected or not self._can_split(window):
                return iter(())
            return iter(self._window_request(child, PatentsStep.COUNT) for child in self._plan(self._children(window)))
        total = self._total(response)
        if total is None or total == 0:
            return iter(())
        if total > self.window_cap and self._can_split(window):
            children = self._plan(self._children(window))
            return iter(self._window_request(child, PatentsStep.COUNT) for child in children)
        return iter((self._window_request(window, PatentsStep.EXPORT, expected=total),))
