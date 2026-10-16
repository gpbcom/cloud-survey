from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, Optional, Tuple, Union
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

# Third Party Imports.
from patchright.async_api import Page, Route
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class AWSCrawler(BaseCloudCrawler):
    """Amazon Web Services catalogue crawler.

    Attributes:
        API_URL (ClassVar[str]): The directory search API.
        PAGE_SIZE (ClassVar[int]): The products read per page.
        QUERY (ClassVar[Dict[str, str]]): The directory search parameters, page number excluded.
        DOCS_URL (ClassVar[str]): The documentation home page, listing every service documentation.
        DOCS_EXCLUDED_SECTIONS (ClassVar[FrozenSet[str]]): The documentation sections which are not services.
        DOCS_NOT_SERVICE (ClassVar[re.Pattern[str]]): The documentation entries which are not services.
        DOCS_HOST (ClassVar[str]): The documentation host, whose first path segment is the service slug.
        DOCS_APP_SCRIPT (ClassVar[str]): The script replacing the server-rendered documentation list in a browser.

    Notes:
        The main source is the JSON directory API behind the https://aws.amazon.com/products/ page, read page after
        page. A directory entry gives the product launch date (`additionalFields.publishedDate`) and its last update
        (`dateUpdated`), not `dateCreated`, which is the same migration date for every entry. The documentation home
        page completes it with the services missing from the directory, undated. A service
        documentation (`docs.aws.amazon.com/ec2/...`) matches the product page of the same slug (`/ec2/`).
        In a browser, a script replaces the full server-rendered documentation list by collapsed panels: it is not
        loaded, so that the list stays complete.
    """

    API_URL: ClassVar[str] = "https://aws.amazon.com/api/dirs/items/search"
    PAGE_SIZE: ClassVar[int] = 500
    QUERY: ClassVar[Dict[str, str]] = {
        "item.directoryId": "products-cards-interactive-aws-products-ams",
        "item.locale": "en_US",
        "sort_by": "item.additionalFields.title",
        "sort_order": "asc",
        "size": str(PAGE_SIZE),
    }
    DOCS_URL: ClassVar[str] = "https://docs.aws.amazon.com/"
    DOCS_EXCLUDED_SECTIONS: ClassVar[FrozenSet[str]] = frozenset(
        {"decision_guides", "sdktoolkits", "genref", "addtlrcs", "featuredsvcs", "console", "custenable"}
    )
    DOCS_NOT_SERVICE: ClassVar[re.Pattern[str]] = re.compile(
        r"^Choosing|\?$|SDK for|Toolkit for|Tools for|Guide$|Reference", re.IGNORECASE
    )
    DOCS_HOST: ClassVar[str] = "docs.aws.amazon.com"
    DOCS_APP_SCRIPT: ClassVar[str] = "**/awsdocs-main-landing-page*.js"

    name = "aws"
    catalogue_url: ClassVar[str] = f"{API_URL}?{urlencode({**QUERY, 'page': 0})}"
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Amazon ", "AWS ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare a service documentation with the product page of the same slug.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The product page key of the service slug for the documentation pages (`docs.aws.amazon.com/ec2/...`
                is compared as `aws.amazon.com/ec2`), the generic URL key otherwise.
        """
        link = urlparse(url.casefold())
        slug = link.path.strip("/").split("/")[0]
        if link.netloc == self.DOCS_HOST and slug:
            return f"aws.amazon.com/{slug}"
        return super()._url_key(url)

    async def _abort(self, route: Route) -> None:
        """Abort a browser request.

        Args:
            route (Route): The intercepted browser request.
        """
        await route.abort()

    async def _keep_server_rendered_list(self, page: Page) -> None:
        """Block the documentation page script, before navigation, so that its full list is kept.

        Args:
            page (Page): The browser page.
        """
        await page.route(self.DOCS_APP_SCRIPT, self._abort)

    def _complement_request(self, url: str) -> Request:
        """Build the documentation home page request, without the script hiding its full list.

        Args:
            url (str): The documentation home page.

        Returns:
            Request: The request, blocking the documentation page script.
        """
        return Request(url, page_setup=self._keep_server_rendered_list)

    def _html_to_text(self, fragment: Optional[str]) -> Optional[str]:
        """Get the text of an HTML fragment, as some descriptions are HTML paragraphs.

        Args:
            fragment (Optional[str]): The HTML fragment.

        Returns:
            Optional[str]: The fragment text, `None` when missing.
        """
        if fragment is None:
            return None
        return Selector(f"<div>{fragment}</div>").get_all_text(separator=" ", strip=True)

    def _product_link(self, link: Optional[str]) -> Optional[str]:
        """Get the absolute URL of a product page, ignoring the links without a product slug (e.g. `#`).

        Args:
            link (Optional[str]): The raw product link.

        Returns:
            Optional[str]: The absolute product URL, `None` without a product slug.
        """
        url = urljoin("https://aws.amazon.com/", link or "")
        return url if urlparse(url).path.strip("/") else None

    def _catalogue_page(self, response: Response) -> Dict[str, JsonValue]:
        """Read a catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Dict[str, JsonValue]: The page data.

        Raises:
            CatalogueFormatError: If the page is not a JSON object.
        """
        try:
            data: JsonValue = response.json()
        except ValueError as e:
            self.logger.error("The %s catalogue page %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the page is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The %s catalogue page %s is not a JSON object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page is not a JSON object")
        return data

    def _next_page_url(self, response: Response) -> Optional[str]:
        """Get the URL of the next catalogue page.

        Args:
            response (Response): The current catalogue page.

        Returns:
            Optional[str]: The next page URL, `None` on the last page.
        """
        total = self._as_object(self._catalogue_page(response).get("metadata")).get("totalHits")
        page = int(parse_qs(urlparse(response.url).query).get("page", ["0"])[0])
        if not isinstance(total, int) or (page + 1) * self.PAGE_SIZE >= total:
            self.logger.debug("Page %d is the last catalogue page (%s products in total).", page, total)
            return None
        return f"{self.API_URL}?{urlencode({**self.QUERY, 'page': page + 1})}"

    def _directory_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a directory page.

        Args:
            response (Response): The directory page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.

        Raises:
            CatalogueFormatError: If the page has no `items` list.
        """
        items = self._catalogue_page(response).get("items")
        if not isinstance(items, list):
            self.logger.error("The %s catalogue page %s has no `items` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`items` is not a list")
        self.logger.debug("%d catalogue entries in %s.", len(items), response.url)
        for entry in items:
            data = self._as_object(self._as_object(entry).get("item"))
            fields = self._as_object(data.get("additionalFields"))
            name = self._as_text(fields.get("title"))
            description = self._html_to_text(self._as_text(fields.get("body")))
            url = self._product_link(self._as_text(fields.get("ctaLink")))
            added_at = self._parse_date(fields.get("publishedDate"), name)
            updated_at = self._parse_date(data.get("dateUpdated"), name)
            if product := self._build_product(name, description, url, added_at, updated_at):
                yield product

    def _docs_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the services of the documentation home page, skipping the guides, SDKs and tools sections.

        Args:
            response (Response): The documentation home page.

        Yields:
            Iterator[CloudProduct]: Each valid service of the page.
        """
        cards = response.css("li.awsdocs-card-list-item")
        self.logger.debug("%d documentation entries in %s.", len(cards), response.url)
        for card in cards:
            link = card.css("a.awsdocs-link").first
            abstract = card.css(".awsdocs-card-list-abstract").first
            if link is None or abstract is None:
                continue
            href = link.attrib.get("href", "")
            section = parse_qs(urlparse(href).query).get("icmpid", [""])[0].removeprefix("docs_homepage_")
            name = self._clean_text(link.get_all_text(separator=" ", strip=True))
            if section in self.DOCS_EXCLUDED_SECTIONS or self.DOCS_NOT_SERVICE.search(name):
                self.logger.debug("Skipping the documentation entry %r (%s), not a service.", name, section)
                continue
            description = abstract.get_all_text(separator=" ", strip=True)
            if product := self._build_product(name, description, urljoin(response.url, href)):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a directory page or of the documentation home page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If a directory page has no `items` list.
        """
        if urlparse(response.url).netloc == self.DOCS_HOST:
            return self._docs_products(response)
        return self._directory_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a catalogue page, then request the next directory page if any.

        Args:
            response (Response): The catalogue page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the next page request.
        """
        async for item in super().parse(response):
            yield item
        if urlparse(response.url).netloc == self.DOCS_HOST:
            return
        if next_url := self._next_page_url(response):
            self.logger.info("Requesting the next %s catalogue page %s.", self.name, next_url)
            yield Request(next_url, priority=self.PRIMARY_PRIORITY)
