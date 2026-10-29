from __future__ import annotations

# Standard Library Imports.
import json
from datetime import date
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Iterator, List, Optional, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.enums import HttpMethod
from crawler.markets.base import BaseMarketsCrawler, MarketFact
from crawler.markets.google_finance.enums import BatchExecuteField, GoogleFinanceHeader, GoogleFinanceMeta
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.facts.price_point import PricePoint
from models.markets.listings.stock_listing import StockListing
from models.markets.markets_catalog import MarketsCatalog


class GoogleFinanceCrawler(BaseMarketsCrawler):
    """Crawl the price history of the listings from Google Finance's chart RPC (one weekly close over the history).

    Attributes:
        BASE_URL (ClassVar[str]): The Google Finance root.
        RPC_PATH (ClassVar[str]): The `batchexecute` endpoint the chart calls.
        MIN_POINTS (ClassVar[int]): The fewest points a list must hold to be taken for a series.
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): Google Finance.
        catalogue_url (ClassVar[str]): The Google Finance root.
        download_delay (float): Two seconds between two listings, as mega-trends paces it.

    Notes:
        - Ported from mega-trends' `GoogleFinanceScraper` (`rt-scrapers/rt_scrapers/scrapers/google/finance.py`):
          one plain POST asks the chart's own RPC (`c2u4wc`, window 8 = Max) for the whole history, so no browser
          is needed. The request is `f.req=[[[rpc, json([[[null, [symbol, exchange]]], 8, …, 0]), null,
          "generic"]]]`, with `X-Same-Domain: 1` and the consent cookies of the catalogue.
        - The response is `)]}'`, then length and JSON lines: each JSON line is a list of `["wrb.fr", rpc,
          payload]` envelopes whose payload is JSON again (decoded twice, on purpose). The series is found by its
          shape, never by its position, which Google moves: a list of `[[Y, M, D, h, m, s, ?, [offset]], [close,
          …], volume]` points. The widest one is kept.
        - The trading day is the local date of the point (the exchange's own day). The prices are in the listing
          currency, split-adjusted, dividends not reinvested.
        - A redirect to `consent.google.com` means Google refused the consent cookies: nothing is streamed and the
          stored prices are kept. No proxy is used (it breaks the cookies), and `robots.txt` allows `/finance/`.
        - A listing whose exchange Google files under another code (`FWB` as `ETR` then `FRA`) is asked again under
          the next code when the first one answers no series.
    """

    BASE_URL: ClassVar[str] = "https://www.google.com/finance"
    RPC_PATH: ClassVar[str] = "/beta/_/FinHubUi/data/batchexecute"
    MIN_POINTS: ClassVar[int] = 5
    name = "google-finance"
    feed: ClassVar[MarketFeed] = MarketFeed.GOOGLE_FINANCE
    catalogue_url: ClassVar[str] = "https://www.google.com/finance/"
    download_delay: float = 2.0

    def __init__(
        self,
        catalog: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            catalog (Optional[MarketsCatalog]): What is read, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(catalog=catalog, scope=scope, crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _listings(self) -> List[StockListing]:
        """Get the listings read: those of the scope, or every listing of the catalogue.

        Returns:
            List[StockListing]: The listings.
        """
        if not self.scope.listings:
            return list(self.catalog.listings)
        unknown = [symbol for symbol in self.scope.listings if self.catalog.listing(symbol) is None]
        if unknown:
            self.logger.warning("Listings left out (not in the catalogue): %s.", ", ".join(unknown))
        return [listing for listing in self.catalog.listings if listing.symbol in self.scope.listings]

    def _rpc_url(self, ticker: str, exchange: str) -> str:
        """Build the URL of the chart RPC, with the query the endpoint expects.

        Args:
            ticker (str): The ticker, as Google files it.
            exchange (str): The exchange, as Google files it.

        Returns:
            str: The URL.

        Notes:
            The session parameters of the page (`f.sid`, `bl`) are left out on purpose: the endpoint answers the
            same series without them, as mega-trends measured.
        """
        query = {
            "rpcids": self.catalog.google_finance.rpc_id,
            "source-path": f"/finance/beta/quote/{ticker}:{exchange}",
            "hl": "en-US",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": "100000",
            "rt": "c",
        }
        return f"{self.BASE_URL}{self.RPC_PATH}?{urlencode(query)}"

    def _rpc_body(self, ticker: str, exchange: str) -> str:
        """Build the form body asking the chart RPC for the whole history.

        Args:
            ticker (str): The ticker.
            exchange (str): The exchange.

        Returns:
            str: The URL-encoded `f.req` field: the request envelope, with the RPC arguments encoded inside it.
        """
        settings = self.catalog.google_finance
        arguments = json.dumps([[[None, [ticker, exchange]]], settings.period, None, None, None, None, None, 0])
        envelope = [[[settings.rpc_id, arguments, None, BatchExecuteField.GENERIC.value]]]
        return urlencode({BatchExecuteField.REQUEST.value: json.dumps(envelope)})

    def _rpc_request(self, listing: StockListing, candidate: int) -> Optional[Request]:
        """Build the chart RPC request of a listing under one of its Google exchange codes.

        Args:
            listing (StockListing): The listing.
            candidate (int): The index of the exchange code tried.

        Returns:
            Optional[Request]: The request, `None` when every code was tried.
        """
        candidates = listing.google_candidates()
        if candidate >= len(candidates):
            return None
        ticker, exchange = candidates[candidate]
        cookies = "; ".join(f"{name}={value}" for name, value in self.catalog.google_finance.consent_cookies.items())
        headers = self._headers("*/*")
        headers.update(
            {
                GoogleFinanceHeader.SAME_DOMAIN.value: "1",
                GoogleFinanceHeader.CONTENT_TYPE.value: "application/x-www-form-urlencoded;charset=UTF-8",
                GoogleFinanceHeader.COOKIE.value: cookies,
                GoogleFinanceHeader.REFERER.value: f"{self.BASE_URL}/quote/{ticker}:{exchange}",
            }
        )
        return Request(
            self._rpc_url(ticker, exchange),
            sid=self._http_session_id(),
            priority=self.PRIMARY_PRIORITY,
            meta={GoogleFinanceMeta.LISTING.value: listing.symbol, GoogleFinanceMeta.CANDIDATE.value: candidate},
            headers=headers,
            method=HttpMethod.POST.value,
            data=self._rpc_body(ticker, exchange),
        )

    def _payloads(self, text: str) -> List[JsonValue]:
        """Decode the payloads of a `batchexecute` response.

        Args:
            text (str): The response body.

        Returns:
            List[JsonValue]: The payload of each `wrb.fr` envelope, decoded. A line or a payload that does not
                decode is left out.
        """
        if text.startswith(BatchExecuteField.PREFIX):
            text = text[len(BatchExecuteField.PREFIX) :]
        payloads: List[JsonValue] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                envelopes = json.loads(line)
            except ValueError as e:
                self.logger.debug("Undecodable batchexecute line (%d characters): %s", len(line), e)
                continue
            for envelope in envelopes if isinstance(envelopes, list) else []:
                if not isinstance(envelope, list) or len(envelope) < 3 or envelope[0] != BatchExecuteField.ENVELOPE:
                    continue
                if not isinstance(envelope[2], str):
                    continue
                try:
                    payloads.append(json.loads(envelope[2]))
                except ValueError as e:
                    self.logger.debug("Undecodable %s payload: %s", envelope[1], e)
        return payloads

    def _lists(self, root: JsonValue) -> List[List[JsonValue]]:
        """Get every list nested under a value, the value first.

        Args:
            root (JsonValue): The value.

        Returns:
            List[List[JsonValue]]: The lists, depth first.
        """
        found: List[List[JsonValue]] = []
        stack: List[JsonValue] = [root]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                found.append(node)
                stack.extend(reversed(node))
        return found

    def _is_number(self, value: JsonValue) -> bool:
        """Tell whether a value is a number (a boolean is not).

        Args:
            value (JsonValue): The value.

        Returns:
            bool: Whether it is an int or a float.
        """
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _day(self, value: JsonValue) -> Optional[date]:
        """Read Google's `[year, month, day, …]` date.

        Args:
            value (JsonValue): The value.

        Returns:
            Optional[date]: The local day, `None` when the value is not a plausible date.
        """
        if not isinstance(value, list) or len(value) < 3:
            return None
        year, month, day = value[0], value[1], value[2]
        if not (isinstance(year, int) and isinstance(month, int) and isinstance(day, int)):
            return None
        try:
            return date(year, month, day) if 1900 < year < 2100 else None
        except ValueError:
            return None

    def _is_point(self, value: JsonValue) -> bool:
        """Tell whether a value is a chart point: `[[Y, M, D, …], [close, …], volume?]`.

        Args:
            value (JsonValue): The value.

        Returns:
            bool: Whether it is a chart point.
        """
        return (
            isinstance(value, list)
            and len(value) >= 2
            and self._day(value[0]) is not None
            and isinstance(value[1], list)
            and len(value[1]) >= 1
            and self._is_number(value[1][0])
        )

    def _span_days(self, series: List[JsonValue]) -> int:
        """Get the days a series covers.

        Args:
            series (List[JsonValue]): The points.

        Returns:
            int: The days between its first and last point.
        """
        first = self._day(series[0][0]) if isinstance(series[0], list) else None
        last = self._day(series[-1][0]) if isinstance(series[-1], list) else None
        return (last - first).days if first and last else 0

    def _widest_series(self, payloads: List[JsonValue]) -> Optional[List[JsonValue]]:
        """Find the chart series covering the longest span.

        Args:
            payloads (List[JsonValue]): The decoded payloads.

        Returns:
            Optional[List[JsonValue]]: The points of the widest series, `None` when there is none.
        """
        series = [
            node
            for payload in payloads
            for node in self._lists(payload)
            if len(node) >= self.MIN_POINTS and all(self._is_point(item) for item in node)
        ]
        return max(series, key=self._span_days) if series else None

    def _currency(self, payloads: List[JsonValue], ticker: str) -> Optional[str]:
        """Find the currency Google states for the listing: `[[ticker, exchange], id, "USD", …]`.

        Args:
            payloads (List[JsonValue]): The decoded payloads.
            ticker (str): The ticker.

        Returns:
            Optional[str]: The currency, `None` when not stated.
        """
        for payload in payloads:
            for node in self._lists(payload):
                head = node[0] if node else None
                if isinstance(head, list) and head and head[0] == ticker and len(node) >= 3:
                    currency = node[2]
                    if isinstance(currency, str) and len(currency) == 3 and currency.isupper():
                        return currency
        return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the history of every listing, under its first Google exchange code.

        Yields:
            Request: A request per listing.
        """
        listings = self._listings()
        self.logger.info("Requesting the price history of %d listings from Google Finance.", len(listings))
        for listing in listings:
            request = self._rpc_request(listing, 0)
            if request is not None:
                yield request

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the weekly closes of a chart RPC response.

        Args:
            response (Response): The response.

        Returns:
            Iterator[MarketFact]: A closing price per point of the widest series.
        """
        symbol = str(response.meta.get(GoogleFinanceMeta.LISTING, ""))
        listing = self.catalog.listing(symbol)
        if listing is None:
            self.logger.warning("The Google Finance response %s is for no listing of the catalogue.", response.url)
            return
        if BatchExecuteField.CONSENT_HOST in response.url:
            self.logger.error(
                "Google answered %s with its consent wall: renew the consent cookies of the catalogue.", symbol
            )
            return
        payloads = self._payloads(self._body_text(response))
        series = self._widest_series(payloads)
        if series is None:
            self.logger.warning("The chart RPC answered %d bytes for %s but no series.", len(response.body), symbol)
            return
        currency = self._currency(payloads, listing.ticker()) or listing.currency
        if currency != listing.currency:
            self.logger.warning("Google quotes %s in %s, the catalogue says %s.", symbol, currency, listing.currency)
        self.logger.info("%s: %d points over %d days.", symbol, len(series), self._span_days(series))
        for point in series:
            if not isinstance(point, list) or not isinstance(point[1], list):
                continue
            volume = point[2] if len(point) > 2 and self._is_number(point[2]) else None
            try:
                yield PricePoint(
                    listing=symbol,
                    day=self._day(point[0]),
                    close=point[1][0],
                    volume=volume,
                    currency=currency,
                    source_url=response.url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid price of %s left out: %s", symbol, e.errors()[0]["msg"])

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Ask the history again under the next Google exchange code of the listing, when the response gave none.

        Args:
            response (Response): The response.
            found (int): The prices it gave.

        Returns:
            Iterator[Request]: The next request, none when prices were found or every code was tried.
        """
        if found:
            return iter(())
        listing = self.catalog.listing(str(response.meta.get(GoogleFinanceMeta.LISTING, "")))
        candidate = response.meta.get(GoogleFinanceMeta.CANDIDATE, 0)
        request = self._rpc_request(listing, int(candidate) + 1) if listing and isinstance(candidate, int) else None
        if request is None:
            if listing:
                self.logger.warning("Google Finance has no price history for %s.", listing.symbol)
            return iter(())
        self.logger.info("Trying %s under its next Google exchange code.", listing.symbol if listing else "?")
        return iter((request,))
