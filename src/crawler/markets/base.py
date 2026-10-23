from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import TextEncoding
from crawler.exception import ParseNotImplementedError
from crawler.markets.catalog_loader import MarketsCatalogLoader
from crawler.tls.ca_bundle import CaBundle
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.facts.fx_observation import FxObservation
from models.markets.facts.price_point import PricePoint
from models.markets.facts.release_share import ReleaseShare
from models.markets.facts.share_observation import ShareObservation
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog

type MarketFact = Union[ShareObservation, PricePoint, FxObservation, WeightObservation, ReleaseShare]


class BaseMarketsCrawler(BaseCloudCrawler):
    """Base class for the crawlers of the market shares, the stock prices and the exchange rates.

    Attributes:
        USER_AGENT (ClassVar[str]): The user agent of the requests (the impersonated browser's is replaced).
        feed (ClassVar[MarketFeed]): The source crawled.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it (never here).
        catalog (MarketsCatalog): What is read: the areas, the listings, the currencies.
        scope (CrawlScope): The part of the catalogue read, and since when.
        facts (int): The facts streamed so far.

    Notes:
        - The sources are public CSV and JSON endpoints, read through an HTTP session (`<name>-http`), the default
          one, one request at a time with the delay of the source, and their `robots.txt` obeyed.
        - A crawler streams the facts as the source states them (a label's share of a month, a weekly close, a
          rate). Mapping the labels to the companies, converting the currencies and estimating the EU-27 is left
          to `analytics.markets`.
    """

    USER_AGENT: ClassVar[str] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
    feed: ClassVar[MarketFeed] = MarketFeed.STATCOUNTER
    lazy_browser: ClassVar[bool] = True

    def __init__(
        self,
        catalog: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            catalog (Optional[MarketsCatalog]): What is read, `conf/history/markets.yaml` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.catalog = catalog if catalog else MarketsCatalogLoader(self.logger).load()
        self.scope = scope if scope else CrawlScope()
        self.facts = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, e.g. `statcounter-http`.
        """
        return f"{self.name}-http"

    def _headers(self, accept: str) -> Dict[str, str]:
        """Build the headers of a request: the user agent, and the media type asked for.

        Args:
            accept (str): The media type asked for.

        Returns:
            Dict[str, str]: The headers.
        """
        return {"User-Agent": self.USER_AGENT, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}

    def _market_request(self, url: str, headers: Dict[str, str], **meta: JsonValue) -> Request:
        """Build a GET request of the HTTP session.

        Args:
            url (str): The requested URL.
            headers (Dict[str, str]): The request headers.
            **meta (JsonValue): The request meta, given back with the response.

        Returns:
            Request: The request.
        """
        return Request(
            url, sid=self._http_session_id(), priority=self.PRIMARY_PRIORITY, meta=dict(meta), headers=headers
        )

    def _body_text(self, response: Response) -> str:
        """Read the raw body of a response as text.

        Args:
            response (Response): The response.

        Returns:
            str: The body, decoded as UTF-8 (undecodable bytes replaced).
        """
        return response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)

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
                stealthy_headers=False,
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
        self.logger.info("The %s markets crawl is over: %d facts.", self.name, self.facts)

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the facts of a document.

        Args:
            response (Response): The document.

        Returns:
            Iterator[MarketFact]: The valid facts of the document.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the fact extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Get the requests a document leads to, e.g. the next page of a listing or the releases it lists.

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
            Union[Dict[str, JsonValue], Request]: Each fact, as a dictionary, then each follow-up request.
        """
        self.logger.debug("Parsing the %s document %s (HTTP %s).", self.name, response.url, response.status)
        found = 0
        for fact in self.extract_facts(response):
            found += 1
            yield fact.model_dump(mode="json")
        self.facts += found
        for request in self.follow_ups(response, found):
            yield request
        self.logger.info("%s document %s parsed: %d facts.", self.name, response.url, found)
