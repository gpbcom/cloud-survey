from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.enums import HtmlAttribute
from crawler.markets.base import MarketFact
from crawler.markets.press.base import BasePressCrawler
from crawler.markets.trendforce.enums import TrendForceMeta, TrendForcePage, TrendForceSelector
from models.markets.enums import MarketFeed, ShareSource

type ListedRelease = Tuple[str, str, date]


class TrendForceCrawler(BasePressCrawler):
    """Crawl the shares of the foundries and memory makers in TrendForce's press releases (quarterly, worldwide).

    Attributes:
        LISTING_URL (ClassVar[str]): A page of the semiconductor news listing, formatted with its number.
        MAX_PAGES (ClassVar[int]): The most listing pages walked (about 260 go back to 2008).
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): TrendForce.
        share_source (ClassVar[ShareSource]): TrendForce.
        catalogue_url (ClassVar[str]): The TrendForce host.
        download_delay (float): Two seconds between two pages.

    Notes:
        - The listing prints five releases per page, newest first, back to 2008 (DRAMeXchange). The releases whose
          title matches a TrendForce family (foundry, DRAM or NAND revenue rankings, the forecasts left out) are
          read. With `MARKETS_SINCE`, the walk stops at the first page older than that month.
        - The text of a release ends before the links to the previous and next releases, which would lend it their
          titles.
        - The rankings are images: the shares are read from the sentences ("TSMC … capturing a 72.5% market share"),
          for the companies the catalogue names, so the smaller ones are often missing.
        - TrendForce's `robots.txt` disallows only `/api`, `/search` and `/research/feedback`.
    """

    LISTING_URL: ClassVar[str] = "https://www.trendforce.com/presscenter/news/Semiconductors?page={page}"
    MAX_PAGES: ClassVar[int] = 300
    name = "trendforce"
    feed: ClassVar[MarketFeed] = MarketFeed.TRENDFORCE
    share_source: ClassVar[ShareSource] = ShareSource.TRENDFORCE
    catalogue_url: ClassVar[str] = "https://www.trendforce.com/"
    download_delay: float = 2.0

    ############################
    # Internal Helpers Methods #
    ############################

    def _listing_request(self, page: int) -> Request:
        """Build the request of a listing page.

        Args:
            page (int): Its number, from 1.

        Returns:
            Request: The request.
        """
        meta: Dict[str, JsonValue] = {
            TrendForceMeta.KIND.value: TrendForcePage.LISTING.value,
            TrendForceMeta.PAGE.value: page,
        }
        return self._market_request(self.LISTING_URL.format(page=page), self._headers("text/html"), **meta)

    def _listed(self, response: Response) -> List[ListedRelease]:
        """Read the releases of a listing page.

        Args:
            response (Response): The listing page.

        Returns:
            List[ListedRelease]: The URL, the title and the publication day of each release.
        """
        releases: List[ListedRelease] = []
        for item in response.css(TrendForceSelector.ITEM):
            links, days = item.css(TrendForceSelector.LINK), item.css(TrendForceSelector.DATE)
            if not links or not days:
                continue
            title = " ".join(str(links[0].get_all_text(separator=" ", strip=True)).split())
            href = str(links[0].attrib.get(HtmlAttribute.HREF, ""))
            try:
                published = datetime.strptime(str(days[0].get_all_text(strip=True)), "%d %B %Y").date()
            except ValueError:
                self.logger.warning("Unreadable date of the TrendForce release %s.", href)
                continue
            if title and href:
                releases.append((urljoin(response.url, href), title, published))
        return releases

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the semiconductor news listing.

        Yields:
            Request: The first listing page.
        """
        self.logger.info("Walking the TrendForce semiconductor news since %s.", self._since() or "2008")
        yield self._listing_request(1)

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the shares a release states (a listing page gives none).

        Args:
            response (Response): The page.

        Returns:
            Iterator[MarketFact]: The shares of the release.
        """
        if response.meta.get(TrendForceMeta.KIND) != TrendForcePage.RELEASE:
            return
        families = self._families()
        index = response.meta.get(TrendForceMeta.FAMILY)
        if not isinstance(index, int) or not 0 <= index < len(families):
            self.logger.warning("The TrendForce release %s has no family.", response.url)
            return
        bodies = response.css(TrendForceSelector.BODY)
        if not bodies:
            self.logger.warning("The TrendForce release %s has no body.", response.url)
            return
        content = str(bodies[0].html_content).split(TrendForceSelector.BODY_END, 1)[0]
        title = str(response.meta.get(TrendForceMeta.TITLE, ""))
        published = date.fromisoformat(str(response.meta.get(TrendForceMeta.PUBLISHED)))
        text = str(Selector(content).get_all_text(separator=" ", strip=True))
        yield from self._read_release(families[index], content, text, title, published, response.url)

    def follow_ups(self, response: Response, found: int) -> Iterator[Request]:
        """Request the releases of a listing page whose title matches a family, then the next page.

        Args:
            response (Response): The page.
            found (int): The shares it gave (none for a listing page).

        Returns:
            Iterator[Request]: The matching releases and the next listing page, none for a release.
        """
        if response.meta.get(TrendForceMeta.KIND) != TrendForcePage.LISTING:
            return iter(())
        page = int(response.meta.get(TrendForceMeta.PAGE, 1))
        since: Optional[date] = self._since()
        releases = self._listed(response)
        requests: List[Request] = []
        for url, title, published in releases:
            family = self._family(title)
            if family is None or (since and published < since):
                continue
            self.logger.debug("TrendForce release %s (%s) matches the %s family.", title, published, family[1].segment)
            meta: Dict[str, JsonValue] = {
                TrendForceMeta.KIND.value: TrendForcePage.RELEASE.value,
                TrendForceMeta.TITLE.value: title,
                TrendForceMeta.PUBLISHED.value: published.isoformat(),
                TrendForceMeta.FAMILY.value: family[0],
            }
            requests.append(self._market_request(url, self._headers("text/html"), **meta))
        oldest = min((published for _, _, published in releases), default=None)
        if releases and page < self.MAX_PAGES and not (since and oldest and oldest < since):
            requests.append(self._listing_request(page + 1))
        else:
            self.logger.info("TrendForce listing walked down to page %d.", page)
        return iter(requests)
