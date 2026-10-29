from __future__ import annotations

# Standard Library Imports.
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Pattern, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.companies.base import BaseCompanyCrawler, CompanyFact
from crawler.companies.enums import CompanyMeta
from crawler.markets.google_finance.enums import BatchExecuteField, GoogleFinanceHeader
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed, FinancialGranularity, FinancialMetric, FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.markets.crawl_scope import CrawlScope
from models.markets.listings.stock_listing import StockListing
from models.markets.markets_catalog import MarketsCatalog

type Statement = Tuple[int, Optional[int], List[JsonValue]]


class GoogleFinanceStatementsCrawler(BaseCompanyCrawler):
    """Crawl the income statement, balance sheet and cash flow of the listed companies from Google Finance.

    Attributes:
        BASE_URL (ClassVar[str]): The Google Finance root.
        BLOCK (ClassVar[Pattern[str]]): The start of a data block the quote page embeds (`AF_initDataCallback`).
        SHARE_COUNTS (ClassVar[Tuple[FinancialMetric, ...]]): The statement lines counting shares (no currency).
        name (str): The crawler name.
        feed (ClassVar[CompanyFeed]): Google Finance statements.
        catalogue_url (ClassVar[str]): The Google Finance root.
        download_delay (float): Two seconds between two quote pages, as the price crawler paces them.

    Notes:
        - One quote page per company (its valued listing: the primary one, or the one the catalogue names) embeds
          the statements of the last 10 fiscal years and 8 quarters, each period a list of 106 values whose
          positions are pinned in the `concepts` block of `conf/settings.yaml`. The blocks are told apart by their
          shape, never by their `ds:N` key, which Google renumbers between pages.
        - A period is `[year, quarter, values, …]` or `[year, values, …]`. The cash flows of a quarter are the
          quarter's own, the balances those at the period end, the amounts in the reporting currency (slot 16).
        - The quote row adds the market capitalisation of the day, in the trading currency.
        - The history of the statements grows run after run: a period read once is kept when Google drops it.
        - A `consent.google.com` landing means the consent cookies of the markets catalogue were refused.
          No proxy is used, and `robots.txt` allows `/finance/`.
    """

    BASE_URL: ClassVar[str] = "https://www.google.com/finance"
    BLOCK: ClassVar[Pattern[str]] = re.compile(r"AF_initDataCallback\(\{key:\s*'ds:\d+'.*?data:", re.DOTALL)
    SHARE_COUNTS: ClassVar[Tuple[FinancialMetric, ...]] = (FinancialMetric.SHARES_OUTSTANDING,)
    name = "gfinance-statements"
    feed: ClassVar[CompanyFeed] = CompanyFeed.GOOGLE_FINANCE
    catalogue_url: ClassVar[str] = "https://www.google.com/finance/"
    download_delay: float = 2.0

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

    def _valued_listing(self, entry: CompanyEntry) -> Optional[StockListing]:
        """Get the listing a company is valued on: the one the catalogue names, else its primary listing.

        Args:
            entry (CompanyEntry): The company.

        Returns:
            Optional[StockListing]: The listing, `None` when the company is not listed.
        """
        if entry.market_cap is not None:
            listing = self.markets.listing(entry.market_cap.listing)
            if listing is None:
                self.logger.warning(
                    "The valued listing %s of %s is not in the markets catalogue.", entry.market_cap.listing, entry.key
                )
            return listing
        listings = self.markets.listings_of(entry.key)
        return listings[0] if listings else None

    def _quote_request(self, company: str, listing: StockListing, candidate: int) -> Optional[Request]:
        """Build the quote page request of a listing under one of its Google exchange codes.

        Args:
            company (str): The company.
            listing (StockListing): The listing.
            candidate (int): The index of the exchange code tried.

        Returns:
            Optional[Request]: The request, `None` when every code was tried.
        """
        candidates = listing.google_candidates()
        if candidate >= len(candidates):
            return None
        ticker, exchange = candidates[candidate]
        cookies = "; ".join(f"{key}={value}" for key, value in self.markets.google_finance.consent_cookies.items())
        headers = self._headers("text/html")
        headers[GoogleFinanceHeader.COOKIE.value] = cookies
        return self._company_request(
            f"{self.BASE_URL}/quote/{ticker}:{exchange}?hl=en",
            headers,
            company,
            {CompanyMeta.LISTING.value: listing.symbol, CompanyMeta.CANDIDATE.value: candidate},
        )

    def _balanced_array(self, text: str, start: int) -> Optional[str]:
        """Cut the JSON array starting at a position, its brackets balanced and its strings respected.

        Args:
            text (str): The page.
            start (int): The position of the opening bracket.

        Returns:
            Optional[str]: The array text, `None` when the brackets never balance.
        """
        depth, inside, escaped = 0, False, False
        for index in range(start, len(text)):
            character = text[index]
            if inside:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    inside = False
                continue
            if character == '"':
                inside = True
            elif character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def _blocks(self, html: str) -> List[JsonValue]:
        """Decode the data blocks the quote page embeds.

        Args:
            html (str): The page.

        Returns:
            List[JsonValue]: The decoded blocks, in page order. A block that does not decode is left out.
        """
        blocks: List[JsonValue] = []
        for match in self.BLOCK.finditer(html):
            start = match.end()
            while start < len(html) and html[start] in " \n\r\t":
                start += 1
            array = self._balanced_array(html, start) if start < len(html) and html[start] == "[" else None
            if array is None:
                continue
            try:
                blocks.append(json.loads(array))
            except ValueError as e:
                self.logger.debug("Undecodable quote page block: %s", e)
        return blocks

    def _lists(self, root: JsonValue) -> Iterator[List[JsonValue]]:
        """Walk every list nested under a value, the value first.

        Args:
            root (JsonValue): The value.

        Returns:
            Iterator[List[JsonValue]]: The lists, depth first.
        """
        stack: List[JsonValue] = [root]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                yield node
                stack.extend(reversed(node))

    def _is_number(self, value: JsonValue) -> bool:
        """Tell whether a value is a number (a boolean is not).

        Args:
            value (JsonValue): The value.

        Returns:
            bool: Whether it is an int or a float.
        """
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _day(self, value: JsonValue) -> Optional[date]:
        """Read Google's `[year, month, day]` date.

        Args:
            value (JsonValue): The value.

        Returns:
            Optional[date]: The day, `None` when the value is not a plausible date.
        """
        if not isinstance(value, list) or len(value) < 3 or not all(isinstance(part, int) for part in value[:3]):
            return None
        try:
            year, month, day = int(str(value[0])), int(str(value[1])), int(str(value[2]))
            return date(year, month, day) if 1900 < year < 2200 else None
        except ValueError:
            return None

    def _is_values(self, value: JsonValue) -> bool:
        """Tell whether a value is the value list of a period: wide enough, a currency and a last day in their slots.

        Args:
            value (JsonValue): The value.

        Returns:
            bool: Whether it is a period's value list.
        """
        layout = self.concepts.google_finance
        if not isinstance(value, list) or len(value) < layout.width:
            return False
        currency = value[layout.currency_slot]
        return isinstance(currency, str) and len(currency) == 3 and self._day(value[layout.period_end_slot]) is not None

    def _statement(self, node: List[JsonValue]) -> Optional[Statement]:
        """Read a period: `[year, quarter, values, …]` (a quarter) or `[year, values, …]` (a year).

        Args:
            node (List[JsonValue]): A list of a block.

        Returns:
            Optional[Statement]: The fiscal year, the quarter (`None` for a year) and the values, `None` otherwise.
        """
        if len(node) >= 3 and isinstance(node[0], int) and isinstance(node[1], int) and self._is_values(node[2]):
            values = node[2]
            return (node[0], node[1], values) if isinstance(values, list) else None
        if len(node) >= 2 and isinstance(node[0], int) and self._is_values(node[1]):
            values = node[1]
            return (node[0], None, values) if isinstance(values, list) else None
        return None

    def _statements(self, blocks: List[JsonValue]) -> List[Statement]:
        """Find every period of the statements, each once.

        Args:
            blocks (List[JsonValue]): The decoded blocks.

        Returns:
            List[Statement]: The periods (years and quarters).
        """
        end_slot = self.concepts.google_finance.period_end_slot
        found: Dict[Tuple[bool, Optional[date]], Statement] = {}
        for block in blocks:
            for node in self._lists(block):
                statement = self._statement(node)
                if statement is not None:
                    key = (statement[1] is None, self._day(statement[2][end_slot]))
                    found.setdefault(key, statement)
        return list(found.values())

    def _market_cap(self, blocks: List[JsonValue], ticker: str, exchange: str) -> Optional[Tuple[float, str]]:
        """Find the market capitalisation of the quote row: the row naming `TICKER:EXCHANGE` in its slug slot.

        Args:
            blocks (List[JsonValue]): The decoded blocks.
            ticker (str): The ticker.
            exchange (str): The exchange.

        Returns:
            Optional[Tuple[float, str]]: The capitalisation and its currency, `None` when no quote row states one.
        """
        layout = self.concepts.google_finance
        slug = f"{ticker}:{exchange}"
        for block in blocks:
            for node in self._lists(block):
                if len(node) <= max(layout.quote_market_cap_slot, layout.quote_currency_slot) or slug not in node:
                    continue
                cap, currency = node[layout.quote_market_cap_slot], node[layout.quote_currency_slot]
                if self._is_number(cap) and isinstance(currency, str) and len(currency) == 3:
                    return float(str(cap)), currency
        return None

    def _period_facts(self, response: Response, statement: Statement) -> Iterator[FinancialFact]:
        """Build the facts of a period, one per pinned statement line it states.

        Args:
            response (Response): The quote page.
            statement (Statement): The fiscal year, the quarter and the values.

        Returns:
            Iterator[FinancialFact]: The facts of the period.
        """
        layout = self.concepts.google_finance
        year, quarter, values = statement
        currency = values[layout.currency_slot]
        end = self._day(values[layout.period_end_slot])
        granularity = FinancialGranularity.YEAR if quarter is None else FinancialGranularity.QUARTER
        for slot in layout.slots:
            value = values[slot.slot] if slot.slot < len(values) else None
            if not self._is_number(value):
                continue
            number = float(str(value))
            try:
                yield FinancialFact(
                    company=self._company(response),
                    source=FinancialSource.GOOGLE_FINANCE,
                    metric=slot.metric,
                    concept=f"gfinance:{slot.slot}",
                    end=end,
                    granularity=granularity,
                    value=-number if slot.negate else number,
                    currency=None if slot.metric in self.SHARE_COUNTS else currency,
                    fiscal_year=year,
                    fiscal_period="FY" if quarter is None else f"Q{quarter}",
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning(
                    "Invalid %s figure of %s left out: %s", slot.metric.value, response.url, e.errors()[0]["msg"]
                )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the quote page of every listed company read, under its first Google exchange code.

        Yields:
            Request: A request per listed company.
        """
        entries = self.companies.entries(self.scope.companies)
        listed = [(entry, self._valued_listing(entry)) for entry in entries]
        self.logger.info(
            "Requesting the Google Finance statements of %d listed companies (of %d).",
            sum(1 for _, listing in listed if listing),
            len(entries),
        )
        for entry, listing in listed:
            request = self._quote_request(entry.key, listing, 0) if listing else None
            if request is not None:
                yield request

    def extract_facts(self, response: Response) -> Iterator[CompanyFact]:
        """Extract the statements and the market capitalisation of a quote page.

        Args:
            response (Response): The quote page.

        Returns:
            Iterator[CompanyFact]: A financial fact per statement line and period, and the market capitalisation.
        """
        symbol = str(response.meta.get(CompanyMeta.LISTING, ""))
        if BatchExecuteField.CONSENT_HOST in response.url:
            self.logger.error("Google answered %s with its consent wall: renew the consent cookies.", symbol)
            return
        blocks = self._blocks(self._body_text(response))
        statements = self._statements(blocks)
        self.logger.info(
            "%s: %d periods of statements (%d years, %d quarters) in %d blocks.",
            symbol,
            len(statements),
            sum(1 for statement in statements if statement[1] is None),
            sum(1 for statement in statements if statement[1] is not None),
            len(blocks),
        )
        for statement in statements:
            yield from self._period_facts(response, statement)
        ticker, _, exchange = response.url.rsplit("/quote/", 1)[-1].split("?", 1)[0].partition(":")
        cap = self._market_cap(blocks, ticker, exchange) if statements else None
        if cap is not None:
            try:
                yield FinancialFact(
                    company=self._company(response),
                    source=FinancialSource.GOOGLE_FINANCE,
                    metric=FinancialMetric.MARKET_CAP,
                    concept=f"gfinance:quote:{self.concepts.google_finance.quote_market_cap_slot}",
                    end=datetime.now(UTC).date(),
                    granularity=FinancialGranularity.INSTANT,
                    value=cap[0],
                    currency=cap[1],
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid market capitalisation of %s left out: %s", symbol, e.errors()[0]["msg"])

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Ask the quote page again under the next Google exchange code of the listing, when it gave no statement.

        Args:
            response (Response): The quote page.
            found (int): The facts it gave.

        Returns:
            Iterator[Request]: The next request, none when statements were found or every code was tried.
        """
        if found:
            return iter(())
        listing = self.markets.listing(str(response.meta.get(CompanyMeta.LISTING, "")))
        candidate = response.meta.get(CompanyMeta.CANDIDATE, 0)
        company = self._company(response)
        request = (
            self._quote_request(company, listing, int(candidate) + 1)
            if listing and isinstance(candidate, int)
            else None
        )
        if request is None:
            self.logger.warning("Google Finance has no statements for %s (%s).", company, response.url)
            return iter(())
        self.logger.info("Trying %s under its next Google exchange code.", listing.symbol if listing else "?")
        return iter((request,))
