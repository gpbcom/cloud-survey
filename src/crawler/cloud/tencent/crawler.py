from __future__ import annotations

# Standard Library Imports.
import json
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class TencentCloudCrawler(BaseCloudCrawler):
    """Tencent Cloud (international website) catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root.
        PRODUCTS_URL (ClassVar[str]): The products page, rendered by a script, the main source.
        DOCS_URL (ClassVar[str]): The documentation home page, listing every product documentation.
        CARD_SELECTOR (ClassVar[str]): The product cards of the products page, which are waited for.
        DOCS_WAIT_SELECTOR (ClassVar[str]): The Next.js data of the documentation home page, which is waited for.
        PAGE_WAIT_SELECTOR (ClassVar[str]): The title of a product page, missing from the bot challenge page.
        DOCS_EXCLUDED_GROUPS (ClassVar[FrozenSet[str]]): The documentation groups which are not products.
        DOCS_EXCLUDED_SLUGS (ClassVar[FrozenSet[str]]): The documentation entries which are not products
            (marketplace, SDK, announcements, partners, records, messages).
        SLUG (ClassVar[re.Pattern[str]]): A valid product slug.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the product page titles.
        DOC_URL (ClassVar[str]): The documentation of a product, by documentation id.
        OVERVIEW_SECTION (ClassVar[re.Pattern[str]]): The documentation section holding the product overview.
        OVERVIEW_PAGE (ClassVar[re.Pattern[str]]): The overview article of that section.
        NAME_ALIASES (ClassVar[Dict[str, Tuple[str, ...]]]): The documentation names of products listed under
            another name, by listed name.
        DOC_ID (ClassVar[str]): The meta key holding the documentation id of a product page request.
        DOC_CATALOGUE (ClassVar[str]): The meta key marking a product documentation request, holding the product URL.
        DOC_ARTICLE (ClassVar[str]): The meta key marking an overview article request, holding the product URL.

    Notes:
        Every page, robots.txt included, is first served as an EdgeOne JavaScript challenge, which the stealth
        browser passes by running it: the requests wait for the expected content.
        The main source is the products page cards (`a.v3-product-menu-card-cell-link`: title and description).
        The documentation home page (`__NEXT_DATA__`, `props.pageProps.catalogueList`) completes it: its leaves
        not streamed yet, without the "More" group, the marketplace, the SDK and the private cloud documents, lead to
        the product pages (`/products/<slug>`), named after the documentation entry and described by their meta
        description. The product pages which redirect elsewhere are skipped.
        A missing product page leads to the product documentation (`/document/product/<id>`, Next.js data): its
        overview article (in the "Product Introduction" section) describes the product, by its `description`
        field, else its first paragraph. The product URL is then the product documentation. The products without
        overview article or without description are skipped.
    """

    SITE_URL: ClassVar[str] = "https://www.tencentcloud.com"
    PRODUCTS_URL: ClassVar[str] = f"{SITE_URL}/product"
    DOCS_URL: ClassVar[str] = f"{SITE_URL}/document/product"
    CARD_SELECTOR: ClassVar[str] = "a.v3-product-menu-card-cell-link"
    DOCS_WAIT_SELECTOR: ClassVar[str] = "script#__NEXT_DATA__"
    PAGE_WAIT_SELECTOR: ClassVar[str] = "head > title"
    DOCS_EXCLUDED_GROUPS: ClassVar[FrozenSet[str]] = frozenset({"more"})
    DOCS_EXCLUDED_SLUGS: ClassVar[FrozenSet[str]] = frozenset(
        {"cloudapp", "sdk", "spla", "partner", "living-record", "message"}
    )
    SLUG: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s*\|\s*Tencent Cloud$", re.IGNORECASE)
    DOC_URL: ClassVar[str] = f"{SITE_URL}/document/product/{{doc_id}}"
    OVERVIEW_SECTION: ClassVar[re.Pattern[str]] = re.compile(
        r"^(product )?(introduction|overview)$|^what is", re.IGNORECASE
    )
    OVERVIEW_PAGE: ClassVar[re.Pattern[str]] = re.compile(r"overview|introduction|what is", re.IGNORECASE)
    NAME_ALIASES: ClassVar[Dict[str, Tuple[str, ...]]] = {
        "Cloud Native Database TDSQL-C": ("TDSQL-C for MySQL",),
        "Image Creation": ("Image Creation Large Model",),
        "Cloud DNS Resolution": ("DNSPod",),
    }
    DOC_ID: ClassVar[str] = "doc_id"
    DOC_CATALOGUE: ClassVar[str] = "doc_catalogue"
    DOC_ARTICLE: ClassVar[str] = "doc_article"

    name = "tencent"
    catalogue_url: ClassVar[str] = PRODUCTS_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Tencent Cloud ", "TencentCloud ", "Tencent ", "T-Sec ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _stream(self, product: CloudProduct) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a product not streamed yet, remembering the documentation names it is listed under.

        Args:
            product (CloudProduct): The extracted product.

        Returns:
            Optional[Dict[str, JsonValue]]: The product as a dictionary, `None` when it was already streamed.
        """
        item = super()._stream(product)
        if item is not None:
            self._remember(self.NAME_ALIASES.get(product.name, ()))
        return item

    def _complement_request(self, url: str) -> Request:
        """Build the documentation home page request,
            waiting for its Next.js data once the challenge is passed.

        Args:
            url (str): The documentation home page.

        Returns:
            Request: The request, waiting for the `__NEXT_DATA__` script.
        """
        return Request(url, wait_selector=self.DOCS_WAIT_SELECTOR)

    def _product_page_request(
        self, url: str, name: Optional[str] = None, updated: Optional[str] = None
    ) -> Optional[Request]:
        """Build the request of a product page, waiting for its title once the challenge is passed.

        Args:
            url (str): The absolute product page URL.
            name (Optional[str]): The product name given by the documentation.
            updated (Optional[str]): The last modification of the page given by a sitemap.

        Returns:
            Optional[Request]: The request, `None` when a product of this page was already streamed.
        """
        request = super()._product_page_request(url, name, updated)
        if request is None:
            return None
        return Request(request.url, meta=request.meta, wait_selector=self.PAGE_WAIT_SELECTOR)

    def _product_url(self, href: str) -> Optional[str]:
        """Get the absolute product page URL of a card link, whose double slashes are normalized.

        Args:
            href (str): The card link, e.g. `/products//cvm`.

        Returns:
            Optional[str]: The absolute product page URL, e.g. `https://www.tencentcloud.com/products/cvm`, `None`
                without a path.
        """
        path = re.sub(r"/{2,}", "/", urlparse(href).path)
        return f"{self.SITE_URL}{path}" if path.strip("/") else None

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page cards.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the cards.
        """
        cards = response.css(self.CARD_SELECTOR)
        self.logger.debug("%d product cards in %s.", len(cards), response.url)
        for card in cards:
            title = card.css("h3.v3-product-menu-card-cell-tit").first
            description = card.css("div.v3-product-menu-card-cell-desc").first
            if "v3-link-item" in card.attrib.get("class", "") or title is None:
                self.logger.debug("Skipping the link %s, not a product card.", card.attrib.get("href"))
                continue
            name = title.get_all_text(separator=" ", strip=True)
            text = description.get_all_text(separator=" ", strip=True) if description is not None else None
            if product := self._build_product(name, text, self._product_url(card.attrib.get("href", ""))):
                yield product

    def _docs_leaves(self, node: Dict[str, JsonValue]) -> Iterator[Dict[str, JsonValue]]:
        """Walk the documentation entries without children, depth first.

        Args:
            node (Dict[str, JsonValue]): A documentation group or entry.

        Yields:
            Dict[str, JsonValue]: Each entry without children.
        """
        children = node.get("children")
        if not isinstance(children, list) or not children:
            yield node
            return
        for child in children:
            yield from self._docs_leaves(self._as_object(child))

    def _docs_entries(self, response: Response) -> List[Tuple[str, str, str]]:
        """Read the product entries of the documentation home page, without the excluded groups and entries.

        Args:
            response (Response): The documentation home page.

        Returns:
            List[Tuple[str, str, str]]: The product names, slugs and documentation ids.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `catalogueList` list.
        """
        props = self._as_object(self._next_data(response).get("props"))
        groups = self._as_object(props.get("pageProps")).get("catalogueList")
        if not isinstance(groups, list):
            self.logger.error("The %s documentation page %s has no `catalogueList` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`catalogueList` is not a list")
        entries: List[Tuple[str, str, str]] = []
        for group in map(self._as_object, groups):
            title = self._clean_text(self._as_text(group.get("title")))
            if title.casefold() in self.DOCS_EXCLUDED_GROUPS:
                self.logger.debug("Skipping the documentation group %r, not products.", title)
                continue
            children = group.get("children")
            for child in children if isinstance(children, list) else []:
                for leaf in self._docs_leaves(self._as_object(child)):
                    name = self._clean_text(self._as_text(leaf.get("title")))
                    slug = self._clean_text(self._as_text(leaf.get("slug"))).casefold()
                    link = self._as_text(leaf.get("url")) or ""
                    if slug in self.DOCS_EXCLUDED_SLUGS or "/document/" in link or not self.SLUG.match(slug):
                        self.logger.debug("Skipping the documentation entry %r (%s), not a product.", name, slug)
                        continue
                    entries.append((name, slug, str(leaf.get("id") or "")))
        self.logger.debug("%d product entries in the documentation page %s.", len(entries), response.url)
        return entries

    def _docs_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the documentation entries not streamed yet.

        Args:
            response (Response): The documentation home page.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `catalogueList` list,
                or if it lists no product.
        """
        entries = self._docs_entries(response)
        if not entries:
            self.logger.error("The %s documentation page %s lists no product.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the documentation lists no product")
        requests: List[Request] = []
        for name, slug, doc_id in entries:
            if self._name_key(name) in self.seen_products:
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
                continue
            if request := self._product_page_request(f"{self.SITE_URL}/products/{slug}", name):
                if doc_id:
                    request.meta[self.DOC_ID] = doc_id
                requests.append(request)
        self.logger.info(
            "%d %s product pages to check in the documentation (%d entries).", len(requests), self.name, len(entries)
        )
        return requests

    def _doc_catalogue_request(self, response: Response) -> Request:
        """Request the documentation of a product whose product page is missing.

        Args:
            response (Response): The missing product page, requested with the `DOC_ID` meta.

        Returns:
            Request: The product documentation request (`DOC_CATALOGUE` meta), waiting for its Next.js data.
        """
        url = self.DOC_URL.format(doc_id=response.meta[self.DOC_ID])
        self.logger.debug("The product page %s is missing, reading the documentation %s.", response.url, url)
        meta: Dict[str, JsonValue] = {self.DOC_CATALOGUE: url, self.PRODUCT_NAME: response.meta[self.PRODUCT_NAME]}
        return Request(url, meta=meta, wait_selector=self.DOCS_WAIT_SELECTOR)

    def _page_props(self, response: Response) -> Dict[str, JsonValue]:
        """Read the page properties of a documentation page (Next.js data).

        Args:
            response (Response): The documentation page.

        Returns:
            Dict[str, JsonValue]: The page properties (`props.pageProps`).

        Raises:
            CatalogueFormatError: If the page has no Next.js data.
        """
        return self._as_object(self._as_object(self._next_data(response).get("props")).get("pageProps"))

    def _overview_link(self, sections: JsonValue) -> Optional[str]:
        """Find the overview article in the table of contents of a product documentation.

        Args:
            sections (JsonValue): The top level sections (`data.list`).

        Returns:
            Optional[str]: The overview article path, e.g. `/document/product/1311/83642`, `None` without one.
        """
        for section in map(self._as_object, sections if isinstance(sections, list) else []):
            if not self.OVERVIEW_SECTION.search(self._clean_text(self._as_text(section.get("title")))):
                continue
            children = section.get("children")
            pages = [self._as_object(child) for child in (children if isinstance(children, list) else [])]
            page = next((page for page in pages if self.OVERVIEW_PAGE.search(str(page.get("title")))), section)
            return self._as_text(page.get("link")) or self._as_text(section.get("link"))
        return None

    def _doc_article_request(self, response: Response) -> Optional[Request]:
        """Request the overview article of a product documentation.

        Args:
            response (Response): The product documentation, requested with the `DOC_CATALOGUE` meta.

        Returns:
            Optional[Request]: The overview article request (`DOC_ARTICLE` meta), `None` without overview article.

        Raises:
            CatalogueFormatError: If the page has no Next.js data.
        """
        link = self._overview_link(self._as_object(self._page_props(response).get("data")).get("list"))
        name = response.meta[self.PRODUCT_NAME]
        if link is None:
            self.logger.debug("Skipping %r, its documentation %s has no overview article.", name, response.url)
            return None
        meta: Dict[str, JsonValue] = {self.DOC_ARTICLE: response.meta[self.DOC_CATALOGUE], self.PRODUCT_NAME: name}
        return Request(f"{self.SITE_URL}{link}", meta=meta, wait_selector=self.DOCS_WAIT_SELECTOR)

    def _slate_text(self, node: JsonValue) -> str:
        """Get the text of a rich text node of an article, with its children.

        Args:
            node (JsonValue): The rich text node.

        Returns:
            str: The text of the node.
        """
        fields = self._as_object(node)
        children = fields.get("children")
        texts = [self._slate_text(child) for child in (children if isinstance(children, list) else [])]
        return (self._as_text(fields.get("text")) or "") + "".join(texts)

    def _doc_article_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product described by its overview article.

        Args:
            response (Response): The overview article, requested with the `DOC_ARTICLE` meta.

        Returns:
            Optional[CloudProduct]: The product, with its documentation as URL, `None` without description.

        Raises:
            CatalogueFormatError: If the page has no Next.js data.
        """
        detail = self._as_object(self._page_props(response).get("detailContent"))
        name = str(response.meta[self.PRODUCT_NAME])
        description = self._clean_text(self._as_text(detail.get("description")))
        if not description:
            try:
                nodes: JsonValue = json.loads(self._as_text(detail.get("slate")) or "[]")
            except json.JSONDecodeError:
                nodes = []
            paragraphs = (
                node for node in (nodes if isinstance(nodes, list) else []) if self._as_object(node).get("type") == "p"
            )
            description = next((text for node in paragraphs if (text := self._clean_text(self._slate_text(node)))), "")
        if not description:
            self.logger.debug("Skipping %r, its overview article %s has no description.", name, response.url)
            return None
        return self._build_product(name, description, str(response.meta[self.DOC_ARTICLE]))

    def _page_title(self, title: str) -> str:
        """Clean a product page title: without the brand suffix.

        Args:
            title (str): The page title, e.g. `Cloud Virtual Machine | Tencent Cloud`.

        Returns:
            str: The product name, e.g. `Cloud Virtual Machine`.
        """
        return self._clean_text(self.TITLE_SUFFIX.sub("", self._clean_text(title)))

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page from its title, as its first heading is the brand.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has no title.
        """
        title = self._clean_text(response.css("head > title::text").get())
        return self._page_title(title) or None

    def _page_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a product page, skipping the missing pages.

        Args:
            response (Response): The product page, requested with the `PRODUCT_PAGE` meta.

        Returns:
            Optional[CloudProduct]: The product, `None` for a missing, redirected or invalid product page.
        """
        if response.status >= 400:
            self.logger.debug("Skipping %s, missing page (HTTP %s).", response.url, response.status)
            return None
        return super()._page_product(response)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the products page, waiting for its cards once the challenge is passed.

        Yields:
            Request: The products page request, then the documentation home page one (lower priority).
        """
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield Request(self.catalogue_url, priority=self.PRIMARY_PRIORITY, wait_selector=self.CARD_SELECTOR)
        for url in self.complement_urls:
            self.logger.debug("Requesting the %s complementary catalogue page %s.", self.name, url)
            yield self._complement_request(url)

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page cards.

        Args:
            response (Response): The products page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the card products, request the documentation product pages, or stream a product page.

        The product pages are read by the base crawler. A missing product page leads to the product documentation,
        which leads to its overview article.

        Args:
            response (Response): The products page, the documentation home page, a product page, a product
                documentation or an overview article.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If the documentation page has no catalogue or lists no product,
                or if a product documentation page has no Next.js data.
        """
        if self.DOC_CATALOGUE in response.meta:
            if (request := self._doc_article_request(response)) is not None:
                yield request
            return
        if self.DOC_ARTICLE in response.meta:
            if (product := self._doc_article_product(response)) and (streamed := self._stream(product)) is not None:
                yield streamed
            return
        if self.DOC_ID in response.meta and response.status >= 400:
            yield self._doc_catalogue_request(response)
            return
        if self.PRODUCT_PAGE not in response.meta and urlparse(response.url).path.startswith("/document/"):
            for request in self._docs_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
