from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.combell.enums import CombellCssClass
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError


class CombellCrawler(BaseCloudCrawler):
    """Combell catalogue crawler.

    Attributes:
        MANAGED_SERVICES_URL (ClassVar[str]): The managed services page, listing the IT solutions.
        MENU_LINKS (ClassVar[str]): The CSS selector of the main menu links.
        SOLUTION_LINKS (ClassVar[str]): The CSS selector of the IT solutions links of the managed services page.
        NOT_PRODUCT_ID (ClassVar[re.Pattern[str]]): The menu link identifiers of the overviews and partner programmes.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The links to prices, partner programmes, the technology page
            and the business needs pages of the managed services (performance, collaboration, security, uptime).
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The link labels which are not products (overviews, tools).
        MENU_CATEGORY (ClassVar[Tuple[CombellCssClass, str]]): The class of the main menu items and the CSS selector
            of their label, the category of the links they hold.
        SOLUTION_CATEGORY (ClassVar[Tuple[CombellCssClass, str]]): The class of the IT solutions cards and the CSS
            selector of their title, the category of the links they hold.

    Notes:
        The main source is the main menu of the https://www.combell.com/en/ home page (domain names, hosting,
        websites, e-mail, tools, servers, managed services). The IT solutions of the managed services page complete
        it. Both only give the product names, so each product page is requested and its product is read from its
        meta description, the link label giving the product name. The catalogue categories of a product are the
        main menu entries listing it (e.g. `Servers`), or the IT solutions cards listing it (e.g.
        `Cloud & infrastructure`). The titles of the menu columns are left out, as many are slogans.
    """

    MANAGED_SERVICES_URL: ClassVar[str] = "https://www.combell.com/en/managed-services"
    MENU_LINKS: ClassVar[str] = 'a.dropdown__link[id^="sel-nav-"][href]'
    SOLUTION_LINKS: ClassVar[str] = "#solutions a[href]"
    NOT_PRODUCT_ID: ClassVar[re.Pattern[str]] = re.compile(r"overview|partners", re.IGNORECASE)
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/prices|/partners|/affiliate|commission-partner|/technology$|/performance-optimisation$|"
        r"/digital-collaboration$|/tailored-security$|/avoid-downtime$",
        re.IGNORECASE,
    )
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(
        r"^(all |more |learn more|find out|discover|generate )", re.IGNORECASE
    )
    MENU_CATEGORY: ClassVar[Tuple[CombellCssClass, str]] = (CombellCssClass.MENU_ITEM, ":scope > a.menu__link")
    SOLUTION_CATEGORY: ClassVar[Tuple[CombellCssClass, str]] = (CombellCssClass.CARD_BODY, "h3")

    name = "combell"
    catalogue_url: ClassVar[str] = "https://www.combell.com/en/"
    complement_urls: ClassVar[Tuple[str, ...]] = (MANAGED_SERVICES_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Combell ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _link_category(self, link: Selector, scope: Tuple[CombellCssClass, str]) -> Optional[str]:
        """Read the category of a link: the label of the closest element of a class holding it.

        Args:
            link (Selector): The link.
            scope (Tuple[CombellCssClass, str]): The class of the category elements and the CSS selector of their label.

        Returns:
            Optional[str]: The category, e.g. `Servers`, `None` when the link is not in such an element.
        """
        container, heading = scope
        node = link.parent
        while node is not None:
            if container in node.attrib.get(HtmlAttribute.CLASS, "").split():
                title = node.css(heading).first
                if title is None:
                    return None
                return self._clean_text(title.get_all_text(separator=" ", strip=True)) or None
            node = node.parent
        return None

    def _link_label(self, link: Selector) -> str:
        """Read the label of a link, without its badges and notes (`small`, `span` children).

        Args:
            link (Selector): The link.

        Returns:
            str: The label, e.g. `Private cloud` for `Private cloud <small>Most popular</small>`.
        """
        return self._clean_text(str(link.text or "")) or self._clean_text(link.get_all_text(separator=" ", strip=True))

    def _is_product_link(self, link: Selector, label: str, url: str) -> bool:
        """Tell whether a link leads to a product page.

        Args:
            link (Selector): The link.
            label (str): Its label.
            url (str): Its absolute URL.

        Returns:
            bool: Whether the link is not an overview, a partner programme, a price list, a tool or a page section.
        """
        parsed = urlparse(url)
        reasons = {
            "overview or partners": bool(self.NOT_PRODUCT_ID.search(link.attrib.get(HtmlAttribute.ID, ""))),
            "prices, partners, technology or business need page": bool(
                self.NOT_PRODUCT_LINK.search(parsed.path.rstrip("/"))
            ),
            "page section": bool(parsed.fragment or parsed.query),
            "overview or tool label": bool(self.NOT_PRODUCT_LABEL.match(label)),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the link %r (%s): %s.", label, url, ", ".join(failed))
            return False
        return True

    def _product_links(
        self, response: Response, selector: str, scope: Tuple[CombellCssClass, str]
    ) -> Dict[str, Tuple[str, str, List[str]]]:
        """Read the product links of a page, once per product page, with their most descriptive label.

        Args:
            response (Response): The page.
            selector (str): The CSS selector of the links.
            scope (Tuple[CombellCssClass, str]): The class of the elements giving the category of the links they hold,
                and the CSS selector of their label.

        Returns:
            Dict[str, Tuple[str, str, List[str]]]: The product page URL, label and categories (of all its links), by
                URL key, in the page order.

        Raises:
            CatalogueFormatError: If the page has no such link.
        """
        links = response.css(selector)
        if not links:
            self.logger.error("The %s page %s has no product links (%s).", self.name, response.url, selector)
            raise CatalogueFormatError(self.name, response.url, f"the product links `{selector}` are missing")
        entries: Dict[str, Tuple[str, str, List[str]]] = {}
        for link in links:
            label = self._link_label(link)
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if not label or not self._is_product_link(link, label, url):
                continue
            key = self._url_key(url)
            category = self._link_category(link, scope)
            categories = [*(entries[key][2] if key in entries else []), *([category] if category else [])]
            if key in entries and len(entries[key][1]) >= len(label):
                entries[key] = (entries[key][0], entries[key][1], categories)
                continue
            entries[key] = (entries[key][0] if key in entries else url, label, categories)
        self.logger.debug("%d product links in %s (%d links).", len(entries), response.url, len(links))
        return entries

    def _page_requests(self, response: Response) -> List[Request]:
        """Request the product pages listed by the main menu or by the IT solutions of the managed services page.

        Args:
            response (Response): The home page or the managed services page.

        Returns:
            List[Request]: The product page requests, with their categories.

        Raises:
            CatalogueFormatError: If the page has no product links.
        """
        if self._url_key(response.url) == self._url_key(self.MANAGED_SERVICES_URL):
            entries = self._product_links(response, self.SOLUTION_LINKS, self.SOLUTION_CATEGORY)
        else:
            entries = self._product_links(response, self.MENU_LINKS, self.MENU_CATEGORY)
        requests: List[Request] = []
        for url, label, categories in entries.values():
            if (request := self._product_page_request(url, label, categories=categories)) is not None:
                requests.append(request)
        self.logger.info("%d %s product pages to read from %s.", len(requests), self.name, response.url)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the menu or of the IT solutions, or stream the product of a product page.

        Args:
            response (Response): The home page, the managed services page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests, or the product of a product page.

        Raises:
            CatalogueFormatError: If the home page or the managed services page has no product links.
        """
        if self.PRODUCT_PAGE in response.meta:
            async for item in super().parse(response):
                yield item
            return
        for request in self._page_requests(response):
            yield request
