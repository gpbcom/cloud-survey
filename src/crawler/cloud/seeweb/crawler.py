from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HtmlAttribute
from crawler.exception import EmptyCatalogueError


class SeewebCrawler(BaseCloudCrawler):
    """Seeweb catalogue crawler.

    Attributes:
        MENU_COLUMNS (ClassVar[str]): The CSS selector of the products menu columns.
        MENU_LINKS (ClassVar[str]): The CSS selector of the links of a products menu column.
        PRODUCT_PATH (ClassVar[re.Pattern[str]]): The path of a product page, e.g. `/en/products/cloud-server`.
        INTRO_TEXT (ClassVar[str]): The CSS selector of the introduction paragraphs of a product page (the two
            page layouts).
        SPACE_BEFORE_PUNCTUATION (ClassVar[re.Pattern[str]]): The space left before a punctuation mark when the
            texts of the introduction elements are joined.
        SENTENCE_END (ClassVar[re.Pattern[str]]): The end of a sentence, where a too long introduction is cut.
        MAX_DESCRIPTION (ClassVar[int]): The maximum length of a product description, in characters.

    Notes:
        The main source is the products menu of the https://www.seeweb.it/en home page: its columns (Compute,
        Services, Storage, Dedicated Infrastructures, Security) list the product names and links only. Each product
        page is read for its description, the product name being the menu label: its English introduction
        paragraph (cut at a sentence end when too long), else its meta description, often written in Italian. The
        solution pages are skipped. The catalogue categories of a product are the titles of the menu columns
        listing it (e.g. `Services`).
    """

    MENU_COLUMNS: ClassVar[str] = "div.product-column"
    MENU_LINKS: ClassVar[str] = "ul li a"
    PRODUCT_PATH: ClassVar[re.Pattern[str]] = re.compile(r"^/en/products/[^/]+/?$")
    INTRO_TEXT: ClassVar[str] = ".cont-title p, div.title > p"
    SPACE_BEFORE_PUNCTUATION: ClassVar[re.Pattern[str]] = re.compile(r"\s+(?=[.,:!?)])")
    SENTENCE_END: ClassVar[re.Pattern[str]] = re.compile(r"[.!?](?=\s|$)")
    MAX_DESCRIPTION: ClassVar[int] = 1000

    name = "seeweb"
    catalogue_url: ClassVar[str] = "https://www.seeweb.it/en"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Seeweb ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _shorten(self, text: str) -> str:
        """Cut a too long description at its last sentence end within the maximum length.

        Args:
            text (str): The description.

        Returns:
            str: The description, whole when short enough, else its first sentences, else its first words
                followed by an ellipsis.
        """
        if len(text) <= self.MAX_DESCRIPTION:
            return text
        head = text[: self.MAX_DESCRIPTION]
        ends = [match.end() for match in self.SENTENCE_END.finditer(head)]
        shortened = head[: ends[-1]] if ends else f"{head[: self.MAX_DESCRIPTION - 1].rsplit(' ', 1)[0]}\u2026"
        self.logger.debug("Description cut from %d to %d characters.", len(text), len(shortened))
        return shortened

    def _introduction(self, response: Response) -> Optional[str]:
        """Read the introduction of a product page: its first non-empty paragraph below the heading.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The introduction, cut at a sentence end when too long, `None` when the page has none.
        """
        for paragraph in response.css(self.INTRO_TEXT):
            text = self.SPACE_BEFORE_PUNCTUATION.sub("", self._clean_text(paragraph.get_all_text(separator=" ")))
            if text:
                return self._shorten(text)
        return None

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its English introduction, else its meta description.

        The meta descriptions of the English pages are often written in Italian.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        return self._introduction(response) or super()._page_description(response)

    def _menu_entries(self, response: Response) -> Dict[str, Tuple[str, str, List[str]]]:
        """Read the product links of the products menu, once per product page, with the titles of their columns.

        Args:
            response (Response): The home page.

        Returns:
            Dict[str, Tuple[str, str, List[str]]]: The product page URL, menu label and column titles, by URL key, in
                the menu order.
        """
        entries: Dict[str, Tuple[str, str, List[str]]] = {}
        for column in response.css(self.MENU_COLUMNS):
            heading = column.css(":scope > p").first
            title = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
            links = column.css(self.MENU_LINKS)
            self.logger.debug("%d links in the products menu column %r of %s.", len(links), title, response.url)
            for link in links:
                label = self._clean_text(link.get_all_text(separator=" ", strip=True))
                url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
                path = urlparse(url).path
                if "/solutions/" in path or not self.PRODUCT_PATH.match(path):
                    self.logger.debug("Skipping the menu entry %r (%s), not a product page.", label, url)
                    continue
                if not label:
                    self.logger.debug("Skipping the menu entry %s, unnamed.", url)
                    continue
                if (key := self._url_key(url)) in entries:
                    self.logger.debug("The menu entry %r (%s) is listed again, under %r.", label, url, title)
                    entries[key][2].append(title)
                    continue
                entries[key] = (url, label, [title])
        return entries

    def _menu_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the products menu, in order and without duplicates.

        Args:
            response (Response): The home page.

        Returns:
            List[Request]: The product page requests, named after the menu labels, with their menu columns.

        Raises:
            EmptyCatalogueError: If the menu links to no product page.
        """
        entries = self._menu_entries(response)
        requests: List[Request] = []
        for url, label, categories in entries.values():
            labels = [category for category in categories if category]
            if (request := self._product_page_request(url, label, categories=labels)) is not None:
                requests.append(request)
        if not entries:
            self.logger.error("The %s products menu of %s links to no product page.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        self.logger.info("%d %s product pages to read from the products menu.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the products menu, or stream the product of a product page.

        Args:
            response (Response): The home page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests, or the product not streamed yet.

        Raises:
            EmptyCatalogueError: If the products menu links to no product page.
        """
        if self.PRODUCT_PAGE not in response.meta:
            for request in self._menu_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
