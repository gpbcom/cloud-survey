from __future__ import annotations

# Standard Library Imports.
import html
from datetime import date
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.markets.base import MarketFact
from crawler.markets.idc.enums import IdcField
from crawler.markets.press.base import BasePressCrawler
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed, ShareSource
from models.markets.markets_catalog import MarketsCatalog


class IdcCrawler(BasePressCrawler):
    """Crawl the shares of the PC, smartphone and tablet makers in IDC's press releases (quarterly, by area).

    Attributes:
        API_URL (ClassVar[str]): The press release API of IDC's site (WordPress).
        PER_PAGE (ClassVar[int]): The releases asked per page, the most the API gives.
        FIELDS (ClassVar[str]): The fields asked for.
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): IDC.
        share_source (ClassVar[ShareSource]): IDC.
        catalogue_url (ClassVar[str]): The IDC host.
        download_delay (float): Two seconds between two pages.
        seen (Set[int]): The releases already read (a release found by two searches is read once).

    Notes:
        - One search per term of the IDC families (`PC`, `smartphone`, `tablet`), one hundred releases a page, with
          their body: no release page is fetched. With `MARKETS_SINCE`, only the releases published since then.
        - Each "Top 5 Companies" table is read, every share column summing to about 100% (the top 5 and Others): a
          release gives its quarter and the quarter a year before. A table goes to the first family matching its
          caption, else the release title and its caption (India's smartphones before the worldwide ones).
        - The releases on the current site start in September 2022. IDC's `robots.txt` disallows nothing.
    """

    API_URL: ClassVar[str] = "https://www.idc.com/wp-json/wp/v2/press-release"
    PER_PAGE: ClassVar[int] = 100
    FIELDS: ClassVar[str] = "id,date,title,link,content"
    name = "idc"
    feed: ClassVar[MarketFeed] = MarketFeed.IDC
    share_source: ClassVar[ShareSource] = ShareSource.IDC
    catalogue_url: ClassVar[str] = "https://www.idc.com/"
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
            catalog (Optional[MarketsCatalog]): What is read, `conf/history/markets.yaml` by default.
            scope (Optional[CrawlScope]): The part read: the releases published since `scope.since` only.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(catalog=catalog, scope=scope, crawldir=crawldir, interval=interval)
        self.seen: Set[int] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_request(self, search: str, page: int) -> Request:
        """Build the request of a page of releases.

        Args:
            search (str): The search term.
            page (int): The page, from 1.

        Returns:
            Request: The request.
        """
        query: Dict[str, str] = {
            "search": search,
            "per_page": str(self.PER_PAGE),
            "page": str(page),
            "_fields": self.FIELDS,
        }
        since = self._since()
        if since:
            query["after"] = f"{since.isoformat()}T00:00:00"
        meta: Dict[str, JsonValue] = {IdcField.SEARCH.value: search, IdcField.PAGE.value: page}
        return self._market_request(f"{self.API_URL}?{urlencode(query)}", self._headers("application/json"), **meta)

    def _posts(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the releases of a page.

        Args:
            response (Response): The page.

        Returns:
            List[Dict[str, JsonValue]]: The releases, none when the page is not a list.
        """
        document = self._json_body(response)
        return [self._as_object(post) for post in document] if isinstance(document, list) else []

    def _rendered(self, post: Dict[str, JsonValue], field: IdcField) -> str:
        """Read a rendered field of a release.

        Args:
            post (Dict[str, JsonValue]): The release.
            field (IdcField): The title or the content.

        Returns:
            str: Its HTML, empty when missing.
        """
        return str(self._as_object(post.get(field)).get(IdcField.RENDERED) or "")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the releases read, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.seen.clear()

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of each search of the IDC families.

        Yields:
            Request: A request per search term.
        """
        searches = [*dict.fromkeys(family.search for family in self._families() if family.search)]
        self.logger.info("Searching the IDC press releases for: %s.", ", ".join(searches))
        for search in searches:
            yield self._page_request(search, 1)

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the shares of the releases of a page.

        Args:
            response (Response): The page.

        Returns:
            Iterator[MarketFact]: The shares of each table of each release, by family.
        """
        for post in self._posts(response):
            identifier = post.get(IdcField.ID)
            if not isinstance(identifier, int) or identifier in self.seen:
                continue
            self.seen.add(identifier)
            title = " ".join(html.unescape(self._rendered(post, IdcField.TITLE)).split())
            link = str(post.get(IdcField.LINK) or response.url)
            try:
                published = date.fromisoformat(str(post.get(IdcField.DATE, ""))[:10])
            except ValueError:
                self.logger.warning("Unreadable date of the IDC release %s.", link)
                continue
            for caption, shares in self.tables.read(self._rendered(post, IdcField.CONTENT), complete=True):
                family = self._family(title, caption)
                if family is None:
                    self.logger.debug("IDC table %r of %s matches no family.", caption, title)
                    continue
                yield from self._release_shares(family[1], shares, title, published, link)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Request the next page of a search when this one was full.

        Args:
            response (Response): The page.
            found (int): The shares it gave.

        Returns:
            Iterator[Request]: The next page, none after the last.
        """
        search = str(response.meta.get(IdcField.SEARCH, ""))
        page = int(response.meta.get(IdcField.PAGE, 1))
        if len(self._posts(response)) < self.PER_PAGE or not search:
            self.logger.info("IDC search %r read down to page %d.", search, page)
            return iter(())
        return iter((self._page_request(search, page + 1),))
