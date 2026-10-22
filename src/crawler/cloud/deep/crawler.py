from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.deep.enums import DEEPMenuGroup
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class DEEPCrawler(BaseCloudCrawler):
    """DEEP (POST Luxembourg) catalogue crawler.

    Attributes:
        MENU_LINKS (ClassVar[str]): The CSS selector of the services menu links.
        SERVICE_PATH (ClassVar[re.Pattern[str]]): The path of a service page, below its category page.
        NOT_PRODUCT (ClassVar[re.Pattern[str]]): The service menu links which are not products (contract renewal,
            network outlook).
        HERO_TEXT (ClassVar[str]): The CSS selector of the introduction paragraphs of a service page.
        MENU_GROUPS (ClassVar[str]): The CSS selector of the category groups of the services menu.
        MENU_GROUP_TITLE (ClassVar[str]): The CSS selector of the category title of a menu group.
        MENU_SUB_GROUPS (ClassVar[str]): The CSS selector of the sub-category groups (accordions) of a menu group.
        MENU_SUB_GROUP_TITLE (ClassVar[str]): The CSS selector of the sub-category title of an accordion.
        NOT_CATEGORY_GROUPS (ClassVar[FrozenSet[DEEPMenuGroup]]): The menu groups which are not categories (the SME
            packs).

    Notes:
        The main source is the product cards of the https://www.deep.eu/en/accueil/services/cloud page (name,
        description and link). The services menu of the same page completes it with the whole catalogue: every
        category (Cloud, Cybersecurity, Data & AI, Customer Infrastructure, Datacenter, Telecom) links to its service
        pages, read for their description (introduction paragraph, else meta description), the product name being
        the menu label (the Open Graph titles of the website are all the same). The category overviews, the SME
        pages and the resources (blog, case studies) are skipped. The menu groups the services by category (e.g.
        `Cloud`) and sub-category (e.g. `Managed Services`): a product gets the categories of every menu place of its
        page, a product card without menu entry the category of the cloud services page itself.
    """

    MENU_LINKS: ClassVar[str] = "a.menu_final_link"
    SERVICE_PATH: ClassVar[re.Pattern[str]] = re.compile(r"^/en/accueil/services/[^/]+/[^?#]+$")
    NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"/reengagement|/reseaux-du-futur", re.IGNORECASE)
    HERO_TEXT: ClassVar[str] = ".jumbotron-text-wrapper p"
    MENU_GROUPS: ClassVar[str] = "div.navigation-level-2-wrapper"
    MENU_GROUP_TITLE: ClassVar[str] = ".navigation-level-header .title"
    MENU_SUB_GROUPS: ClassVar[str] = "li.navigation-collapse"
    MENU_SUB_GROUP_TITLE: ClassVar[str] = "button.btn-collapse"
    NOT_CATEGORY_GROUPS: ClassVar[FrozenSet[DEEPMenuGroup]] = frozenset({DEEPMenuGroup.OUR_SERVICES})

    name = "deep"
    catalogue_url: ClassVar[str] = "https://www.deep.eu/en/accueil/services/cloud"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("DEEP ", "POST ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a service page: its introduction, else its meta description.

        Args:
            response (Response): The service page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        for paragraph in response.css(self.HERO_TEXT):
            if text := self._clean_text(paragraph.get_all_text(separator=" ", strip=True)):
                return text
        return super()._page_description(response)

    def _title(self, element: Selector, selector: str) -> str:
        """Read the text of the first element matching a CSS selector within an element.

        Args:
            element (Selector): The element.
            selector (str): The CSS selector.

        Returns:
            str: The text, empty when no element matches.
        """
        match = element.css(selector).first
        return self._clean_text(match.get_all_text(separator=" ", strip=True)) if match is not None else ""

    def _menu_categories(self, response: Response) -> Dict[str, List[str]]:
        """Gather the categories and sub-categories of the services menu links, by page (`_url_key`).

        Args:
            response (Response): The cloud services page, holding the services menu.

        Returns:
            Dict[str, List[str]]: The labels of each linked page, in menu order.
        """
        categories: Dict[str, List[str]] = {}
        for group in response.css(self.MENU_GROUPS):
            category = self._title(group, self.MENU_GROUP_TITLE)
            if category in self.NOT_CATEGORY_GROUPS:
                self.logger.debug("Skipping the menu group %r of %s, not a category.", category, response.url)
                continue
            sub_categories: Dict[str, str] = {}
            for sub_group in group.css(self.MENU_SUB_GROUPS):
                sub_category = self._title(sub_group, self.MENU_SUB_GROUP_TITLE)
                for link in sub_group.css(self.MENU_LINKS):
                    sub_categories[self._url_key(urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")))] = (
                        sub_category
                    )
            for link in group.css(self.MENU_LINKS):
                key = self._url_key(urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")))
                categories.setdefault(key, []).extend([category, sub_categories.get(key, "")])
        self.logger.debug("%d categorized menu links in %s.", len(categories), response.url)
        return categories

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the cloud services page.

        Args:
            response (Response): The cloud services page.

        Yields:
            Iterator[CloudProduct]: Each valid product card.
        """
        cards = response.css("div.card-product")
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        categories = self._menu_categories(response)
        page_categories = categories.get(self._url_key(response.url), [])
        for card in cards:
            heading = card.css("h3").first
            description = card.css("p").first
            if heading is None or description is None:
                self.logger.debug("Skipping a product card without name or description.")
                continue
            link = card.css("a.stretched-link").first
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) if link is not None else None
            name = heading.get_all_text(separator=" ", strip=True)
            labels = categories.get(self._url_key(url), page_categories) if url else page_categories
            if product := self._build_product(
                name, description.get_all_text(separator=" ", strip=True), url, categories=labels
            ):
                yield product

    def _menu_requests(self, response: Response) -> List[Request]:
        """Request the service pages of the services menu, in order and without duplicates.

        Args:
            response (Response): The cloud services page, holding the services menu.

        Returns:
            List[Request]: The service page requests, named after the menu labels, filed under their menu
                categories (`PRODUCT_CATEGORIES` meta).
        """
        links = response.css(self.MENU_LINKS)
        categories = self._menu_categories(response)
        requests: List[Request] = []
        requested: Set[str] = set()
        for link in links:
            label = self._clean_text(link.get_all_text(separator=" ", strip=True))
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            path = urlparse(url).path
            if not self.SERVICE_PATH.match(path) or self.NOT_PRODUCT.search(path):
                self.logger.debug("Skipping the menu entry %r (%s), not a service page.", label, url)
                continue
            if not label or self._url_key(url) in requested:
                self.logger.debug("Skipping the menu entry %r (%s), unnamed or already listed.", label, url)
                continue
            requested.add(self._url_key(url))
            labels = categories.get(self._url_key(url), [])
            if (request := self._product_page_request(url, label, categories=labels)) is not None:
                requests.append(request)
        self.logger.info(
            "%d %s service pages to read from the services menu (%d links).", len(requests), self.name, len(links)
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the cloud services page.

        Args:
            response (Response): The cloud services page.

        Returns:
            Iterator[CloudProduct]: The valid product cards.
        """
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the cloud product cards then request the services menu pages, or stream a service page product.

        Args:
            response (Response): The cloud services page or a service page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the service page requests.

        Raises:
            EmptyCatalogueError: If the cloud services page holds no product card.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta:
            for request in self._menu_requests(response):
                yield request
