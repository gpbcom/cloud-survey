from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.aruba.enums import ArubaMenuMarkup, ArubaPricingCardName
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HtmlAttribute
from models.cloud.products.product import CloudProduct


class ArubaCloudCrawler(BaseCloudCrawler):
    """Aruba Cloud catalogue crawler.

    Attributes:
        PRICING_URL (ClassVar[str]): The pricing page, listing the products by family.
        PRICING_ALIASES (ClassVar[Dict[str, str]]): The menu name of each pricing card (`ArubaPricingCardName`)
            naming a product otherwise.
        ITALIAN_WORDS (ClassVar[re.Pattern[str]]): Common Italian words, revealing an untranslated menu description.
        HTML_TAG (ClassVar[re.Pattern[str]]): An HTML tag left in a meta description, e.g. `<br/>`.
        MENU_ITEM (ClassVar[ArubaMenuMarkup]): The class of the menu items, whose links label the menu groups.
        untranslated (List[Tuple[str, str, List[str]]]): The product pages (URL, menu name and menu categories) of
            the menu entries described in Italian, to read for their English description.

    Notes:
        The main source is the products menu of the https://www.arubacloud.com/ home page: its links holding a
        description (`span.description`) are the products, with a name (`strong`), once the solution pages are
        filtered out. The product cards of the pricing page (a name and a description) complete it with the products
        missing from the menu. Some pricing cards name a menu product differently (e.g. `Server Bare Metal` for
        `Dedicated Servers`): they are renamed after the menu product, so that they are recognized as duplicates.
        A few menu descriptions are left in Italian: those products are read from their (English) product page
        instead, named after the menu label, with the page meta description.
        The catalogue categories of a menu product are the labels of the menu items holding it: its top menu (e.g.
        `Public Cloud`), then its menu group (e.g. `Container`), gathered over all the menu entries of the product.
        Those of a pricing card are the title of its pricing family section (e.g. `Public Cloud`).
    """

    PRICING_URL: ClassVar[str] = "https://www.arubacloud.com/pricing"
    PRICING_ALIASES: ClassVar[Dict[str, str]] = {
        ArubaPricingCardName.SERVER_BARE_METAL: "Dedicated Servers",
        ArubaPricingCardName.VIRTUAL_PRIVATE_SERVERS: "VPS - Virtual Private Server",
        ArubaPricingCardName.BACKUP_AGENTLESS: "Agentless Backup",
        ArubaPricingCardName.DISASTER_RECOVERY: "Disaster Recovery for VMware",
        ArubaPricingCardName.CLOUD_BARE_METAL_BACKUP: "Backup for VMware",
        ArubaPricingCardName.AI_TOOLS_TEXT_MANAGEMENT: "AI Tools",
    }
    ITALIAN_WORDS: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:il|della|delle|dei|degli|con|e|sviluppato|privato|connetti|ambienti|infrastrutture|semplice|modo)\b",
        re.IGNORECASE,
    )
    HTML_TAG: ClassVar[re.Pattern[str]] = re.compile(r"<[^>]*>")
    MENU_ITEM: ClassVar[ArubaMenuMarkup] = ArubaMenuMarkup.NAV_ITEM

    name = "aruba"
    catalogue_url: ClassVar[str] = "https://www.arubacloud.com/"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRICING_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Aruba Cloud ", "Aruba ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.untranslated: List[Tuple[str, str, List[str]]] = []

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page, without the HTML tags some meta descriptions hold.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        description = super()._page_description(response)
        return self._clean_text(self.HTML_TAG.sub(" ", description)) if description else None

    def _is_italian(self, text: str) -> bool:
        """Tell whether a menu description is written in Italian (at least two common Italian words).

        Args:
            text (str): The menu description.

        Returns:
            bool: Whether the description is in Italian.
        """
        return len(self.ITALIAN_WORDS.findall(text)) >= 2

    def _menu_categories(self, link: Selector) -> List[str]:
        """Read the menu categories of a menu link: the labels of the menu items holding its own item.

        Args:
            link (Selector): The menu link.

        Returns:
            List[str]: The labels, the top menu first, e.g. `["Public Cloud", "Container"]`, empty out of a menu.
        """
        labels: List[str] = []
        node = link.parent
        own_item = True
        while node is not None:
            if (
                node.tag == ArubaMenuMarkup.LIST_ITEM
                and self.MENU_ITEM in node.attrib.get(HtmlAttribute.CLASS, "").split()
            ):
                label = node.css(":scope > a").first
                if not own_item and label is not None:
                    labels.insert(0, self._clean_text(label.get_all_text(separator=" ", strip=True)))
                own_item = False
            node = node.parent
        return labels

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menu: the links with a description, except the solutions.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once, with the menu categories of all its entries.

        Notes:
            A product listed by several menu groups (e.g. `Hybrid Connect`) is read from its first entry.
        """
        links = response.css("a.nav-link")
        self.logger.debug("%d menu links in %s.", len(links), response.url)
        entries: Dict[str, Tuple[Optional[str], str, str, List[str]]] = {}
        for link in links:
            description = link.css("span.description").first
            if description is None:
                continue
            heading = link.css("strong").first
            name = str(heading.get_all_text(separator=" ", strip=True)) if heading is not None else None
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if "/solutions/" in urlparse(url).path:
                self.logger.debug("Skipping the menu entry %r (%s), a solution page.", name, url)
                continue
            text = self._clean_text(description.get_all_text(separator=" ", strip=True))
            key = self._name_key(name) if name and self._clean_text(name) else url
            categories = self._menu_categories(link)
            if key in entries:
                self.logger.debug("The menu entry %r is listed again, under %s.", name, categories)
                entries[key][3].extend(categories)
                continue
            entries[key] = (name, text, url, categories)
        for name, text, url, categories in entries.values():
            if name and self._is_italian(text):
                self.logger.debug("The menu entry %r is described in Italian, reading its page %s.", name, url)
                self.untranslated.append((url, self._clean_text(name), categories))
                continue
            if product := self._build_product(name, text, url, categories=categories):
                yield product

    def _untranslated_requests(self) -> List[Request]:
        """Request the product pages of the menu entries described in Italian, once.

        Returns:
            List[Request]: The product page requests, named after the menu labels, with their menu categories.
        """
        pages, self.untranslated = self.untranslated, []
        requests: List[Request] = []
        for url, name, categories in pages:
            if (request := self._product_page_request(url, name, categories=categories)) is not None:
                requests.append(request)
        if requests:
            self.logger.info("%d %s product pages to read for an English description.", len(requests), self.name)
        return requests

    def _pricing_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the product cards of the pricing page: the card bodies holding a heading.

        Args:
            response (Response): The pricing page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, renamed after the menu product when aliased, once, with
                the pricing families of all its cards.
        """
        entries: Dict[str, Tuple[str, Optional[str], Optional[str], List[str]]] = {}
        for section in response.css("section"):
            title = section.css("h2").first
            family = self._clean_text(title.get_all_text(separator=" ", strip=True)) if title is not None else ""
            cards = section.css("div.card-body")
            self.logger.debug("%d pricing card bodies in the family %r of %s.", len(cards), family, response.url)
            for card in cards:
                heading = card.css(":scope > h3").first
                if heading is None:
                    continue
                name = self._clean_text(heading.get_all_text(separator=" ", strip=True))
                if alias := self.PRICING_ALIASES.get(name):
                    self.logger.debug("The pricing card %r is the menu product %r.", name, alias)
                    name = alias
                key = self._name_key(name) if name else ""
                if key in entries:
                    entries[key][3].append(family)
                    continue
                description = card.css("p").first
                link = card.css("a[href]").first
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, "")) if link is not None else None
                text = str(description.get_all_text(separator=" ", strip=True)) if description is not None else None
                entries[key] = (name, text, url, [family])
        for name, text, url, families in entries.values():
            if product := self._build_product(name, text, url, categories=families):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the home page menu or of the pricing page.

        Args:
            response (Response): The home page or the pricing page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if urlparse(response.url).path.rstrip("/") == urlparse(self.PRICING_URL).path:
            return self._pricing_products(response)
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of the menu or of the pricing page, or the product of a product page.

        Args:
            response (Response): The home page, the pricing page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            EmptyCatalogueError: If the home page or the pricing page holds no product.
        """
        async for item in super().parse(response):
            yield item
        for request in self._untranslated_requests():
            yield request
