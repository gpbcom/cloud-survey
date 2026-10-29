from __future__ import annotations

# Standard Library Imports.
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.alibaba.enums import (
    AlibabaBandwidthUnit,
    AlibabaCardField,
    AlibabaCardsDataField,
    AlibabaCardsGroupField,
    AlibabaCardsSection,
    AlibabaCardsSectionField,
    AlibabaCrawlerMeta,
    AlibabaHelpArticleSlug,
    AlibabaHelpBlock,
    AlibabaNavCategoryField,
    AlibabaNavProductField,
    AlibabaNavTreeField,
    AlibabaPageNotice,
    AlibabaPageSource,
    AlibabaPriceFile,
)
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.enums import HtmlAttribute, PageMetaName, TextEncoding
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.products.product import CloudProduct


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
        CARDS_EXCLUDED_SECTIONS (ClassVar[FrozenSet[AlibabaCardsSection]]): The "All products" sections which are
            not products.
        HELP_EXCLUDED_BLOCKS (ClassVar[FrozenSet[AlibabaHelpBlock]]): The documentation blocks which are not products.
        HELP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The documentation entries which are tools, consoles or guides.
        DEPRECATED (ClassVar[re.Pattern[str]]): The deprecation mark of the documentation entries.
        PRODUCT_PAGE_URL (ClassVar[re.Pattern[str]]): A one-segment product page of the sitemap, capturing its slug.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The sitemap product slugs which are forms, tests,
            categories, instance families or offers.
        LOCALE (ClassVar[re.Pattern[str]]): The locale segment of the website paths, e.g. `/en/`.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the product page titles.
        TITLE_TAGLINE (ClassVar[re.Pattern[str]]): The separators of the SEO taglines of the product page titles.
        NOT_FOR_SALE (ClassVar[AlibabaPageNotice]): The notice of the retired product pages.
        URL_ALIASES (ClassVar[Dict[str, str]]): The URL keys of the product pages which are aliases of another one.
        NAME_ALIASES (ClassVar[Dict[str, Tuple[str, ...]]]): The documentation names of products listed under
            another name, by listed name.
        ABBREVIATION (ClassVar[re.Pattern[str]]): The abbreviation of a product name, e.g. `(ENS)`, also a name.
        HELP_LANDING_URL (ClassVar[str]): The documentation landing page of a product, by slug.
        HELP_GUESS_URL (ClassVar[str]): The usual "What is" article of a product, by slug, which the website resolves.
        HELP_ARTICLE_LINK (ClassVar[re.Pattern[str]]): The last path segment of an overview article link.
        HELP_BOILERPLATE (ClassVar[re.Pattern[str]]): The generic description of the documentation pages.
        HELP_SLUG (ClassVar[AlibabaCrawlerMeta]): The meta key holding the documentation slug of a product page
            request.
        HELP_LANDING (ClassVar[AlibabaCrawlerMeta]): The meta key marking a documentation landing page request,
            holding its slug.
        HELP_ARTICLE (ClassVar[AlibabaCrawlerMeta]): The meta key marking an overview article request, holding the
            product URL.
        help_names (Dict[str, Tuple[str, str]]): The names and slugs of the documentation entries not streamed yet,
            by normalized slug.
        help_categories (Dict[str, List[str]]): The documentation blocks listing each documentation entry not
            streamed yet, by normalized name.
        deprecated_names (Set[str]): The normalized names of the products marked as deprecated by the documentation.
        category_urls (Set[str]): The URL keys of the navigation categories, whose pages are not product pages.
        PRICING_DIRECTORY_URL (ClassVar[str]): The pricing directory, listing the pricing page (or billing help
            page) of every product.
        DIRECTORY_DATA (ClassVar[str]): The CSS selector of the element holding its entries (JSON in `data-data`).
        MODEL_PRICES_URL (ClassVar[str]): The Model Studio pricing page (the token prices of every model, by region).
        MODEL_SERVICE (ClassVar[str]): The service of those prices.
        DIRECTORY_META (ClassVar[str]): The request meta marking the pricing directory request.
        PRICE_LOADER_URL (ClassVar[str]): The loader of the international ECS price list, naming its versioned
            price files.
        PRICE_FILE_URL (ClassVar[re.Pattern[str]]): A price file named by the loader.
        FILE_VERSION (ClassVar[re.Pattern[str]]): The version segment of a price file URL, e.g. `/2.0.421/`.
        PRICE_FILE (ClassVar[str]): The request meta holding the name of a price file.
        PRICE_VERSION (ClassVar[str]): The request meta holding its version.
        PRICE_CURRENCY (ClassVar[str]): The currency of the international price list.
        PERIODS (ClassVar[Tuple[Tuple[PriceUnit, int, PriceTerm], ...]]): The periods of the seven prices of an
            instance row: hourly, monthly, then 1 to 5 years paid at once (their months and term).
        ROW_LENGTH (ClassVar[int]): The least length of an instance row.
        DISK_UNITS (ClassVar[Tuple[Tuple[PriceUnit, str], ...]]): The units of the two prices of a disk row (per
            its size: monthly, hourly).
        BANDWIDTH_UNITS (ClassVar[Dict[AlibabaBandwidthUnit, PriceUnit]]): The unit of a bandwidth price.
        ECS_SERVICE (ClassVar[str]): The service of the ECS prices.
        INSTANCES_KEY (ClassVar[str]): The key part of an instance price.
        DISKS_KEY (ClassVar[str]): The key part of a disk price.
        BANDWIDTH_KEY (ClassVar[str]): The key part of a bandwidth price.
        GROUP_ATTRIBUTE (ClassVar[str]): The attribute naming the generation and network of an instance price.
        CATEGORY_ATTRIBUTE (ClassVar[str]): The attribute naming the category of a disk.
        USE_ATTRIBUTE (ClassVar[str]): The attribute naming the use of a disk (system or data).
        MBPS_ATTRIBUTE (ClassVar[str]): The attribute naming the bandwidth of a bandwidth price.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their prices.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

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
        The categories of a product are the navigation category and subcategory names above it, the "All products"
        section and group titles, or the documentation block titles (for the product pages and documentation
        pages of the documentation entries), each occurrence counted: they are gathered over the whole listing
        before the product is streamed.
        In price mode it reads the international ECS price list: its loader names the versioned price files of
        the instance types (hourly, monthly and 1 to 5 years paid at once, discounted), the disks (per 100 GB,
        monthly and hourly) and the bandwidth (per Mbps value, or per GB of traffic), in dollars. Each file is a
        source versioned by its path: an unchanged one is not downloaded again.
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
    CARDS_EXCLUDED_SECTIONS: ClassVar[FrozenSet[AlibabaCardsSection]] = frozenset(AlibabaCardsSection)
    HELP_EXCLUDED_BLOCKS: ClassVar[FrozenSet[AlibabaHelpBlock]] = frozenset(AlibabaHelpBlock)
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
    NOT_FOR_SALE: ClassVar[AlibabaPageNotice] = AlibabaPageNotice.NOT_FOR_SALE
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
    HELP_SLUG: ClassVar[AlibabaCrawlerMeta] = AlibabaCrawlerMeta.HELP_SLUG
    HELP_LANDING: ClassVar[AlibabaCrawlerMeta] = AlibabaCrawlerMeta.HELP_LANDING
    HELP_ARTICLE: ClassVar[AlibabaCrawlerMeta] = AlibabaCrawlerMeta.HELP_ARTICLE
    PRICE_LOADER_URL: ClassVar[str] = "https://ecs.console.alibabacloud.com/tools/price.do?channel=intl"
    PRICING_DIRECTORY_URL: ClassVar[str] = "https://www.alibabacloud.com/en/pricing"
    DIRECTORY_DATA: ClassVar[str] = "div.render-container-data[data-data]"
    MODEL_PRICES_URL: ClassVar[str] = "https://www.alibabacloud.com/help/en/model-studio/model-pricing"
    MODEL_SERVICE: ClassVar[str] = "Model Studio"
    DIRECTORY_META: ClassVar[str] = "price_directory"
    PRICE_FILE_URL: ClassVar[re.Pattern[str]] = re.compile(r"'(https://g\.alicdn\.com/[^']+\.js)'")
    FILE_VERSION: ClassVar[re.Pattern[str]] = re.compile(r"/(\d+\.\d+\.\d+)/")
    PRICE_FILE: ClassVar[str] = "price_file"
    PRICE_VERSION: ClassVar[str] = "price_version"
    PRICE_CURRENCY: ClassVar[str] = "USD"
    PERIODS: ClassVar[Tuple[Tuple[PriceUnit, int, PriceTerm], ...]] = (
        (PriceUnit.HOUR, 1, PriceTerm.NONE),
        (PriceUnit.MONTH, 1, PriceTerm.NONE),
        (PriceUnit.MONTH, 12, PriceTerm.ONE_YEAR),
        (PriceUnit.MONTH, 24, PriceTerm.TWO_YEARS),
        (PriceUnit.MONTH, 36, PriceTerm.THREE_YEARS),
        (PriceUnit.MONTH, 48, PriceTerm.FOUR_YEARS),
        (PriceUnit.MONTH, 60, PriceTerm.FIVE_YEARS),
    )
    ROW_LENGTH: ClassVar[int] = 7
    DISK_UNITS: ClassVar[Tuple[Tuple[PriceUnit, str], ...]] = (
        (PriceUnit.GIB_MONTH, "month"),
        (PriceUnit.GIB_HOUR, "hour"),
    )
    BANDWIDTH_UNITS: ClassVar[Dict[AlibabaBandwidthUnit, PriceUnit]] = {
        AlibabaBandwidthUnit.MONTH: PriceUnit.UNIT_MONTH,
        AlibabaBandwidthUnit.HOUR: PriceUnit.UNIT_HOUR,
        AlibabaBandwidthUnit.GB: PriceUnit.GIB,
    }
    ECS_SERVICE: ClassVar[str] = "Elastic Compute Service"
    INSTANCES_KEY: ClassVar[str] = "instances"
    DISKS_KEY: ClassVar[str] = "disks"
    BANDWIDTH_KEY: ClassVar[str] = "bandwidth"
    GROUP_ATTRIBUTE: ClassVar[str] = "group"
    CATEGORY_ATTRIBUTE: ClassVar[str] = "category"
    USE_ATTRIBUTE: ClassVar[str] = "use"
    MBPS_ATTRIBUTE: ClassVar[str] = "mbps"

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
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
        self.help_categories: Dict[str, List[str]] = {}
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
            aliases = (*self.NAME_ALIASES.get(product.name, ()), *(abbreviation.groups() if abbreviation else ()))
            self.logger.debug("Remembering %d alias(es) of the %s product %r.", len(aliases), self.name, product.name)
            self._remember(aliases)
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
            self.logger.debug("Requesting the %s documentation home page %s, waiting for its entries.", self.name, url)
            return Request(url, priority=self.HELP_PRIORITY, wait_selector=self.HELP_WAIT_SELECTOR)
        self.logger.debug("Requesting the %s complementary page %s.", self.name, url)
        return Request(url)

    def _source(self, url: str) -> AlibabaPageSource:
        """Tell which source a page is.

        Args:
            url (str): The page URL.

        Returns:
            AlibabaPageSource: `nav`, `help`, `sitemap` or `cards`.
        """
        link = urlparse(url)
        if link.netloc != urlparse(self.SITE_URL).netloc:
            return AlibabaPageSource.NAV
        if link.path.startswith("/help/"):
            return AlibabaPageSource.HELP
        if link.path.startswith("/sitemaps/"):
            return AlibabaPageSource.SITEMAP
        return AlibabaPageSource.CARDS

    def _slug_key(self, slug: str) -> str:
        """Normalize a page slug to compare the documentation slugs with the product page ones.

        Args:
            slug (str): The slug, e.g. `optimization-solver` or `optimization_solver`.

        Returns:
            str: The comparison key, e.g. `optimizationsolver`.
        """
        return re.sub(r"[\W_]+", "", slug.casefold())

    def _nav_category_products(
        self, category: Dict[str, JsonValue], path: Tuple[Optional[str], ...] = ()
    ) -> Iterator[CloudProduct]:
        """Extract the products of a navigation category and of its subcategories, depth first.

        Args:
            category (Dict[str, JsonValue]): The navigation category.
            path (Tuple[Optional[str], ...]): The names of the parent categories, top level first.

        Yields:
            Iterator[CloudProduct]: Each valid product of the category, filed under the category path.

        Notes:
            The category page, if any, is remembered as a category page.
        """
        if link := self._as_text(category.get(AlibabaNavCategoryField.URL)):
            self.category_urls.add(self._url_key(link))
        path = (*path, self._as_text(category.get(AlibabaNavCategoryField.NAME)))
        products = category.get(AlibabaNavCategoryField.PRODUCTS)
        if products is not None and not isinstance(products, list):
            self.logger.warning("The %s navigation category %s lists no product array, it is skipped.", self.name, path)
        found = 0
        for entry in products if isinstance(products, list) else []:
            fields = self._as_object(entry)
            name, url = (
                self._as_text(fields.get(AlibabaNavProductField.NAME)),
                self._as_text(fields.get(AlibabaNavProductField.URL)),
            )
            if product := self._build_product(
                name, self._as_text(fields.get(AlibabaNavProductField.SHORT_DESC)), url, categories=path
            ):
                found += 1
                yield product
        self.logger.debug("%d valid product(s) in the %s navigation category %s.", found, self.name, path)
        subcategories = category.get(AlibabaNavCategoryField.SUB_CATEGORIES)
        for subcategory in subcategories if isinstance(subcategories, list) else []:
            yield from self._nav_category_products(self._as_object(subcategory), path)

    def _nav_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the navigation product tree, without its ad groups and featured category.

        Args:
            response (Response): The navigation product tree (JSON).

        Yields:
            Iterator[CloudProduct]: Each valid product of the tree.

        Raises:
            CatalogueFormatError: If the document is not JSON or has no `detailedCategories` list.
        """
        categories = self._as_object(self._json_body(response)).get(AlibabaNavTreeField.DETAILED_CATEGORIES)
        if not isinstance(categories, list):
            self.logger.error("The %s product tree %s has no `detailedCategories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`detailedCategories` is not a list")
        self.logger.debug("%d navigation categories in %s.", len(categories), response.url)
        entries = (
            product for category in categories for product in self._nav_category_products(self._as_object(category))
        )
        yield from self._merge_categories(entries)

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
            sections = self._as_object(data).get(AlibabaCardsDataField.CONTENT)
            if isinstance(sections, list):
                return sections
        self.logger.error("The %s page %s embeds no product cards.", self.name, response.url)
        raise CatalogueFormatError(self.name, response.url, "the product cards (`render-container-data`) are missing")

    def _card_entries(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the "All products" cards, without the Academy section and the solutions.

        Args:
            response (Response): The "All products" page.

        Yields:
            Iterator[CloudProduct]: Each valid card, filed under its section and group titles.

        Raises:
            CatalogueFormatError: If the page embeds no product cards.
        """
        for section in map(self._as_object, self._cards_data(response)):
            title = self._clean_text(self._as_text(section.get(AlibabaCardsSectionField.FIRST_LEVEL_HEAD)))
            if title.casefold() in self.CARDS_EXCLUDED_SECTIONS:
                self.logger.debug("Skipping the %r section of %s, not products.", title, response.url)
                continue
            groups = section.get(AlibabaCardsSectionField.PRODUCT_CARD)
            for group in map(self._as_object, groups if isinstance(groups, list) else []):
                categories = [title, self._as_text(group.get(AlibabaCardsGroupField.CARD_TITLE))]
                cards = group.get(AlibabaCardsGroupField.CARD_LIST)
                for card in map(self._as_object, cards if isinstance(cards, list) else []):
                    name = self._as_text(card.get(AlibabaCardField.TITLE))
                    link = self._as_text(card.get(AlibabaCardField.URL)) or ""
                    if "solutions/" in link or self._name_key(name or "") in self.deprecated_names:
                        self.logger.debug("Skipping the card %r (%s), a solution or a deprecated product.", name, link)
                        continue
                    url = urljoin(self.SITE_URL, link) if link else None
                    description = self._as_text(card.get(AlibabaCardField.DESC))
                    if product := self._build_product(name, description, url, categories=categories):
                        yield product

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the "All products" cards.

        Args:
            response (Response): The "All products" page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the cards, with the categories of all its cards.

        Raises:
            CatalogueFormatError: If the page embeds no product cards.
        """
        yield from self._merge_categories(self._card_entries(response))

    def _help_entries(self, response: Response) -> List[Tuple[str, str, str]]:
        """Read the product entries of the documentation home page, without the guides, tools and deprecated ones.

        Args:
            response (Response): The documentation home page.

        Returns:
            List[Tuple[str, str, str]]: The product names, documentation slugs and block titles.

        Raises:
            CatalogueFormatError: If the page lists no documentation entry.
        """
        blocks = response.css('[class*="ProductList--allProductsBodyBlock"]')
        entries: List[Tuple[str, str, str]] = []
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
                slug = urlparse(link.attrib.get(HtmlAttribute.HREF, "")).path.strip("/").split("/")[-1]
                if self.DEPRECATED.search(name):
                    self.logger.debug("Skipping the documentation entry %r, deprecated.", name)
                    self.deprecated_names.add(self._name_key(self.DEPRECATED.sub("", name)))
                    continue
                if self.HELP_NOT_PRODUCT.search(name):
                    self.logger.debug("Skipping the documentation entry %r, not a product.", name)
                    continue
                entries.append((name, slug, title))
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
        for name, slug, title in self._help_entries(response):
            if self._name_key(name) in self.seen_products:
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
                continue
            self.help_names.setdefault(self._slug_key(slug), (name, slug))
            blocks = self.help_categories.setdefault(self._name_key(name), [])
            if title and title not in blocks:
                blocks.append(title)
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
        self.logger.debug("Requesting the %s documentation landing page %r of %r.", self.name, slug, name)
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
                if segment == AlibabaHelpArticleSlug.PRODUCT_INTRODUCTION:
                    candidates.append((2, urljoin(self.SITE_URL, path)))
            elif match.group("overview") is None or match.group("overview") == slug:
                rank = 0 if match.group(0).startswith(AlibabaHelpArticleSlug.WHAT_IS) else 1
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
        description = self._meta_content(response, PageMetaName.DESCRIPTION) or ""
        marker = f",{name}:".casefold()
        if (index := description.casefold().find(marker)) >= 0:
            description = self._clean_text(description[index + len(marker) :])
        if not description:
            paragraphs = (
                paragraph.get_all_text(separator=" ", strip=True) for paragraph in response.css(".markdown-body p")
            )
            description = next((self._clean_text(text) for text in paragraphs if self._clean_text(text)), "")
        if not description or self.HELP_BOILERPLATE.search(description):
            self.logger.debug("No genuine description of %r in the %s article %s.", name, self.name, response.url)
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
            self.logger.debug("The landing page %s of %r describes nothing, reading its overview.", response.url, name)
            return None
        slug = str(response.meta[self.HELP_LANDING])
        categories = self.help_categories.get(self._name_key(name))
        return self._build_product(name, description, self.HELP_LANDING_URL.format(slug=slug), categories=categories)

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
        categories = self.help_categories.get(self._name_key(name))
        return self._build_product(name, description, str(response.meta[self.HELP_ARTICLE]), categories=categories)

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
        title = title or self._meta_content(response, PageMetaName.OG_TITLE) or ""
        return self._page_title(title) or None

    def _page_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a product page, skipping the retired products.

        Args:
            response (Response): The product page, requested with the `PRODUCT_PAGE` meta.

        Returns:
            Optional[CloudProduct]: The product with the requested URL (without the tracking query), `None` for a
                retired, deprecated, unknown (redirected) or invalid product page.
        """
        if self.NOT_FOR_SALE in response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE).casefold():
            self.logger.debug("Skipping %s, the product is no longer available for sale.", response.url)
            return None
        product = super()._page_product(response)
        if product is None:
            return None
        if self._name_key(product.name) in self.deprecated_names:
            self.logger.debug("Skipping %s, %r is deprecated.", response.url, product.name)
            return None
        categories = self.help_categories.get(self._name_key(product.name))
        url = str(response.meta[self.PRODUCT_PAGE])
        return self._build_product(product.name, product.description, url, categories=categories)

    def _script_object(self, response: Response) -> JsonValue:
        """Read the object a price file assigns (`var X = {...}`).

        Args:
            response (Response): The price file.

        Returns:
            JsonValue: The object.

        Raises:
            CatalogueFormatError: If the file assigns no JSON object.
        """
        text = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            self.logger.error("The Alibaba Cloud price file %s assigns no object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price file assigns no JSON object")
        try:
            data: JsonValue = json.loads(text[start : end + 1])
        except ValueError as e:
            self.logger.error("The Alibaba Cloud price file %s assigns no JSON object: %s", response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the price file assigns no JSON object") from e
        return data

    def _instance_row_prices(
        self, row: JsonValue, system: str, region: str, group: str, source: str
    ) -> Iterator[ServicePrice]:
        """Read the prices of a row of the instance type prices.

        Args:
            row (JsonValue): The row: `[type, os, region, io optimized, vCPUs, memory, [7 prices], network, [7 list
                prices], [discounts]]`.
            system (str): Its operating system.
            region (str): Its region.
            group (str): Its generation and network.
            source (str): The price file (its source).

        Yields:
            ServicePrice: Its price per period (`PERIODS`).
        """
        if not isinstance(row, list) or len(row) < self.ROW_LENGTH or not isinstance(row[6], list):
            return
        instance, vcpu, memory = row[0], row[4], row[5]
        for index, (unit, months, term) in enumerate(self.PERIODS):
            amount = row[6][index] if index < len(row[6]) else None
            try:
                price = Decimal(str(amount))
            except ArithmeticError:
                continue
            fact = self._price_fact(
                {
                    "sku_key": f"{self.INSTANCES_KEY}/{region}/{system}/{group}/{instance}/{index}",
                    "service": self.ECS_SERVICE,
                    "family": self.INSTANCES_KEY,
                    "region": region,
                    "instance_type": instance,
                    "vcpu": vcpu if isinstance(vcpu, int) and vcpu > 0 else None,
                    "memory_gib": memory if isinstance(memory, (int, float)) and memory > 0 else None,
                    "os": system,
                    "attributes": {self.GROUP_ATTRIBUTE: group},
                    "unit": unit,
                    "unit_raw": unit.value if months <= 1 else f"{months} months",
                    "unit_factor": Decimal(months) if unit is PriceUnit.MONTH else Decimal(1),
                    "price": price,
                    "currency": self.PRICE_CURRENCY,
                    "model": PriceModel.FREE
                    if price == 0
                    else PriceModel.COMMITMENT
                    if months > 1
                    else PriceModel.ON_DEMAND,
                    "term": term,
                    "source_url": source,
                    "source_kind": PriceSourceKind.CALCULATOR,
                }
            )
            if fact is not None:
                yield fact

    def _instance_prices(self, data: JsonValue, source: str) -> Iterator[ServicePrice]:
        """Read the prices of the instance types: hourly, monthly, then for 1 to 5 years paid at once (discounted).

        Args:
            data (JsonValue): The instance type prices, by operating system, region, generation and network.
            source (str): The price file (its source).

        Yields:
            ServicePrice: A price per instance type, region, operating system and period.
        """
        for system, regions in (data if isinstance(data, dict) else {}).items():
            for region, generations in (regions if isinstance(regions, dict) else {}).items():
                for generation, networks in (generations if isinstance(generations, dict) else {}).items():
                    for network, groups in (networks if isinstance(networks, dict) else {}).items():
                        for rows in groups.values() if isinstance(groups, dict) else []:
                            for row in rows if isinstance(rows, list) else []:
                                yield from self._instance_row_prices(
                                    row, system, region, f"{generation}/{network}", source
                                )

    def _disk_prices(self, data: JsonValue, source: str) -> Iterator[ServicePrice]:
        """Read the disk prices: monthly and hourly, per 100 GB.

        Args:
            data (JsonValue): The disk prices, by region and kind.
            source (str): The price file (its source).

        Yields:
            ServicePrice: A monthly and an hourly price per region, disk use and category.
        """
        for region, kinds in (data if isinstance(data, dict) else {}).items():
            for kind, rows in kinds.items() if isinstance(kinds, dict) else []:
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, list) or len(row) < 5 or not isinstance(row[4], list):
                        continue
                    size, category = row[2], row[3]
                    level = row[5] if len(row) > 5 else ""
                    for (unit, written), amount in zip(self.DISK_UNITS, row[4], strict=False):
                        try:
                            price = Decimal(str(amount))
                        except ArithmeticError:
                            continue
                        fact = self._price_fact(
                            {
                                "sku_key": f"{self.DISKS_KEY}/{region}/{kind}/{category}/{level}/{written}",
                                "service": self.ECS_SERVICE,
                                "family": self.DISKS_KEY,
                                "region": region,
                                "attributes": {self.CATEGORY_ATTRIBUTE: category, self.USE_ATTRIBUTE: row[1]},
                                "unit": unit,
                                "unit_raw": f"{size} GB/{written}",
                                "unit_factor": Decimal(str(size)) if str(size).isdigit() else Decimal(1),
                                "price": price,
                                "currency": self.PRICE_CURRENCY,
                                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                                "source_url": source,
                                "source_kind": PriceSourceKind.CALCULATOR,
                            }
                        )
                        if fact is not None:
                            yield fact

    def _bandwidth_prices(self, data: JsonValue, source: str) -> Iterator[ServicePrice]:
        """Read the bandwidth prices: per Mbps value, monthly or hourly, and the traffic per GB.

        Args:
            data (JsonValue): The bandwidth prices, by region.
            source (str): The price file (its source).

        Yields:
            ServicePrice: A price per region, bandwidth value and unit.
        """
        for region, kinds in (data if isinstance(data, dict) else {}).items():
            for rows in kinds.values() if isinstance(kinds, dict) else []:
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, list) or len(row) < 4:
                        continue
                    try:
                        unit = self.BANDWIDTH_UNITS[AlibabaBandwidthUnit(str(row[2]))]
                        price = Decimal(str(row[3]))
                    except ValueError, ArithmeticError:
                        continue
                    fact = self._price_fact(
                        {
                            "sku_key": f"{self.BANDWIDTH_KEY}/{region}/{row[2]}/{row[1]}",
                            "service": self.ECS_SERVICE,
                            "family": self.BANDWIDTH_KEY,
                            "region": region,
                            "attributes": {self.MBPS_ATTRIBUTE: row[1]},
                            "unit": unit,
                            "unit_raw": str(row[2]),
                            "price": price,
                            "currency": self.PRICE_CURRENCY,
                            "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                            "source_url": source,
                            "source_kind": PriceSourceKind.CALCULATOR,
                        }
                    )
                    if fact is not None:
                        yield fact

    def _directory_pages(self, response: Response) -> Iterator[Request]:
        """Request the pricing pages listed by the pricing directory.

        Args:
            response (Response): The pricing directory.

        Yields:
            Request: One request per pricing page, named after its directory entry.

        Raises:
            CatalogueFormatError: If the directory holds no entries.
        """
        holder = response.css(self.DIRECTORY_DATA).first
        raw = holder.attrib.get("data-data", "") if holder is not None else ""
        try:
            data: JsonValue = json.loads(raw) if raw else None
        except json.JSONDecodeError as e:
            self.logger.error("The %s pricing directory %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the pricing directory is not JSON") from e
        groups = data.get("product") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            self.logger.error("The %s pricing directory %s holds no entries.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the pricing directory holds no entries")
        pages: Dict[str, str] = {}
        for group in groups:
            items = group.get("productItem") if isinstance(group, dict) else None
            for item in items if isinstance(items, list) else []:
                children = item.get("child") if isinstance(item, dict) else None
                for child in children if isinstance(children, list) else []:
                    name = child.get("h4s") if isinstance(child, dict) else None
                    link = child.get("url") if isinstance(child, dict) else None
                    if isinstance(name, str) and isinstance(link, str) and link:
                        pages.setdefault(urljoin(self.SITE_URL, link.strip()), name.strip())
        self.logger.info("%d %s pricing pages in the pricing directory.", len(pages), self.name)
        for url, name in pages.items():
            yield self._price_request(url, {self.PRODUCT_PAGE_META: name})

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the loader of the ECS price list, the pricing directory and the Model Studio pricing page.

        Yields:
            Request: The loader, directory and Model Studio requests (the pricing pages and the Model Studio page
                being read by the base reader of product pages).
        """
        self.logger.info("Reading the Alibaba Cloud ECS prices from %s.", self.PRICE_LOADER_URL)
        yield self._price_request(self.PRICE_LOADER_URL)
        self.logger.info("Reading the Alibaba Cloud pricing pages listed by %s.", self.PRICING_DIRECTORY_URL)
        yield self._price_request(self.PRICING_DIRECTORY_URL, {self.DIRECTORY_META: True})
        yield self._price_request(self.MODEL_PRICES_URL, {self.PRODUCT_PAGE_META: self.MODEL_SERVICE})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the loader (requesting each changed price file), a price file, or the pricing directory.

        Args:
            response (Response): The loader, a price file, or the pricing directory.

        Yields:
            PriceFact: The price file requests, the prices of a file, or the pricing page requests.

        Raises:
            CatalogueFormatError: If a price file assigns no JSON object, or the directory holds no entries.
        """
        if response.meta.get(self.DIRECTORY_META):
            for request in self._directory_pages(response):
                yield request
            return
        name = response.meta.get(self.PRICE_FILE)
        if not isinstance(name, str):
            text = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
            for url in self.PRICE_FILE_URL.findall(text):
                file_name = url.rsplit("/", 1)[-1]
                version = self.FILE_VERSION.search(url)
                if file_name not in tuple(AlibabaPriceFile) or version is None:
                    continue
                source = self.FILE_VERSION.sub("/", url)
                if self._price_unchanged(source, version=version[1]):
                    continue
                yield self._price_request(url, {self.PRICE_FILE: file_name, self.PRICE_VERSION: version[1]})
            return
        data = self._script_object(response)
        file_version = str(response.meta.get(self.PRICE_VERSION) or "")
        source = self.FILE_VERSION.sub("/", response.url)
        if name == AlibabaPriceFile.DISKS:
            facts = self._disk_prices(data, source)
        elif name == AlibabaPriceFile.BANDWIDTH:
            facts = self._bandwidth_prices(data, source)
        else:
            facts = self._instance_prices(data, source)
        found = 0
        for fact in facts:
            found += 1
            yield fact
        self._record_price_source(source, found, version=file_version or None)
        self.logger.info("The Alibaba Cloud price file %s (%s) is read: %d prices.", name, file_version, found)

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
        if self._source(response.url) == AlibabaPageSource.NAV:
            self.logger.debug("Extracting the %s products of the navigation tree %s.", self.name, response.url)
            return self._nav_products(response)
        self.logger.debug("Extracting the %s product cards of %s.", self.name, response.url)
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
            else:
                self.logger.debug("Nothing new streamed from the %s documentation page %s.", self.name, response.url)
            return
        if self.HELP_SLUG in response.meta and self._page_description(response) is None:
            self.logger.debug("The product page %s has no description, reading its documentation.", response.url)
            yield self._help_landing_request(str(response.meta[self.PRODUCT_NAME]), str(response.meta[self.HELP_SLUG]))
            return
        source = self._source(response.url)
        if self.PRODUCT_PAGE not in response.meta and source == AlibabaPageSource.HELP:
            self.logger.debug("Reading the %s documentation home page %s.", self.name, response.url)
            yield self._help_request(response)
            return
        if self.PRODUCT_PAGE not in response.meta and source == AlibabaPageSource.SITEMAP:
            self.logger.debug("Reading the %s sitemap %s.", self.name, response.url)
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
