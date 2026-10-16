from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import quote, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct

# A menu product: its name, description (`None` for a placeholder), page URL and type (page template slug).
MenuEntry = Tuple[Optional[str], Optional[str], str, Optional[str]]


class ChinaMobileCloudCrawler(BaseCloudCrawler):
    """China Mobile Cloud (移动云, ecloud) catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the relative product links being relative to it.
        PRODUCT_URL (ClassVar[str]): The product page of a product type, when the menu gives no link.
        TEMPLATE_URL (ClassVar[str]): The JSON template of a product page, holding its SEO description.
        TEMPLATE_PRODUCT (ClassVar[str]): The meta key of a template request, holding the product page URL.
        PROMO_NODE (ClassVar[str]): The type of the menu nodes holding promotions, not products.
        CO_BRANDED_NODE (ClassVar[str]): The name of the co-branded menu node, processed last.
        PLACEHOLDER (ClassVar[re.Pattern[str]]): The placeholder descriptions of some menu entries.
        PARENTHESES (ClassVar[re.Pattern[str]]): The parentheses (ASCII or fullwidth) around the edition of a product.
        fetch_retries (ClassVar[int]): How many times a failed fetch is attempted: the website drops connections.
        retry_delay (ClassVar[float]): The delay between two attempts, in seconds, long enough for a ban to expire.
        download_delay (float): The delay between two requests, in seconds: the website bans the faster clients.

    Notes:
        The website is a JavaScript application. The main source is its public products menu, a JSON document
        (https://ecloud.10086.cn/api/query/menu/v4/menu/tree?situationCode=product): a tree of nodes (`bindData`,
        then `children`) whose products are the `bindMetadatas` of every level. A product is described by its
        `sDesc`, else by its `brief` when `sDesc` is a placeholder (`...介绍页`, `...菜单`). Its page is its
        `introduceUrl`, else `/portal/product/{type}`. The promotion nodes (`card`) and the entries without type nor
        link are not products. The recommended products are listed again in their category: they are streamed once
        (same identifier, name or link). The co-branded 和云 node (`heyun.cmecloud.cn` pages) is part of the menu and
        processed last. A product with only a placeholder is described by the SEO description of its page template
        (one more JSON request). Products only differ by their edition between parentheses, e.g. `云电脑(办公型)`
        and `云电脑(行业型)`: the edition is kept when comparing names. The website drops the connections and bans
        the clients above about one request per second: the crawler is slow and only reads JSON documents. The names
        and descriptions are in Chinese.
    """

    SITE_URL: ClassVar[str] = "https://ecloud.10086.cn/"
    PRODUCT_URL: ClassVar[str] = "https://ecloud.10086.cn/portal/product/{slug}"
    TEMPLATE_URL: ClassVar[str] = (
        "https://ecloud.10086.cn/api/query/template-delivery/application/detail?group=product-gray&type={slug}"
    )
    TEMPLATE_PRODUCT: ClassVar[str] = "template_product"
    PROMO_NODE: ClassVar[str] = "card"
    CO_BRANDED_NODE: ClassVar[str] = "和云"
    PLACEHOLDER: ClassVar[re.Pattern[str]] = re.compile(r"介绍页|菜单")
    PARENTHESES: ClassVar[re.Pattern[str]] = re.compile(r"[()\uff08\uff09]")

    name = "ecloud"
    catalogue_url: ClassVar[str] = "https://ecloud.10086.cn/api/query/menu/v4/menu/tree?situationCode=product"
    name_prefixes: ClassVar[Tuple[str, ...]] = ("移动云", "中国移动", "和云")
    fetch_retries: ClassVar[int] = 4
    retry_delay: ClassVar[float] = 60.0
    download_delay: float = 3.0

    ############################
    # Internal Helpers Methods #
    ############################

    def _name_key(self, name: str) -> str:
        """Normalize a product name to compare it, keeping its edition between parentheses.

        Args:
            name (str): The product name, e.g. `云电脑(办公型)`.

        Returns:
            str: The comparison key, e.g. `云电脑办公型`, distinct from the `云电脑` one.
        """
        return super()._name_key(self.PARENTHESES.sub(" ", name))

    def _url_key(self, url: str) -> str:
        """Compare the co-branded pages by their route, a URL fragment (`heyun.cmecloud.cn/#/product/vm`).

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, followed by the fragment route if any.
        """
        route = urlparse(url.casefold()).fragment
        key = super()._url_key(url)
        return f"{key}#{route.rstrip('/')}" if route.startswith("/") else key

    def _json_object(self, response: Response) -> Dict[str, JsonValue]:
        """Read a JSON object response, the menu or a page template.

        Args:
            response (Response): The JSON response.

        Returns:
            Dict[str, JsonValue]: The JSON object.

        Raises:
            CatalogueFormatError: If the response is empty (dropped connection), not JSON or not a JSON object.
        """
        data = self._json_body(response)
        if not isinstance(data, dict):
            self.logger.error("The %s page %s is not a JSON object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page is not a JSON object")
        return data

    def _menu_nodes(self, response: Response) -> List[JsonValue]:
        """Read the top nodes of the products menu, the co-branded node last.

        Args:
            response (Response): The products menu.

        Returns:
            List[JsonValue]: The top menu nodes.

        Raises:
            CatalogueFormatError: If the response is not a JSON object, or has no product menu nodes.
        """
        situations = self._json_object(response).get("body")
        menu = next(
            (
                self._as_object(situation)
                for situation in (situations if isinstance(situations, list) else [])
                if self._as_object(situation).get("situationCode") == "product"
            ),
            {},
        )
        nodes = menu.get("bindData")
        if not isinstance(nodes, list) or not nodes:
            self.logger.error("The %s menu %s has no product nodes (`bindData`).", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the product menu nodes (`bindData`) are missing")
        self.logger.debug("%d top nodes in the %s menu %s.", len(nodes), self.name, response.url)
        return sorted(nodes, key=lambda node: self._as_object(node).get("name") == self.CO_BRANDED_NODE)

    def _menu_metadata(self, nodes: List[JsonValue]) -> Iterator[Dict[str, JsonValue]]:
        """Walk the products (`bindMetadatas`) of every menu level, skipping the promotion nodes.

        Args:
            nodes (List[JsonValue]): The menu nodes.

        Yields:
            Dict[str, JsonValue]: Each product entry of the nodes and of their children, depth first.
        """
        for node in map(self._as_object, nodes):
            if node.get("type") == self.PROMO_NODE:
                self.logger.debug("Skipping the menu node %r, a promotion.", node.get("name"))
                continue
            metadata = node.get("bindMetadatas")
            yield from (self._as_object(entry) for entry in (metadata if isinstance(metadata, list) else []))
            children = node.get("children")
            yield from self._menu_metadata(children if isinstance(children, list) else [])

    def _description(self, metadata: Dict[str, JsonValue]) -> Optional[str]:
        """Read the description of a menu entry: its `sDesc`, else its `brief` when `sDesc` is a placeholder.

        Args:
            metadata (Dict[str, JsonValue]): The menu entry.

        Returns:
            Optional[str]: The description, `None` when the entry only holds placeholders.
        """
        for field in ("sDesc", "brief"):
            text = self._clean_text(self._as_text(metadata.get(field)))
            if text and not self.PLACEHOLDER.search(text):
                return text
        return None

    def _menu_entries(self, response: Response) -> List[MenuEntry]:
        """Read the products of the menu, once per identifier.

        Args:
            response (Response): The products menu.

        Returns:
            List[MenuEntry]: The products, the co-branded ones last.

        Raises:
            CatalogueFormatError: If the response is not a JSON object, or has no product menu nodes.
        """
        entries: List[MenuEntry] = []
        identifiers: Set[str] = set()
        for metadata in self._menu_metadata(self._menu_nodes(response)):
            name, identifier = self._as_text(metadata.get("name")), self._as_text(metadata.get("id"))
            slug = self._clean_text(self._as_text(metadata.get("type"))) or None
            link = self._clean_text(self._as_text(metadata.get("introduceUrl")))
            if identifier is not None and identifier in identifiers:
                self.logger.debug("Skipping the menu entry %r, already listed.", name)
                continue
            if not link and slug is None:
                self.logger.debug("Skipping the menu entry %r, without type nor link.", name)
                continue
            if identifier is not None:
                identifiers.add(identifier)
            url = urljoin(self.SITE_URL, link) if link else self.PRODUCT_URL.format(slug=slug)
            entries.append((name, self._description(metadata), url, slug))
        self.logger.debug("%d product entries in the %s menu %s.", len(entries), self.name, response.url)
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the described products of the menu.

        Args:
            response (Response): The products menu.

        Yields:
            Iterator[CloudProduct]: Each valid product with a description.

        Raises:
            CatalogueFormatError: If the response is not a JSON object, or has no product menu nodes.
        """
        for name, description, url, _ in self._menu_entries(response):
            if description is not None and (product := self._build_product(name, description, url)):
                yield product

    def _template_requests(self, response: Response) -> List[Request]:
        """Request the page templates of the menu products without description, not streamed yet.

        Args:
            response (Response): The products menu.

        Returns:
            List[Request]: The template requests.

        Raises:
            CatalogueFormatError: If the response is not a JSON object, or has no product menu nodes.
        """
        requests: List[Request] = []
        requested: Set[str] = set()
        for name, description, url, slug in self._menu_entries(response):
            if description is not None:
                continue
            if slug is None or not name or not self._clean_text(name):
                self.logger.debug("Skipping the menu entry %r, without description nor page template.", name)
                continue
            known = {*self.seen_urls, *requested}
            if self._url_key(url) in known or self._name_key(name) in self.seen_products:
                self.logger.debug("Not requesting the page template of %r, its product is already listed.", name)
                continue
            requested.add(self._url_key(url))
            meta: Dict[str, str] = {self.TEMPLATE_PRODUCT: url, self.PRODUCT_NAME: self._clean_text(name)}
            requests.append(Request(self.TEMPLATE_URL.format(slug=quote(slug)), meta=meta))
        self.logger.info("%d %s page templates to read for the products without description.", len(requests), self.name)
        return requests

    def _template_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a page template: the menu name and link, and the template SEO description.

        Args:
            response (Response): The page template, requested with the `TEMPLATE_PRODUCT` meta.

        Returns:
            Optional[CloudProduct]: The product, `None` for an unknown template (no `body`) or an invalid product.

        Raises:
            CatalogueFormatError: If the response is empty (dropped connection), not JSON or not a JSON object.
        """
        name, url = str(response.meta.get(self.PRODUCT_NAME, "")), str(response.meta[self.TEMPLATE_PRODUCT])
        template = self._json_object(response).get("body")
        if not isinstance(template, dict):
            self.logger.debug("Skipping the product %r, its page template %s is unknown.", name, response.url)
            return None
        return self._build_product(name, self._as_text(template.get("seoDescription")), url)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the described products of the products menu.

        Args:
            response (Response): The products menu.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu, duplicates included.

        Raises:
            CatalogueFormatError: If the response is not a JSON object, or has no product menu nodes.
        """
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, then request the page templates of the products without description.

        Args:
            response (Response): The products menu, or a page template (`TEMPLATE_PRODUCT` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the template requests.

        Raises:
            CatalogueFormatError: If a response is empty (dropped connection), not JSON or not a JSON object,
                or if the menu has no product nodes.
        """
        if self.TEMPLATE_PRODUCT in response.meta:
            product = self._template_product(response)
            if product is not None and (template_item := self._stream(product)) is not None:
                yield template_item
            return
        async for item in super().parse(response):
            yield item
        for request in self._template_requests(response):
            yield request
