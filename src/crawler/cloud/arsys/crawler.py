from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, List, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError


class ArsysCrawler(BaseCloudCrawler):
    """Arsys catalogue crawler.

    Attributes:
        MENU_LINKS (ClassVar[str]): The CSS selector of the main menu links, the main and "more" lists of each section.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to tools, prices, company pages and partners.
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The menu labels which are not products.
        TRADEMARKS (ClassVar[re.Pattern[str]]): The trademark signs removed from the menu labels.

    Notes:
        The main source is the main menu of the https://www.arsys.net/ home page (English website). Each section of
        the menu (domains, e-mail, websites, hosting, servers, cloud, security, managed services...) lists its
        products, without description, so each product page is requested and its product is read from its meta
        description, the menu label giving the product name.
    """

    MENU_LINKS: ClassVar[str] = "div.section ul.main a[href], div.section ul.more a[href]"
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/tools(/|$)|prices|/about(/|$)|/contact|partners|generator|/whois", re.IGNORECASE
    )
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(r"^(use cases|customer support)$", re.IGNORECASE)
    TRADEMARKS: ClassVar[re.Pattern[str]] = re.compile(r"[®™]")

    name = "arsys"
    catalogue_url: ClassVar[str] = "https://www.arsys.net/"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Arsys ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _menu_entries(self, response: Response) -> Dict[str, Tuple[str, str]]:
        """Read the product links of the main menu, once per page, with their label.

        Args:
            response (Response): The home page.

        Returns:
            Dict[str, Tuple[str, str]]: The product page URL and label, by URL key, in the menu order.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        links = response.css(self.MENU_LINKS)
        if not links:
            self.logger.error("The %s page %s has no main menu (%s).", self.name, response.url, self.MENU_LINKS)
            raise CatalogueFormatError(self.name, response.url, "the main menu is missing")
        entries: Dict[str, Tuple[str, str]] = {}
        for link in links:
            label = self._clean_text(self.TRADEMARKS.sub("", link.get_all_text(separator=" ", strip=True)))
            url = urljoin(response.url, link.attrib.get("href", ""))
            parsed = urlparse(url)
            if parsed.query or self.NOT_PRODUCT_LINK.search(parsed.path) or self.NOT_PRODUCT_LABEL.match(label):
                self.logger.debug("Skipping the menu link %r (%s), not a product.", label, url)
                continue
            key = self._url_key(url)
            if key in entries:
                self.logger.debug("Skipping the menu link %r (%s), already listed.", label, url)
                continue
            entries[key] = (url, label)
        self.logger.debug("%d product links in the %s menu (%d links).", len(entries), self.name, len(links))
        return entries

    def _menu_requests(self, response: Response) -> List[Request]:
        """Request the product pages listed by the main menu.

        Args:
            response (Response): The home page.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the page has no main menu.
        """
        entries = self._menu_entries(response)
        requests = [
            request
            for url, label in entries.values()
            if (request := self._product_page_request(url, label)) is not None
        ]
        self.logger.info("%d %s product pages to read from the menu of %s.", len(requests), self.name, response.url)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the main menu, or stream the product of a product page.

        Args:
            response (Response): The home page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests,
                or the product of a product page.

        Raises:
            CatalogueFormatError: If the home page has no main menu.
        """
        if self.PRODUCT_PAGE in response.meta:
            async for item in super().parse(response):
                yield item
            return
        for request in self._menu_requests(response):
            yield request
