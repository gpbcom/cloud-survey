from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class ExoscaleMarketplaceCrawler(BaseMarketplaceCrawler):
    """Exoscale marketplace crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The website sitemap, listing every marketplace listing page.
        LISTING_PATH (ClassVar[str]): The path of the marketplace listing pages.
        LISTING (ClassVar[str]): The meta key marking a listing page request, holding the requested URL.
        SITEMAP (ClassVar[str]): The meta key marking the sitemap request.
        SECTION_DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace section.
        LICENSE_SUFFIX (ClassVar[re.Pattern[str]]): The license suffix of the listing page titles, e.g. `- BYOL`.

    Notes:
        The https://www.exoscale.com/marketplace/ page lists the software as cards (`article.mkplace-item`) in
        sections (`section[id]`) giving their delivery: compute instance templates, managed services and software
        powered by Exoscale. The sitemap lists more listing pages than the cards: each listing page not shown as a
        card is requested, and its software is read from its title, its editor and its description. A listing page
        offering a compute instance template (a `template-name` link) is a virtual machine.
    """

    SITEMAP_URL: ClassVar[str] = "https://www.exoscale.com/sitemap.xml"
    LISTING_PATH: ClassVar[str] = "/marketplace/listing/"
    LISTING: ClassVar[str] = "listing"
    SITEMAP: ClassVar[str] = "sitemap"
    SECTION_DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "templates": DeliveryMethod.VIRTUAL_MACHINE,
        "managed-services": DeliveryMethod.SAAS,
        "powered-by-exoscale": DeliveryMethod.SAAS,
    }
    LICENSE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s+-\s+(BYOL|PAYG)\s*$", re.IGNORECASE)

    name = "exoscale-marketplace"
    catalogue_url: ClassVar[str] = "https://www.exoscale.com/marketplace/"

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, element: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element matching a selector, within a page or a card.

        Args:
            element (Selector): The page or the card.
            selector (str): The CSS selector.

        Returns:
            Optional[str]: The text, `None` without matching element.
        """
        found = element.css(selector).first
        return found.get_all_text(separator=" ", strip=True) if found is not None else None

    def _cards_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the marketplace cards, section by section.

        Args:
            response (Response): The marketplace page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the cards.
        """
        for section in response.css("section[id]"):
            cards = section.css("article.mkplace-item")
            if not cards:
                continue
            identifier = section.attrib.get("id", "")
            title = self._text(section, "h2") or self._text(section, "h1")
            delivery = self.SECTION_DELIVERIES.get(identifier, DeliveryMethod.OTHER)
            self.logger.debug("%s section %r (%s): %d cards.", self.name, title, delivery, len(cards))
            for card in cards:
                link = card.css("a.mkplace-item__block-link::attr(href)").get()
                software = self._build_software(
                    self._text(card, "h3.mkplace-item__title"),
                    self._text(card, ".mkplace-item__bodycopy"),
                    urljoin(response.url, link) if link else None,
                    self._text(card, ".mkplace-item__editor span"),
                    delivery,
                    [title],
                )
                if software is not None:
                    yield software

    def _listing_description(self, response: Response, name: str) -> Optional[str]:
        """Read the description of a listing page: its meta description, else its product overview.

        Args:
            response (Response): The listing page.
            name (str): The page title, which some meta descriptions merely repeat.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        description = self._page_description(response)
        if description and self._name_key(description) != self._name_key(name):
            return description
        overview = ".mkplace-listing__blob-item--product-overview .mkplace-listing__blob-item__blob"
        return self._text(response, f"{overview} p") or self._text(response, overview) or description

    def _listing_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a listing page not shown as a card.

        Args:
            response (Response): The listing page, requested with the `LISTING` meta.

        Yields:
            Iterator[MarketplaceSoftware]: The software, unless the page is missing or invalid.
        """
        if response.status >= 400:
            self.logger.debug("Skipping the %s listing page %s (HTTP %s).", self.name, response.url, response.status)
            return
        title = self._text(response, "h1") or ""
        editor = self._text(response, ".mkplace-listing__aside__meta__list__element--editor")
        publisher = re.sub(r"^Editor\s*", "", editor or "").strip()
        templates = response.css('a[href*="template-name="]')
        software = self._build_software(
            self.LICENSE_SUFFIX.sub("", title),
            self._listing_description(response, title),
            str(response.meta.get(self.LISTING) or response.url),
            publisher,
            DeliveryMethod.VIRTUAL_MACHINE if templates else DeliveryMethod.OTHER,
        )
        if software is not None:
            yield software

    def _listing_requests(self, response: Response) -> List[Request]:
        """Build the requests of the listing pages of the sitemap not streamed yet (not shown as cards).

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The listing page requests.
        """
        requests: List[Request] = []
        for url in self._sitemap_urls(response):
            if self.LISTING_PATH not in url or url.casefold().rstrip("/") in self.software_categories:
                continue
            requests.append(Request(url, meta={self.LISTING: url, self.MAY_BE_EMPTY: True}))
        self.logger.info("%d %s listing pages not shown as cards requested.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the marketplace page, or of a listing page not shown as a card.

        Args:
            response (Response): The marketplace page, or a listing page (`LISTING` meta).

        Returns:
            Iterator[MarketplaceSoftware]: The valid software of the page.
        """
        if self.LISTING in response.meta:
            return self._listing_software(response)
        return self._cards_software(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a page, then request the sitemap once the cards are read.

        Args:
            response (Response): The marketplace page, a listing page (`LISTING` meta) or the sitemap (`SITEMAP`
                meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, or the follow-up requests.
        """
        if response.meta.get(self.SITEMAP):
            for request in self._listing_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
        if self.LISTING not in response.meta:
            self.logger.debug("Requesting the %s sitemap %s.", self.name, self.SITEMAP_URL)
            yield Request(self.SITEMAP_URL, meta={self.SITEMAP: True})
