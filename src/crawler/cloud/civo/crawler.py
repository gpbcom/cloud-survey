from __future__ import annotations

# Standard Library Imports.
import json
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from models.cloud.product import CloudProduct


class CivoCrawler(BaseCloudCrawler):
    """Civo catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the links being relative to it.
        PRIVATE_CLOUD_URL (ClassVar[str]): The Private Cloud hub page.
        AI_URL (ClassVar[str]): The Civo AI hub page, also listing the GPU models and read for its footer.
        PRICING_URL (ClassVar[str]): The pricing page, whose navigation lists the priced services.
        LD_JSON (ClassVar[str]): The CSS selector of the JSON-LD scripts.
        GPU_CARDS (ClassVar[str]): The CSS selector of the GPU model cards of the Civo AI hub.
        PRICING_NAV (ClassVar[str]): The CSS selector of the pricing navigation entries.
        FOOTER_COLUMNS (ClassVar[FrozenSet[str]]): The footer columns listing products.
        FOOTER_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The footer links which are not product pages.
        URL_ALIASES (ClassVar[Dict[str, str]]): The short paths redirecting to a product page, by redirected path.
        PRICING_PAGES (ClassVar[Dict[str, str]]): The pricing anchors covered by a product page, by anchor.
        PRICING_NOT_PRODUCT (ClassVar[FrozenSet[str]]): The pricing anchors which are not products.

    Notes:
        The main source is the JSON-LD service of the three hub pages (https://www.civo.com/public-cloud,
        `/private-cloud` and `/ai`): its offer catalogue (`hasOfferCatalog.itemListElement`) gives the name,
        description and URL of each product. The Civo AI hub also lists the GPU models as cards. The pricing
        navigation adds the priced services without a product page (Object Store), the other entries being
        covered by their product pages. Last, the footer columns "Public Cloud", "Private Cloud" and "Civo AI"
        link to the remaining product pages, read for their description and named after the footer label.
        The JSON-LD links are short paths redirecting to the product pages: they are replaced by the product page
        URLs, and compared with them, through `URL_ALIASES`.
    """

    SITE_URL: ClassVar[str] = "https://www.civo.com/"
    PRIVATE_CLOUD_URL: ClassVar[str] = "https://www.civo.com/private-cloud"
    AI_URL: ClassVar[str] = "https://www.civo.com/ai"
    PRICING_URL: ClassVar[str] = "https://www.civo.com/pricing"
    LD_JSON: ClassVar[str] = 'script[type="application/ld+json"]::text'
    GPU_CARDS: ClassVar[str] = "div[data-card] article a[href]"
    PRICING_NAV: ClassVar[str] = "aside.pricing-nav a.pricing-nav-item"
    FOOTER_COLUMNS: ClassVar[FrozenSet[str]] = frozenset({"Public Cloud", "Private Cloud", "Civo AI"})
    FOOTER_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"^/pricing\b")
    URL_ALIASES: ClassVar[Dict[str, str]] = {
        "/kubernetes": "/public-cloud/kubernetes",
        "/compute": "/public-cloud/compute",
        "/databases": "/public-cloud/databases",
        "/load-balancers": "/public-cloud/load-balancers",
        "/features/block-storage": "/public-cloud/block-storage",
        "/civostack-enterprise": "/private-cloud/civostack-enterprise",
        "/flexcore": "/private-cloud/flexcore",
        "/vmware-alternative": "/private-cloud/vmware-alternative",
        "/ai/kubernetes": "/ai/kubernetes-gpu",
        "/ai/compute": "/ai/gpu-compute",
    }
    PRICING_PAGES: ClassVar[Dict[str, str]] = {
        "#kubernetes": "/public-cloud/kubernetes",
        "#compute-instances": "/public-cloud/compute",
        "#databases": "/public-cloud/databases",
        "#load-balancers": "/public-cloud/load-balancers",
        "#volumes": "/public-cloud/block-storage",
        "#nvidia-gpus": "/ai/cloud-gpu",
    }
    PRICING_NOT_PRODUCT: ClassVar[FrozenSet[str]] = frozenset({"#data-transfer"})

    name = "civo"
    catalogue_url: ClassVar[str] = "https://www.civo.com/public-cloud"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRIVATE_CLOUD_URL, AI_URL, PRICING_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Civo ",)

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare the short paths with the product pages they redirect to, and the pricing anchors apart.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The URL key of the product page, e.g. `civo.com/public-cloud/databases` for `/databases`, with the
                anchor for the pricing page entries (`civo.com/pricing#object-store`).
        """
        link = urlparse(url.casefold())
        path = link.path.rstrip("/")
        path = self.URL_ALIASES.get(path, path)
        anchor = f"#{link.fragment}" if path == "/pricing" and link.fragment else ""
        return f"{link.netloc.removeprefix('www.')}{path}{anchor}"

    def _canonical_url(self, link: str) -> str:
        """Get the product page URL of a JSON-LD link, which may be a short path redirecting to it.

        Args:
            link (str): The absolute or relative link.

        Returns:
            str: The absolute product page URL, e.g. `https://www.civo.com/public-cloud/databases` for `/databases`.
        """
        url = urljoin(self.SITE_URL, link)
        path = urlparse(url).path.rstrip("/")
        return urljoin(self.SITE_URL, self.URL_ALIASES[path]) if path in self.URL_ALIASES else url

    def _offer_catalogues(self, response: Response) -> Iterator[List[JsonValue]]:
        """Find the offer catalogues of the JSON-LD scripts of a hub page.

        Args:
            response (Response): The hub page.

        Yields:
            List[JsonValue]: The `itemListElement` list of each offer catalogue.
        """
        for raw in response.css(self.LD_JSON).getall():
            try:
                data: JsonValue = json.loads(str(raw))
            except json.JSONDecodeError as e:
                self.logger.debug("Skipping a JSON-LD script of %s which is not JSON: %s", response.url, e)
                continue
            for node in self._walk_objects(data):
                items = self._as_object(node.get("hasOfferCatalog")).get("itemListElement")
                if isinstance(items, list):
                    self.logger.debug(
                        "Offer catalogue %r of %s: %d entries.", node.get("name"), response.url, len(items)
                    )
                    yield items

    def _offer_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the JSON-LD offer catalogues of a hub page.

        Args:
            response (Response): The hub page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the offer catalogues.
        """
        for items in self._offer_catalogues(response):
            for item in items:
                fields = self._as_object(item)
                name, description = self._as_text(fields.get("name")), self._as_text(fields.get("description"))
                url = self._as_text(fields.get("url"))
                if product := self._build_product(name, description, self._canonical_url(url) if url else None):
                    yield product

    def _gpu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the GPU models of the cards of a hub page (only the Civo AI hub has some).

        Args:
            response (Response): The hub page.

        Yields:
            Iterator[CloudProduct]: Each valid GPU model.
        """
        cards = response.css(self.GPU_CARDS)
        self.logger.debug("%d GPU cards in %s.", len(cards), response.url)
        for card in cards:
            name, description = card.css("h3").first, card.css("p").first
            if product := self._build_product(
                name.get_all_text(separator=" ", strip=True) if name is not None else None,
                description.get_all_text(separator=" ", strip=True) if description is not None else None,
                urljoin(self.SITE_URL, card.attrib.get("href", "")),
            ):
                yield product

    def _hub_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a hub page: its JSON-LD offer catalogue, then its GPU cards.

        Args:
            response (Response): The hub page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the page.
        """
        yield from self._offer_products(response)
        yield from self._gpu_products(response)

    def _pricing_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the priced services of the pricing navigation which have no product page.

        Args:
            response (Response): The pricing page.

        Yields:
            Iterator[CloudProduct]: Each valid priced service without product page, e.g. Object Store.
        """
        entries = response.css(self.PRICING_NAV)
        self.logger.debug("%d pricing navigation entries in %s.", len(entries), response.url)
        for entry in entries:
            anchor = entry.attrib.get("href", "")
            title, description = entry.css("h4").first, entry.css("p").first
            name = title.get_all_text(separator=" ", strip=True) if title is not None else None
            if anchor in self.PRICING_NOT_PRODUCT:
                self.logger.debug("Skipping the pricing entry %r, not a product.", name)
                continue
            if anchor in self.PRICING_PAGES:
                self.logger.debug("Skipping the pricing entry %r, covered by %s.", name, self.PRICING_PAGES[anchor])
                continue
            text = description.get_all_text(separator=" ", strip=True) if description is not None else None
            if product := self._build_product(name, text, urljoin(self.PRICING_URL, anchor)):
                yield product

    def _footer_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the footer product columns which were not streamed yet.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Request]: The product page requests, named after the footer labels.
        """
        requests: List[Request] = []
        for heading in response.css("footer h3.footer-heading"):
            column = self._clean_text(heading.get_all_text(separator=" ", strip=True))
            if column not in self.FOOTER_COLUMNS or heading.parent is None:
                continue
            for link in heading.parent.css("a.footer-link"):
                label = self._clean_text(link.get_all_text(separator=" ", strip=True))
                url = urljoin(self.SITE_URL, link.attrib.get("href", ""))
                if self.FOOTER_NOT_PRODUCT.search(urlparse(url).path):
                    self.logger.debug("Skipping the footer link %r (%s), not a product page.", label, url)
                    continue
                if (request := self._product_page_request(url, label)) is not None:
                    requests.append(request)
        self.logger.info("%d %s product pages to read from the footer of %s.", len(requests), self.name, response.url)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a hub page or of the pricing page.

        Args:
            response (Response): The hub page or the pricing page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        if self._url_key(response.url) == self._url_key(self.PRICING_URL):
            return self._pricing_products(response)
        return self._hub_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a page, then request the footer product pages from the Civo AI hub.

        Args:
            response (Response): A hub page, the pricing page or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the product page requests.

        Raises:
            EmptyCatalogueError: If a hub page or the pricing page holds no valid product.
        """
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and self._url_key(response.url) == self._url_key(self.AI_URL):
            for request in self._footer_requests(response):
                yield request
