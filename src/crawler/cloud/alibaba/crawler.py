from __future__ import annotations

# Standard Library Imports.
import json
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class AlibabaCloudCrawler(BaseCloudCrawler):
    """Alibaba Cloud (international website) catalogue crawler.

    Attributes:
        NAV_URL (ClassVar[str]): The product tree of the website navigation menu (JSON), the main source.
        PRODUCTS_URL (ClassVar[str]): The "All products" page, whose product cards are embedded as JSON.
        HELP_URL (ClassVar[str]): The documentation home page, listing every product documentation.
        SITEMAP_URL (ClassVar[str]): The sitemap of the product pages.
        SITE_URL (ClassVar[str]): The English website root, which the relative card links are relative to.
        HELP_WAIT_SELECTOR (ClassVar[str]): The documentation entries, rendered by a script, which are waited for.
        HELP_PRIORITY (ClassVar[int]): The priority of the documentation home page, read before the "All products"
            cards so that its deprecated products are known first.
        CARDS_EXCLUDED_SECTIONS (ClassVar[FrozenSet[str]]): The "All products" sections which are not products.
        HELP_EXCLUDED_BLOCKS (ClassVar[FrozenSet[str]]): The documentation blocks which are not products.
        HELP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The documentation entries which are tools, consoles or guides.
        DEPRECATED (ClassVar[re.Pattern[str]]): The deprecation mark of the documentation entries.
        PRODUCT_PAGE_URL (ClassVar[re.Pattern[str]]): A one-segment product page of the sitemap, capturing its slug.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The sitemap product slugs which are forms, tests,
            categories, instance families or offers.
        LOCALE (ClassVar[re.Pattern[str]]): The locale segment of the website paths, e.g. `/en/`.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the product page titles.
        TITLE_TAGLINE (ClassVar[re.Pattern[str]]): The separators of the SEO taglines of the product page titles.
        NOT_FOR_SALE (ClassVar[str]): The notice of the retired product pages.
        URL_ALIASES (ClassVar[Dict[str, str]]): The URL keys of the product pages which are aliases of another one.
        NAME_ALIASES (ClassVar[Dict[str, Tuple[str, ...]]]): The documentation names of products listed under
            another name, by listed name.
        ABBREVIATION (ClassVar[re.Pattern[str]]): The abbreviation of a product name, e.g. `(ENS)`, also a name.
        HELP_LANDING_URL (ClassVar[str]): The documentation landing page of a product, by slug.
        HELP_GUESS_URL (ClassVar[str]): The usual "What is" article of a product, by slug, which the website resolves.
        HELP_ARTICLE_LINK (ClassVar[re.Pattern[str]]): The last path segment of an overview article link.
        HELP_BOILERPLATE (ClassVar[re.Pattern[str]]): The generic description of the documentation pages.
        HELP_SLUG (ClassVar[str]): The meta key holding the documentation slug of a product page request.
        HELP_LANDING (ClassVar[str]): The meta key marking a documentation landing page request, holding its slug.
        HELP_ARTICLE (ClassVar[str]): The meta key marking an overview article request, holding the product URL.
        help_names (Dict[str, Tuple[str, str]]): The names and slugs of the documentation entries not streamed yet,
            by normalized slug.
        deprecated_names (Set[str]): The normalized names of the products marked as deprecated by the documentation.
        category_urls (Set[str]): The URL keys of the navigation categories, whose pages are not product pages.

    Notes:
        The main source is the product tree of the navigation menu (`detailedCategories`, walked through the
        `subCategories`), whose ad groups and featured category are left out. The cards embedded in the
        "All products" page (`div.render-container-data[data-data]`) complete it, without the Academy section
        (certifications), the solutions and the products the documentation marks as deprecated.
        The documentation home page (rendered by a script) lists more products, without description: once read,
        the product pages of the sitemap not streamed yet (categories excluded) are requested, named after their
        documentation entry when the slugs match, else after their title. A documentation entry without product
        page, or whose product page has no description, is described by its documentation landing page, whose
        URL is then the product URL. When the landing page description is generic ("Learn from Alibaba Cloud
        experts..."), its overview article is read instead: the "What is" (or product introduction) article
        linked from the landing page, else the usual "What is" article URL, which the website resolves. The meta
        description (without its keywords prefix) is used, else the first paragraph of the article, and the
        products without a genuine description are skipped.
        The retired product pages ("no longer available for sale", or deprecated in the documentation) are
        skipped, as the unknown product pages which redirect to a "not found" page.
    """

    NAV_URL: ClassVar[str] = (
        "https://file-intl.alicdn.com/stmt/2/alibabacloud/product/navigation_product_tree/aggregation-product/1.0/en.json"
    )
    PRODUCTS_URL: ClassVar[str] = "https://www.alibabacloud.com/en/product"
    HELP_URL: ClassVar[str] = "https://www.alibabacloud.com/help/en/"
    SITEMAP_URL: ClassVar[str] = "https://www.alibabacloud.com/sitemaps/en/product/sitemap.xml"
    SITE_URL: ClassVar[str] = "https://www.alibabacloud.com/en/"
    HELP_WAIT_SELECTOR: ClassVar[str] = '[class*="ProductList--subNodeContent"] a'
    HELP_PRIORITY: ClassVar[int] = 1
    CARDS_EXCLUDED_SECTIONS: ClassVar[FrozenSet[str]] = frozenset({"alibaba cloud academy"})
    HELP_EXCLUDED_BLOCKS: ClassVar[FrozenSet[str]] = frozenset(
        {"getting started", "solutions", "membership service", "more"}
    )
    HELP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"\bSDK\b|\bCLI\b|BSS OpenAPI|Ticket System API|\bConsole\b|Overview|^Marketplace$|^Pulumi$|^Terraform$|"
        r"Well-architected|Guidelines",
        re.IGNORECASE,
    )
    DEPRECATED: ClassVar[re.Pattern[str]] = re.compile(r"\(Deprecated\)|\s-\sDeprecated$", re.IGNORECASE)
    PRODUCT_PAGE_URL: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.alibabacloud\.com/en/product/([^/?#]+)/?(?:[?#].*)?$"
    )
    SITEMAP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"contact|form|test|savings-plan|^ecs-[a-z]+\d+$|"
        r"^(index|computing|databases|networking|security|storage|cloud-native|product-mapping)$",
        re.IGNORECASE,
    )
    LOCALE: ClassVar[re.Pattern[str]] = re.compile(r"^/[a-z]{2}(-[a-z]{2})?(?=/)")
    TITLE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"(\s*-\s*Alibaba Cloud)+$", re.IGNORECASE)
    TITLE_TAGLINE: ClassVar[re.Pattern[str]] = re.compile(r":|_|\s\|\s|\s-\s")
    NOT_FOR_SALE: ClassVar[str] = "no longer available for sale"
    URL_ALIASES: ClassVar[Dict[str, str]] = {
        "alibabacloud.com/product/polardb-for-xscale": "alibabacloud.com/product/polardb-x"
    }
    NAME_ALIASES: ClassVar[Dict[str, Tuple[str, ...]]] = {
        "mPaaS": ("Mobile Platform as a Service",),
        "Cloud Migration Hub (CMH)": ("Migration Hub",),
        "Intelligent Computing Service PAI-Lingjun": ("Intelligent Computing LINGJUN",),
        "Domain Names and Website": ("Domain Names",),
    }
    ABBREVIATION: ClassVar[re.Pattern[str]] = re.compile(r"\(([A-Za-z][A-Za-z0-9-]{1,9})\)$")
    HELP_LANDING_URL: ClassVar[str] = "https://www.alibabacloud.com/help/en/{slug}/"
    HELP_GUESS_URL: ClassVar[str] = "https://www.alibabacloud.com/help/en/{slug}/product-overview/what-is-{slug}"
    HELP_ARTICLE_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"^what-is|product-introduction$|^(?P<overview>.+)-overview$"
    )
    HELP_BOILERPLATE: ClassVar[re.Pattern[str]] = re.compile(r"^Learn from Alibaba Cloud experts", re.IGNORECASE)
    HELP_SLUG: ClassVar[str] = "help_slug"
    HELP_LANDING: ClassVar[str] = "help_landing"
    HELP_ARTICLE: ClassVar[str] = "help_article"

    name = "alibaba"
    catalogue_url: ClassVar[str] = NAV_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (PRODUCTS_URL, HELP_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Alibaba Cloud ", "Alibaba ", "ApsaraDB for ", "ApsaraDB ", "Apsara ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.help_names: Dict[str, Tuple[str, str]] = {}
        self.deprecated_names: Set[str] = set()
        self.category_urls: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare the website pages whatever their locale (`/en/product/ecs` and `/product/ecs` are the same).

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, without the locale segment, the key of the main page for an alias.
        """
        link = urlparse(url.casefold())
        key = f"{link.netloc.removeprefix('www.')}{self.LOCALE.sub('', link.path).rstrip('/')}"
        return self.URL_ALIASES.get(key, key)

    def _stream(self, product: CloudProduct) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a product not streamed yet, remembering its abbreviation and documentation names.

        Args:
            product (CloudProduct): The extracted product.

        Returns:
            Optional[Dict[str, JsonValue]]: The product as a dictionary, `None` when it was already streamed.
        """
        item = super()._stream(product)
        if item is not None:
            abbreviation = self.ABBREVIATION.search(product.name)
            self._remember((*self.NAME_ALIASES.get(product.name, ()), *(abbreviation.groups() if abbreviation else ())))
        return item

    def _complement_request(self, url: str) -> Request:
        """Build the request of a complementary page, waiting for the documentation entries to be rendered.

        Args:
            url (str): The complementary catalogue page.

        Returns:
            Request: The request, waiting for the documentation entries on the documentation home page, which is
                read before the "All products" cards.
        """
        if url == self.HELP_URL:
            return Request(url, priority=self.HELP_PRIORITY, wait_selector=self.HELP_WAIT_SELECTOR)
        return Request(url)

    def _source(self, url: str) -> str:
        """Tell which source a page is.

        Args:
            url (str): The page URL.

        Returns:
            str: `nav`, `help`, `sitemap` or `cards`.
        """
        link = urlparse(url)
        if link.netloc != urlparse(self.SITE_URL).netloc:
            return "nav"
        if link.path.startswith("/help/"):
            return "help"
        if link.path.startswith("/sitemaps/"):
            return "sitemap"
        return "cards"

    def _slug_key(self, slug: str) -> str:
        """Normalize a page slug to compare the documentation slugs with the product page ones.

        Args:
            slug (str): The slug, e.g. `optimization-solver` or `optimization_solver`.

        Returns:
            str: The comparison key, e.g. `optimizationsolver`.
        """
        return re.sub(r"[\W_]+", "", slug.casefold())

    def _nav_category_products(self, category: Dict[str, JsonValue]) -> Iterator[CloudProduct]:
        """Extract the products of a navigation category and of its subcategories, depth first.

        The category page, if any, is remembered as a category page.

        Args:
            category (Dict[str, JsonValue]): The navigation category.

        Yields:
            Iterator[CloudProduct]: Each valid product of the category.
        """
        if link := self._as_text(category.get("url")):
            self.category_urls.add(self._url_key(link))
        products = category.get("products")
        for entry in products if isinstance(products, list) else []:
            fields = self._as_object(entry)
            name, url = self._as_text(fields.get("name")), self._as_text(fields.get("url"))
            if product := self._build_product(name, self._as_text(fields.get("shortDesc")), url):
                yield product
        subcategories = category.get("subCategories")
        for subcategory in subcategories if isinstance(subcategories, list) else []:
            yield from self._nav_category_products(self._as_object(subcategory))

    def _nav_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the navigation product tree, without its ad groups and featured category.

        Args:
            response (Response): The navigation product tree (JSON).

        Yields:
            Iterator[CloudProduct]: Each valid product of the tree.

        Raises:
            CatalogueFormatError: If the document is not JSON or has no `detailedCategories` list.
        """
        categories = self._as_object(self._json_body(response)).get("detailedCategories")
        if not isinstance(categories, list):
            self.logger.error("The %s product tree %s has no `detailedCategories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`detailedCategories` is not a list")
        self.logger.debug("%d navigation categories in %s.", len(categories), response.url)
        for category in categories:
            yield from self._nav_category_products(self._as_object(category))

    def _cards_data(self, response: Response) -> List[JsonValue]:
        """Read the sections of the product cards embedded in the "All products" page.

        Args:
            response (Response): The "All products" page.

        Returns:
            List[JsonValue]: The sections (`content` list).

        Raises:
            CatalogueFormatError: If the page embeds no product cards.
        """
        for raw in response.css("div.render-container-data::attr(data-data)").getall():
            try:
                data: JsonValue = json.loads(str(raw))
            except json.JSONDecodeError:
                self.logger.debug("Skipping a render data block of %s, not JSON.", response.url)
                continue
            sections = self._as_object(data).get("content")
            if isinstance(sections, list):
                return sections
        self.logger.error("The %s page %s embeds no product cards.", self.name, response.url)
        raise CatalogueFormatError(self.name, response.url, "the product cards (`render-container-data`) are missing")

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the "All products" cards, without the Academy section and the solutions.

        Args:
            response (Response): The "All products" page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the cards.

        Raises:
            CatalogueFormatError: If the page embeds no product cards.
        """
        for section in map(self._as_object, self._cards_data(response)):
            title = self._clean_text(self._as_text(section.get("FirstLevelHead")))
            if title.casefold() in self.CARDS_EXCLUDED_SECTIONS:
                self.logger.debug("Skipping the %r section of %s, not products.", title, response.url)
                continue
            groups = section.get("productCard")
            for group in groups if isinstance(groups, list) else []:
                cards = self._as_object(group).get("cardList")
                for card in map(self._as_object, cards if isinstance(cards, list) else []):
                    name, link = self._as_text(card.get("title")), self._as_text(card.get("url")) or ""
                    if "solutions/" in link or self._name_key(name or "") in self.deprecated_names:
                        self.logger.debug("Skipping the card %r (%s), a solution or a deprecated product.", name, link)
                        continue
                    url = urljoin(self.SITE_URL, link) if link else None
                    if product := self._build_product(name, self._as_text(card.get("desc")), url):
                        yield product

    def _help_entries(self, response: Response) -> List[Tuple[str, str]]:
        """Read the product entries of the documentation home page, without the guides, tools and deprecated ones.

        Args:
            response (Response): The documentation home page.

        Returns:
            List[Tuple[str, str]]: The product names and documentation slugs.

        Raises:
            CatalogueFormatError: If the page lists no documentation entry.
        """
        blocks = response.css('[class*="ProductList--allProductsBodyBlock"]')
        entries: List[Tuple[str, str]] = []
        total = 0
        for block in blocks:
            heading = block.css("span").first
            title = self._clean_text(heading.get_all_text(strip=True) if heading is not None else "")
            links = block.css('[class*="ProductList--subNodeContent"] a')
            total += len(links)
            if title.casefold() in self.HELP_EXCLUDED_BLOCKS:
                self.logger.debug("Skipping the documentation block %r (%d entries), not products.", title, len(links))
                continue
            for link in links:
                name = self._clean_text(link.get_all_text(separator=" ", strip=True))
                slug = urlparse(link.attrib.get("href", "")).path.strip("/").split("/")[-1]
                if self.DEPRECATED.search(name):
                    self.logger.debug("Skipping the documentation entry %r, deprecated.", name)
                    self.deprecated_names.add(self._name_key(self.DEPRECATED.sub("", name)))
                    continue
                if self.HELP_NOT_PRODUCT.search(name):
                    self.logger.debug("Skipping the documentation entry %r, not a product.", name)
                    continue
                entries.append((name, slug))
        if not total:
            self.logger.error("The %s documentation page %s lists no product.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the documentation lists no product")
        self.logger.debug("%d documentation entries in %s (%d product entries).", total, response.url, len(entries))
        return entries

    def _help_request(self, response: Response) -> Request:
        """Remember the documentation entries not streamed yet, then request the sitemap of the product pages.

        Args:
            response (Response): The documentation home page.

        Returns:
            Request: The sitemap request.

        Raises:
            CatalogueFormatError: If the page lists no documentation entry.
        """
        for name, slug in self._help_entries(response):
            if self._name_key(name) in self.seen_products:
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
                continue
            self.help_names.setdefault(self._slug_key(slug), (name, slug))
        self.logger.info(
            "%d %s documentation entries not streamed yet, requesting the sitemap %s.",
            len(self.help_names),
            self.name,
            self.SITEMAP_URL,
        )
        return Request(self.SITEMAP_URL)

    def _help_landing_request(self, name: str, slug: str) -> Request:
        """Build the request of the documentation landing page of a product, to find its overview article.

        Args:
            name (str): The product name given by the documentation.
            slug (str): The documentation slug, e.g. `epg`.

        Returns:
            Request: The landing page request.
        """
        meta: Dict[str, str] = {self.HELP_LANDING: slug, self.PRODUCT_NAME: name}
        return Request(self.HELP_LANDING_URL.format(slug=slug), meta=meta)

    def _help_article_request(self, response: Response) -> Request:
        """Request the overview article of a product, found on its documentation landing page.

        Args:
            response (Response): The documentation landing page, requested with the `HELP_LANDING` meta.

        Returns:
            Request: The overview article request (`HELP_ARTICLE` meta), named after the documentation entry: the
                "What is" article, else a product introduction or overview article, else the product introduction
                section (which opens its first article), else the usual "What is" article URL.
        """
        slug = str(response.meta[self.HELP_LANDING])
        prefix = f"/help/en/{slug}/"
        candidates: List[Tuple[int, str]] = []
        for href in response.css("a::attr(href)").getall():
            path = urlparse(str(href)).path
            segment = path.rstrip("/").rsplit("/", 1)[-1]
            match = self.HELP_ARTICLE_LINK.search(segment)
            if not path.startswith(prefix) or match is None:
                continue
            if path.endswith("/"):
                if segment == "product-introduction":
                    candidates.append((2, urljoin(self.SITE_URL, path)))
            elif match.group("overview") is None or match.group("overview") == slug:
                rank = 0 if match.group(0).startswith("what-is") else 1
                candidates.append((rank, urljoin(self.SITE_URL, path)))
        url = min(candidates)[1] if candidates else self.HELP_GUESS_URL.format(slug=slug)
        self.logger.debug("Requesting the overview article %s of %r.", url, response.meta[self.PRODUCT_NAME])
        meta: Dict[str, JsonValue] = {
            self.HELP_ARTICLE: self.HELP_LANDING_URL.format(slug=slug),
            self.PRODUCT_NAME: response.meta[self.PRODUCT_NAME],
        }
        return Request(url, meta=meta)

    def _help_description(self, response: Response, name: str) -> Optional[str]:
        """Read the genuine description of a product from its overview article.

        Args:
            response (Response): The overview article.
            name (str): The product name, which prefixes the meta description after its keywords.

        Returns:
            Optional[str]: The meta description without its keywords prefix (e.g. `What is CloudSSO,CloudSSO:`),
                else the first paragraph of the article, `None` when missing or generic.
        """
        description = self._meta_content(response, "description") or ""
        marker = f",{name}:".casefold()
        if (index := description.casefold().find(marker)) >= 0:
            description = self._clean_text(description[index + len(marker) :])
        if not description:
            paragraphs = (
                paragraph.get_all_text(separator=" ", strip=True) for paragraph in response.css(".markdown-body p")
            )
            description = next((self._clean_text(text) for text in paragraphs if self._clean_text(text)), "")
        if not description or self.HELP_BOILERPLATE.search(description):
            return None
        return description

    def _help_landing_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product described by its documentation landing page, when its description is genuine.

        Args:
            response (Response): The documentation landing page, requested with the `HELP_LANDING` meta.

        Returns:
            Optional[CloudProduct]: The product, with the landing page as URL, `None` without a genuine description.
        """
        name = str(response.meta[self.PRODUCT_NAME])
        description = self._help_description(response, name)
        if description is None:
            return None
        slug = str(response.meta[self.HELP_LANDING])
        return self._build_product(name, description, self.HELP_LANDING_URL.format(slug=slug))

    def _help_article_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product described by its overview article.

        Args:
            response (Response): The overview article, requested with the `HELP_ARTICLE` meta.

        Returns:
            Optional[CloudProduct]: The product, with its documentation landing page as URL, `None` without a
                genuine description.
        """
        name = str(response.meta[self.PRODUCT_NAME])
        description = self._help_description(response, name)
        if description is None:
            self.logger.debug("Skipping %r, its overview article %s has no genuine description.", name, response.url)
            return None
        return self._build_product(name, description, str(response.meta[self.HELP_ARTICLE]))

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the one-segment product pages of the sitemap not streamed yet, named after the documentation.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page and documentation landing page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        urls = self._sitemap_urls(response)
        requests: List[Request] = []
        for page in urls:
            match = self.PRODUCT_PAGE_URL.match(page)
            if match is None or self.SITEMAP_NOT_PRODUCT.search(match.group(1)):
                continue
            if self._url_key(page) in self.category_urls:
                self.logger.debug("Skipping the sitemap page %s, a navigation category.", page)
                continue
            slug = match.group(1)
            name, help_slug = self.help_names.pop(self._slug_key(slug), (None, None))
            if name is not None and self._name_key(name) in self.seen_products:
                self.logger.debug("Not requesting the product page of %r, already streamed.", name)
                continue
            if request := self._product_page_request(f"{self.SITE_URL}product/{slug}", name):
                if help_slug is not None:
                    request.meta[self.HELP_SLUG] = help_slug
                requests.append(request)
        pages = len(requests)
        for name, help_slug in self.help_names.values():
            if self._name_key(name) in self.seen_products:
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
                continue
            requests.append(self._help_landing_request(name, help_slug))
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d pages), %d documentation entries without product page.",
            pages,
            self.name,
            len(urls),
            len(requests) - pages,
        )
        return requests

    def _page_title(self, title: str) -> str:
        """Clean a product page title: without the brand suffix and the SEO tagline.

        Args:
            title (str): The page title, e.g. `ApsaraDB for Cassandra: Managed Database Engine - Alibaba Cloud`.

        Returns:
            str: The product name, e.g. `ApsaraDB for Cassandra`.
        """
        name = self.TITLE_SUFFIX.sub("", self._clean_text(title))
        return self._clean_text(self.TITLE_TAGLINE.split(name, maxsplit=1)[0])

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its title, else its Open Graph title.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        title = self._clean_text(response.css("head > title::text").get())
        title = title or self._meta_content(response, "og:title") or ""
        return self._page_title(title) or None

    def _page_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a product page, skipping the retired products.

        Args:
            response (Response): The product page, requested with the `PRODUCT_PAGE` meta.

        Returns:
            Optional[CloudProduct]: The product with the requested URL (without the tracking query), `None` for a
                retired, deprecated, unknown (redirected) or invalid product page.
        """
        if self.NOT_FOR_SALE in response.body.decode("utf-8", errors="replace").casefold():
            self.logger.debug("Skipping %s, the product is no longer available for sale.", response.url)
            return None
        product = super()._page_product(response)
        if product is None:
            return None
        if self._name_key(product.name) in self.deprecated_names:
            self.logger.debug("Skipping %s, %r is deprecated.", response.url, product.name)
            return None
        return self._build_product(product.name, product.description, str(response.meta[self.PRODUCT_PAGE]))

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the navigation product tree or of the "All products" cards.

        Args:
            response (Response): The navigation product tree or the "All products" page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If the product tree or the product cards are missing.
        """
        if self._source(response.url) == "nav":
            return self._nav_products(response)
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the listed products, or request the sitemap or the product pages, or stream a product page.

        Args:
            response (Response): The product tree, the "All products" page, the documentation home page, the
                sitemap, a product page, a documentation landing page or an overview article.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the follow-up requests.

        Raises:
            CatalogueFormatError: If a listing is missing, or if the documentation or the sitemap lists nothing.
        """
        if self.HELP_LANDING in response.meta or self.HELP_ARTICLE in response.meta:
            landing = self.HELP_LANDING in response.meta
            product = self._help_landing_product(response) if landing else self._help_article_product(response)
            if product is not None and (streamed := self._stream(product)) is not None:
                yield streamed
            elif product is None and landing:
                yield self._help_article_request(response)
            return
        if self.HELP_SLUG in response.meta and self._page_description(response) is None:
            self.logger.debug("The product page %s has no description, reading its documentation.", response.url)
            yield self._help_landing_request(str(response.meta[self.PRODUCT_NAME]), str(response.meta[self.HELP_SLUG]))
            return
        source = self._source(response.url)
        if self.PRODUCT_PAGE not in response.meta and source == "help":
            yield self._help_request(response)
            return
        if self.PRODUCT_PAGE not in response.meta and source == "sitemap":
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
