from __future__ import annotations

# Standard Library Imports.
import json
import re
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.tencent.enums import (
    TencentArticleField,
    TencentCardClass,
    TencentChargeType,
    TencentCrawlerMeta,
    TencentDocsDataField,
    TencentDocsEntryField,
    TencentDocsGroup,
    TencentDocsPagePropsField,
    TencentDocsSectionField,
    TencentDocsSlug,
    TencentNextDataField,
    TencentPriceField,
    TencentSlateField,
    TencentSlateType,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class TencentCloudCrawler(BaseCloudCrawler):
    """Tencent Cloud (international website) catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root.
        PRODUCTS_URL (ClassVar[str]): The products page, rendered by a script, the main source.
        DOCS_URL (ClassVar[str]): The documentation home page, listing every product documentation.
        CARD_SELECTOR (ClassVar[str]): The product cards of the products page, which are waited for.
        DOCS_WAIT_SELECTOR (ClassVar[str]): The Next.js data of the documentation home page, which is waited for.
        PAGE_WAIT_SELECTOR (ClassVar[str]): The title of a product page, missing from the bot challenge page.
        DOCS_EXCLUDED_GROUPS (ClassVar[FrozenSet[TencentDocsGroup]]): The documentation groups which are not
            products.
        DOCS_EXCLUDED_SLUGS (ClassVar[FrozenSet[TencentDocsSlug]]): The documentation entries which are not products
            (marketplace, SDK, announcements, partners, records, messages).
        SLUG (ClassVar[re.Pattern[str]]): A valid product slug.
        TITLE_SUFFIX (ClassVar[re.Pattern[str]]): The brand suffix of the product page titles.
        DOC_URL (ClassVar[str]): The documentation of a product, by documentation id.
        OVERVIEW_SECTION (ClassVar[re.Pattern[str]]): The documentation section holding the product overview.
        OVERVIEW_PAGE (ClassVar[re.Pattern[str]]): The overview article of that section.
        NAME_ALIASES (ClassVar[Dict[str, Tuple[str, ...]]]): The documentation names of products listed under
            another name, by listed name.
        DOC_ID (ClassVar[TencentCrawlerMeta]): The meta key holding the documentation id of a product page request.
        DOC_CATALOGUE (ClassVar[TencentCrawlerMeta]): The meta key marking a product documentation request, holding
            the product URL.
        DOC_ARTICLE (ClassVar[TencentCrawlerMeta]): The meta key marking an overview article request, holding the
            product URL.
        CATEGORY_HEADING (ClassVar[TencentCardClass]): The class of the category headings of the products page.
        SUBCATEGORY_HEADING (ClassVar[TencentCardClass]): The class of the subcategory headings of the products page.
        REGIONS_URL (ClassVar[str]): The CVM documentation page listing the regions and their codes.
        REGION_TEXT (ClassVar[str]): The text nodes of that page.
        REGION_CODE (ClassVar[re.Pattern[str]]): A region code (a zone code ends with its number).
        PRICES_URL (ClassVar[str]): The CVM purchase API of the purchase page (POST, no key), proxied by the console.
        PURCHASE_URL (ClassVar[str]): The purchase page, the origin the API expects.
        PRICE_CALL (ClassVar[Dict[str, JsonValue]]): The fixed part of a call body (service, action and version).
        UNSUPPORTED (ClassVar[FrozenSet[str]]): The error codes of a region where CVM is not sold (no price).
        CVM_SERVICE (ClassVar[str]): The service of the prices.
        PRICE_CURRENCY (ClassVar[str]): The currency of the prices (yuan, not stated by the API).
        STEP_HOURS (ClassVar[Tuple[Decimal, ...]]): The usage hours in the month from which each step of an hourly
            price applies.
        STEP_FIELDS (ClassVar[Tuple[TencentPriceField, ...]]): The hourly price of each step.
        PREPAID_PERIODS (ClassVar[Tuple[Tuple[TencentPriceField, int, PriceTerm], ...]]): The prepaid prices: their
            field, months and term.
        REGION_META (ClassVar[str]): The request meta holding the region of a call.
        CHARGE_META (ClassVar[str]): The request meta holding the charge type of a call.
        DOC_HOST (ClassVar[str]): The mainland documentation website.
        HYDRATION (ClassVar[re.Pattern[str]]): The state embedded in a documentation page (a JSON string parsed by
            `JSON.parse`).
        PRODUCT_SLUG (ClassVar[re.Pattern[str]]): The slug of a catalogue product page, e.g. `/products/cos`.
        DOC_PRODUCT (ClassVar[re.Pattern[str]]): The identifier of a product documentation, e.g.
            `/document/product/436`.
        PRICE_DOC_TYPE (ClassVar[str]): The document type of the pricing section of a documentation.
        PRICE_TITLE (ClassVar[re.Pattern[str]]): The titles of the pricing pages of that section.
        NOT_PRICE_TITLE (ClassVar[re.Pattern[str]]): The titles of its pages which are not price lists (refunds,
            overdue payments, renewals, guides, notices, API).
        SIDEBAR_META (ClassVar[str]): The request meta holding the catalogue product of a documentation request.
        price_pending (int): The calls not answered yet, in price mode.
        price_rows (int): The prices read, in price mode.

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
        The categories of a card are the category and subcategory headings above it on the products page. Those of
        a documentation entry are its group and parent entry titles, carried by its product page request
        (`PRODUCT_CATEGORIES` meta) on to its documentation and overview article requests.
        In price mode it reads the CVM prices, in yuan, from the purchase API of the mainland site (the
        international site being behind the challenge): one call per region (from the CVM regions documentation)
        and charge type. Pay-as-you-go prices are hourly, in up to three steps of usage hours in the month (the
        tiers). Prepaid prices are monthly, then for 1, 3, 5 and 6 years paid at once (per month, their factor
        being their months). Sold-out instance types keep their price, their status stated. The API is one source,
        recorded once every call is answered.
        The regions documentation also gives the documentation menu (`popupNav`, a slug and a documentation id per
        product): each catalogue product whose page slug (or documentation link) is in it gets its documentation
        read, whose pricing section (`docType` `price`) lists its price pages, read by the base reader of product
        pages, named after the catalogue product.
    """

    SITE_URL: ClassVar[str] = "https://www.tencentcloud.com"
    PRODUCTS_URL: ClassVar[str] = f"{SITE_URL}/product"
    DOCS_URL: ClassVar[str] = f"{SITE_URL}/document/product"
    CARD_SELECTOR: ClassVar[str] = "a.v3-product-menu-card-cell-link"
    DOCS_WAIT_SELECTOR: ClassVar[str] = "script#__NEXT_DATA__"
    PAGE_WAIT_SELECTOR: ClassVar[str] = "head > title"
    DOCS_EXCLUDED_GROUPS: ClassVar[FrozenSet[TencentDocsGroup]] = frozenset({TencentDocsGroup.MORE})
    DOCS_EXCLUDED_SLUGS: ClassVar[FrozenSet[TencentDocsSlug]] = frozenset(TencentDocsSlug)
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
    DOC_ID: ClassVar[TencentCrawlerMeta] = TencentCrawlerMeta.DOC_ID
    DOC_CATALOGUE: ClassVar[TencentCrawlerMeta] = TencentCrawlerMeta.DOC_CATALOGUE
    DOC_ARTICLE: ClassVar[TencentCrawlerMeta] = TencentCrawlerMeta.DOC_ARTICLE
    CATEGORY_HEADING: ClassVar[TencentCardClass] = TencentCardClass.CATEGORY_HEADING
    SUBCATEGORY_HEADING: ClassVar[TencentCardClass] = TencentCardClass.SUBCATEGORY_HEADING
    REGIONS_URL: ClassVar[str] = "https://cloud.tencent.com/document/product/213/6091"
    REGION_TEXT: ClassVar[str] = "span[data-slate-string]"
    REGION_CODE: ClassVar[re.Pattern[str]] = re.compile(r"^(?:ap|na|eu|sa|me)-[a-z]+$")
    PRICES_URL: ClassVar[str] = "https://workbench.cloud.tencent.com/cgi/api?i=cvm/DescribeZoneInstanceConfigInfos"
    PURCHASE_URL: ClassVar[str] = "https://buy.cloud.tencent.com"
    PRICE_CALL: ClassVar[Dict[str, JsonValue]] = {
        "serviceType": "cvm",
        "action": "DescribeZoneInstanceConfigInfos",
        "regionId": 1,
    }
    UNSUPPORTED: ClassVar[FrozenSet[str]] = frozenset({"InvalidParameterValue.ZoneNotSupported"})
    CVM_SERVICE: ClassVar[str] = "Cloud Virtual Machine"
    PRICE_CURRENCY: ClassVar[str] = "CNY"
    STEP_HOURS: ClassVar[Tuple[Decimal, ...]] = (Decimal(0), Decimal(96), Decimal(360))
    STEP_FIELDS: ClassVar[Tuple[TencentPriceField, ...]] = (
        TencentPriceField.UNIT_PRICE_DISCOUNT,
        TencentPriceField.SECOND_STEP_PRICE,
        TencentPriceField.THIRD_STEP_PRICE,
    )
    PREPAID_PERIODS: ClassVar[Tuple[Tuple[TencentPriceField, int, PriceTerm], ...]] = (
        (TencentPriceField.DISCOUNT_PRICE, 1, PriceTerm.MONTH),
        (TencentPriceField.ONE_YEAR_PRICE, 12, PriceTerm.ONE_YEAR),
        (TencentPriceField.THREE_YEARS_PRICE, 36, PriceTerm.THREE_YEARS),
        (TencentPriceField.FIVE_YEARS_PRICE, 60, PriceTerm.FIVE_YEARS),
        (TencentPriceField.SIX_YEARS_PRICE, 72, PriceTerm.SIX_YEARS),
    )
    REGION_META: ClassVar[str] = "price_region"
    CHARGE_META: ClassVar[str] = "price_charge"
    DOC_HOST: ClassVar[str] = "https://cloud.tencent.com"
    HYDRATION: ClassVar[re.Pattern[str]] = re.compile(
        r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\((\"(?:[^\"\\]|\\.)*\")\)", re.S
    )
    PRODUCT_SLUG: ClassVar[re.Pattern[str]] = re.compile(r"/products?/(?P<slug>[a-z0-9_-]+)")
    DOC_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(r"/document/product/(?P<id>\d+)")
    PRICE_DOC_TYPE: ClassVar[str] = "price"
    PRICE_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"价格|定价|计费|费用")
    NOT_PRICE_TITLE: ClassVar[re.Pattern[str]] = re.compile(r"退费|欠费|续费|指引|公告|API|变更|调整")
    SIDEBAR_META: ClassVar[str] = "price_sidebar"

    name = "tencent"
    catalogue_url: ClassVar[str] = PRODUCTS_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (DOCS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Tencent Cloud ", "TencentCloud ", "Tencent ", "T-Sec ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_pending = 0
        self.price_rows = 0

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
        """Build the documentation home page request, waiting for its Next.js data once the challenge is passed.

        Args:
            url (str): The documentation home page.

        Returns:
            Request: The request, waiting for the `__NEXT_DATA__` script.
        """
        return Request(url, wait_selector=self.DOCS_WAIT_SELECTOR)

    def _product_page_request(
        self,
        url: str,
        name: Optional[str] = None,
        updated: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> Optional[Request]:
        """Build the request of a product page, waiting for its title once the challenge is passed.

        Args:
            url (str): The absolute product page URL.
            name (Optional[str]): The product name given by the documentation.
            updated (Optional[str]): The last modification of the page given by a sitemap.
            categories (Optional[Sequence[str]]): The documentation groups of the product (`PRODUCT_CATEGORIES`
                meta), if any.

        Returns:
            Optional[Request]: The request, `None` when a product of this page was already streamed.
        """
        request = super()._product_page_request(url, name, updated, categories)
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
        headings = f"h3.{self.CATEGORY_HEADING}, h3.{self.SUBCATEGORY_HEADING}, {self.CARD_SELECTOR}"
        category: Optional[str] = None
        subcategory: Optional[str] = None
        for card in response.css(headings):
            classes = card.attrib.get(HtmlAttribute.CLASS, "").split()
            if self.CATEGORY_HEADING in classes or self.SUBCATEGORY_HEADING in classes:
                label = str(card.get_all_text(separator=" ", strip=True))
                category, subcategory = (label, None) if self.CATEGORY_HEADING in classes else (category, label)
                continue
            title = card.css("h3.v3-product-menu-card-cell-tit").first
            description = card.css("div.v3-product-menu-card-cell-desc").first
            if TencentCardClass.LINK_ITEM in card.attrib.get(HtmlAttribute.CLASS, "") or title is None:
                self.logger.debug("Skipping the link %s, not a product card.", card.attrib.get(HtmlAttribute.HREF))
                continue
            name = title.get_all_text(separator=" ", strip=True)
            text = description.get_all_text(separator=" ", strip=True) if description is not None else None
            url = self._product_url(card.attrib.get(HtmlAttribute.HREF, ""))
            if product := self._build_product(name, text, url, categories=[category, subcategory]):
                yield product

    def _docs_leaves(
        self, node: Dict[str, JsonValue], path: Tuple[str, ...] = ()
    ) -> Iterator[Tuple[Dict[str, JsonValue], Tuple[str, ...]]]:
        """Walk the documentation entries without children, depth first.

        Args:
            node (Dict[str, JsonValue]): A documentation group or entry.
            path (Tuple[str, ...]): The titles of the parent entries, top level first.

        Yields:
            Tuple[Dict[str, JsonValue], Tuple[str, ...]]: Each entry without children, with the titles of its
                parent entries.
        """
        children = node.get(TencentDocsEntryField.CHILDREN)
        if not isinstance(children, list) or not children:
            yield node, path
            return
        path = (*path, self._clean_text(self._as_text(node.get(TencentDocsEntryField.TITLE))))
        for child in children:
            yield from self._docs_leaves(self._as_object(child), path)

    def _docs_entries(self, response: Response) -> List[Tuple[str, str, str, List[str]]]:
        """Read the product entries of the documentation home page, without the excluded groups and entries.

        Args:
            response (Response): The documentation home page.

        Returns:
            List[Tuple[str, str, str, List[str]]]: The product names, slugs, documentation ids and categories (the
                group title, then the parent entry titles).

        Raises:
            CatalogueFormatError: If the page has no Next.js data or no `catalogueList` list.
        """
        props = self._as_object(self._next_data(response).get(TencentNextDataField.PROPS))
        groups = self._as_object(props.get(TencentNextDataField.PAGE_PROPS)).get(
            TencentDocsPagePropsField.CATALOGUE_LIST
        )
        if not isinstance(groups, list):
            self.logger.error("The %s documentation page %s has no `catalogueList` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`catalogueList` is not a list")
        entries: List[Tuple[str, str, str, List[str]]] = []
        for group in map(self._as_object, groups):
            title = self._clean_text(self._as_text(group.get(TencentDocsEntryField.TITLE)))
            if title.casefold() in self.DOCS_EXCLUDED_GROUPS:
                self.logger.debug("Skipping the documentation group %r, not products.", title)
                continue
            children = group.get(TencentDocsEntryField.CHILDREN)
            for child in children if isinstance(children, list) else []:
                for leaf, path in self._docs_leaves(self._as_object(child), (title,)):
                    name = self._clean_text(self._as_text(leaf.get(TencentDocsEntryField.TITLE)))
                    slug = self._clean_text(self._as_text(leaf.get(TencentDocsEntryField.SLUG))).casefold()
                    link = self._as_text(leaf.get(TencentDocsEntryField.URL)) or ""
                    if slug in self.DOCS_EXCLUDED_SLUGS or "/document/" in link or not self.SLUG.match(slug):
                        self.logger.debug("Skipping the documentation entry %r (%s), not a product.", name, slug)
                        continue
                    categories = list(dict.fromkeys(label for label in path if label))
                    entries.append((name, slug, str(leaf.get(TencentDocsEntryField.ID) or ""), categories))
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
        for name, slug, doc_id, categories in entries:
            if self._name_key(name) in self.seen_products:
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
                continue
            if request := self._product_page_request(f"{self.SITE_URL}/products/{slug}", name, categories=categories):
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
        if self.PRODUCT_CATEGORIES in response.meta:
            meta[self.PRODUCT_CATEGORIES] = response.meta[self.PRODUCT_CATEGORIES]
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
        props = self._as_object(self._next_data(response).get(TencentNextDataField.PROPS))
        return self._as_object(props.get(TencentNextDataField.PAGE_PROPS))

    def _overview_link(self, sections: JsonValue) -> Optional[str]:
        """Find the overview article in the table of contents of a product documentation.

        Args:
            sections (JsonValue): The top level sections (`data.list`).

        Returns:
            Optional[str]: The overview article path, e.g. `/document/product/1311/83642`, `None` without one.
        """
        for section in map(self._as_object, sections if isinstance(sections, list) else []):
            if not self.OVERVIEW_SECTION.search(
                self._clean_text(self._as_text(section.get(TencentDocsSectionField.TITLE)))
            ):
                continue
            children = section.get(TencentDocsSectionField.CHILDREN)
            pages = [self._as_object(child) for child in (children if isinstance(children, list) else [])]
            page = next(
                (page for page in pages if self.OVERVIEW_PAGE.search(str(page.get(TencentDocsSectionField.TITLE)))),
                section,
            )
            return self._as_text(page.get(TencentDocsSectionField.LINK)) or self._as_text(
                section.get(TencentDocsSectionField.LINK)
            )
        self.logger.debug(
            "No %s overview section among the %s documentation sections.",
            self.name,
            len(sections) if isinstance(sections, list) else 0,
        )
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
        link = self._overview_link(
            self._as_object(self._page_props(response).get(TencentDocsPagePropsField.DATA)).get(
                TencentDocsDataField.LIST
            )
        )
        name = response.meta[self.PRODUCT_NAME]
        if link is None:
            self.logger.debug("Skipping %r, its documentation %s has no overview article.", name, response.url)
            return None
        meta: Dict[str, JsonValue] = {self.DOC_ARTICLE: response.meta[self.DOC_CATALOGUE], self.PRODUCT_NAME: name}
        if self.PRODUCT_CATEGORIES in response.meta:
            meta[self.PRODUCT_CATEGORIES] = response.meta[self.PRODUCT_CATEGORIES]
        return Request(f"{self.SITE_URL}{link}", meta=meta, wait_selector=self.DOCS_WAIT_SELECTOR)

    def _slate_text(self, node: JsonValue) -> str:
        """Get the text of a rich text node of an article, with its children.

        Args:
            node (JsonValue): The rich text node.

        Returns:
            str: The text of the node.
        """
        fields = self._as_object(node)
        children = fields.get(TencentSlateField.CHILDREN)
        texts = [self._slate_text(child) for child in (children if isinstance(children, list) else [])]
        return (self._as_text(fields.get(TencentSlateField.TEXT)) or "") + "".join(texts)

    def _doc_article_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product described by its overview article.

        Args:
            response (Response): The overview article, requested with the `DOC_ARTICLE` meta.

        Returns:
            Optional[CloudProduct]: The product, with its documentation as URL, `None` without description.

        Raises:
            CatalogueFormatError: If the page has no Next.js data.
        """
        detail = self._as_object(self._page_props(response).get(TencentDocsPagePropsField.DETAIL_CONTENT))
        name = str(response.meta[self.PRODUCT_NAME])
        description = self._clean_text(self._as_text(detail.get(TencentArticleField.DESCRIPTION)))
        if not description:
            try:
                nodes: JsonValue = json.loads(self._as_text(detail.get(TencentArticleField.SLATE)) or "[]")
            except json.JSONDecodeError:
                nodes = []
            paragraphs = (
                node
                for node in (nodes if isinstance(nodes, list) else [])
                if self._as_object(node).get(TencentSlateField.TYPE) == TencentSlateType.PARAGRAPH
            )
            description = next((text for node in paragraphs if (text := self._clean_text(self._slate_text(node)))), "")
        if not description:
            self.logger.debug("Skipping %r, its overview article %s has no description.", name, response.url)
            return None
        url = str(response.meta[self.DOC_ARTICLE])
        return self._build_product(name, description, url, categories=self._page_categories(response))

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

    def _regions(self, response: Response) -> List[str]:
        """Read the region codes of the CVM regions documentation.

        Args:
            response (Response): The documentation page.

        Returns:
            List[str]: The region codes, in page order.

        Raises:
            CatalogueFormatError: If the page lists no region.
        """
        regions: List[str] = []
        for node in response.css(self.REGION_TEXT):
            text = self._clean_text(str(node.text))
            if self.REGION_CODE.match(text) and text not in regions:
                regions.append(text)
        if not regions:
            self.logger.error("The %s regions documentation %s lists no region.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the regions documentation lists no region")
        self.logger.debug("The %s regions documentation lists %d regions.", self.name, len(regions))
        return regions

    def _cvm_request(self, region: str, charge: TencentChargeType) -> Request:
        """Build a counted call to the CVM purchase API, for the instance types of a region and charge type.

        Args:
            region (str): The region code.
            charge (TencentChargeType): The charge type.

        Returns:
            Request: The POST request, with the headers the console proxy expects.
        """
        self.price_pending += 1
        body: Dict[str, JsonValue] = {
            **self.PRICE_CALL,
            "data": {
                "Version": "2017-03-12",
                "Filters": [{"Name": "instance-charge-type", "Values": [charge.value]}],
            },
            "region": region,
        }
        headers = {
            "Referer": f"{self.PURCHASE_URL}/",
            "Origin": self.PURCHASE_URL,
            "X-CsrfCode": "",
            "X-SeqId": str(uuid.uuid4()),
        }
        url = f"{self.PRICES_URL}&t={int(time.time() * 1000)}"
        return self._price_request(url, {self.REGION_META: region, self.CHARGE_META: charge.value}, body, headers)

    def _quotas(self, response: Response, region: str) -> List[Dict[str, JsonValue]]:
        """Read the instance types of a CVM purchase API answer.

        Args:
            response (Response): The answer.
            region (str): The region of the call.

        Returns:
            List[Dict[str, JsonValue]]: The instance types of the zones of the region, with their price, none in a
                region where CVM is not sold.

        Raises:
            CatalogueFormatError: If the answer is another error or has no instance type list.
        """
        data = self._json_body(response)
        answer = data.get(TencentPriceField.DATA) if isinstance(data, dict) else None
        result = answer.get(TencentPriceField.RESPONSE) if isinstance(answer, dict) else None
        quotas = result.get(TencentPriceField.QUOTAS) if isinstance(result, dict) else None
        if isinstance(quotas, list):
            return [quota for quota in quotas if isinstance(quota, dict)]
        error = result.get(TencentPriceField.ERROR) if isinstance(result, dict) else None
        code = error.get(TencentPriceField.CODE) if isinstance(error, dict) else None
        if code in self.UNSUPPORTED:
            self.logger.warning("The %s CVM purchase API sells no instance in %s (%s).", self.name, region, code)
            return []
        self.logger.error("The %s CVM purchase API answered without prices in %s: %s", self.name, region, error)
        raise CatalogueFormatError(self.name, response.url, f"the CVM purchase API answered without prices in {region}")

    def _amount(self, prices: Dict[str, JsonValue], field: TencentPriceField) -> Optional[Decimal]:
        """Read a price of an instance type.

        Args:
            prices (Dict[str, JsonValue]): Its prices.
            field (TencentPriceField): The price read.

        Returns:
            Optional[Decimal]: The price, or None when missing or unreadable.
        """
        value = prices.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            return None
        return Decimal(str(value))

    def _quota_prices(self, quota: Dict[str, JsonValue], region: str, charge: str) -> Iterator[ServicePrice]:
        """Read the prices of an instance type in a zone.

        Args:
            quota (Dict[str, JsonValue]): The instance type, with its price.
            region (str): The region of the call.
            charge (str): The charge type of the call.

        Yields:
            ServicePrice: Its hourly price per step (pay as you go), or its monthly and yearly prices (prepaid).
        """
        prices = quota.get(TencentPriceField.PRICE)
        zone, instance = quota.get(TencentPriceField.ZONE), quota.get(TencentPriceField.INSTANCE_TYPE)
        if not isinstance(prices, dict) or not isinstance(instance, str) or not instance:
            return
        cpu, memory, gpu = (
            quota.get(TencentPriceField.CPU),
            quota.get(TencentPriceField.MEMORY),
            quota.get(TencentPriceField.GPU),
        )
        attributes: Dict[str, JsonValue] = {
            field.value: quota.get(field)
            for field in (
                TencentPriceField.ZONE,
                TencentPriceField.TYPE_NAME,
                TencentPriceField.CPU_TYPE,
                TencentPriceField.STATUS,
            )
            if quota.get(field)
        }
        if isinstance(gpu, (int, float)) and gpu > 0:
            attributes[TencentPriceField.GPU.value] = gpu
        base: Dict[str, RawValue] = {
            "service": self.CVM_SERVICE,
            "family": quota.get(TencentPriceField.INSTANCE_FAMILY) or None,
            "region": region,
            "instance_type": instance,
            "vcpu": cpu if isinstance(cpu, int) and cpu > 0 else None,
            "memory_gib": memory if isinstance(memory, (int, float)) and memory > 0 else None,
            "attributes": attributes,
            "currency": self.PRICE_CURRENCY,
            "source_url": self.PRICES_URL,
            "source_kind": PriceSourceKind.CALCULATOR,
        }
        key = f"{zone}/{instance}/{charge}"
        if charge == TencentChargeType.POSTPAID:
            steps = [self._amount(prices, field) for field in self.STEP_FIELDS]
            found = [(index, step) for index, step in enumerate(steps) if step is not None]
            stepped = len({step for _, step in found}) > 1
            for index, step in found if stepped else found[:1]:
                end = self.STEP_HOURS[index + 1] if stepped and index + 1 < len(found) else None
                fact = self._price_fact(
                    {
                        **base,
                        "sku_key": f"{key}/{index}" if stepped else key,
                        "unit": PriceUnit.HOUR,
                        "unit_raw": str(prices.get(TencentPriceField.CHARGE_UNIT) or PriceUnit.HOUR.value),
                        "unit_factor": Decimal(1),
                        "price": step,
                        "model": PriceModel.FREE if step == 0 else PriceModel.ON_DEMAND,
                        "term": PriceTerm.NONE,
                        "tier_start": self.STEP_HOURS[index] if stepped else Decimal(0),
                        "tier_end": end,
                    }
                )
                if fact is not None:
                    yield fact
            return
        for field, months, term in self.PREPAID_PERIODS:
            price = self._amount(prices, field)
            if price is None:
                continue
            fact = self._price_fact(
                {
                    **base,
                    "sku_key": f"{key}/{months}",
                    "unit": PriceUnit.MONTH,
                    "unit_raw": f"{months} months",
                    "unit_factor": Decimal(months),
                    "price": price,
                    "model": PriceModel.FREE if price == 0 else PriceModel.COMMITMENT,
                    "term": term,
                }
            )
            if fact is not None:
                yield fact

    def _price_settled(self) -> None:
        """Count a call as answered, and record the API once every call is answered."""
        self.price_pending -= 1
        if self.price_pending == 0 and not self.price_failures:
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The %s CVM prices are read whole: %d prices.", self.name, self.price_rows)

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the CVM regions documentation, which leads to the purchase API calls.

        Yields:
            Request: The documentation request.
        """
        self.price_pending = 1
        self.price_rows = 0
        self.logger.info("Reading the %s CVM regions from %s.", self.name, self.REGIONS_URL)
        yield self._price_request(self.REGIONS_URL)

    def _hydration(self, response: Response) -> Dict[str, JsonValue]:
        """Read the state embedded in a mainland documentation page.

        Args:
            response (Response): The documentation page.

        Returns:
            Dict[str, JsonValue]: The state, empty when the page embeds none.
        """
        match = self.HYDRATION.search(response.body.decode("utf-8", errors="replace"))
        if match is None:
            self.logger.warning("The %s documentation page %s embeds no state.", self.name, response.url)
            return {}
        try:
            state = json.loads(json.loads(match.group(1)))
        except json.JSONDecodeError as e:
            self.logger.warning("The state of the %s documentation page %s is not JSON: %s", self.name, response.url, e)
            return {}
        return state if isinstance(state, dict) else {}

    def _doc_menu(self, state: Dict[str, JsonValue]) -> Dict[str, int]:
        """Read the documentation menu: the documentation identifier of each product slug.

        Args:
            state (Dict[str, JsonValue]): The state of a documentation page.

        Returns:
            Dict[str, int]: The documentation identifier of each slug.
        """
        loader = state.get("loaderData")
        product = loader.get("product") if isinstance(loader, dict) else None
        data = product.get("data") if isinstance(product, dict) else None
        plugins = data.get("plugins") if isinstance(data, dict) else None
        menu = plugins.get("popupNav") if isinstance(plugins, dict) else None
        pending: List[JsonValue] = [menu.get("data") if isinstance(menu, dict) else None]
        found: Dict[str, int] = {}
        while pending:
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                slug, ident = node.get("slug"), node.get("id")
                if isinstance(slug, str) and isinstance(ident, int) and not node.get("children"):
                    found.setdefault(slug, ident)
                pending.append(node.get("children"))
        self.logger.debug("%d products in the %s documentation menu.", len(found), self.name)
        return found

    def _doc_requests(self, response: Response) -> Iterator[Request]:
        """Request the documentation of each catalogue product found in the documentation menu.

        Args:
            response (Response): The regions documentation page (any documentation page holds the menu).

        Yields:
            Request: One documentation request per catalogue product.
        """
        menu = self._doc_menu(self._hydration(response))
        docs: Dict[int, str] = {}
        for name, url in self.price_products.items():
            link = url or ""
            documented = self.DOC_PRODUCT.search(link) if "tencent.com/document" in link else None
            slug = self.PRODUCT_SLUG.search(link)
            ident = int(documented.group("id")) if documented else menu.get(slug.group("slug")) if slug else None
            if ident is not None:
                docs.setdefault(ident, name)
        self.logger.info("%d %s catalogue products have a documentation to read for prices.", len(docs), self.name)
        for ident, name in docs.items():
            yield self._price_request(f"{self.DOC_HOST}/document/product/{ident}", {self.SIDEBAR_META: name})

    def _price_doc_pages(self, response: Response) -> Iterator[Request]:
        """Request the price pages of the pricing section of a product documentation.

        Args:
            response (Response): The product documentation.

        Yields:
            Request: One request per price page, named after the catalogue product.
        """
        name = str(response.meta.get(self.SIDEBAR_META))
        state = self._hydration(response)
        loader = state.get("loaderData")
        product = loader.get("product") if isinstance(loader, dict) else None
        data = product.get("data") if isinstance(product, dict) else None
        sidebar = data.get("sidebar") if isinstance(data, dict) else None
        catalogue = sidebar.get("catalogue") if isinstance(sidebar, dict) else None
        pending: List[Tuple[JsonValue, bool]] = [
            (catalogue.get("list") if isinstance(catalogue, dict) else None, False)
        ]
        links: List[str] = []
        while pending:
            node, priced = pending.pop()
            if isinstance(node, list):
                pending.extend((child, priced) for child in node)
                continue
            if not isinstance(node, dict):
                continue
            title, link = str(node.get("title") or ""), node.get("link")
            inside = priced or node.get("docType") == self.PRICE_DOC_TYPE
            listed = isinstance(link, str) and link in links
            wanted = self.PRICE_TITLE.search(title) and not self.NOT_PRICE_TITLE.search(title)
            if inside and node.get("type") == "page" and isinstance(link, str) and wanted and not listed:
                links.append(link)
            pending.append((node.get("children"), inside))
        self.logger.debug("%d %s price pages in the documentation of %s.", len(links), self.name, name)
        for link in links:
            yield self._price_request(f"{self.DOC_HOST}{link}", {self.PRODUCT_PAGE_META: name})

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the regions documentation, a purchase API call, or a product documentation.

        Args:
            response (Response): The regions documentation, the answer of a call, or a product documentation.

        Yields:
            PriceFact: The calls of each region and charge type and the product documentations, the prices of a
                call, or the price pages of a product documentation.

        Raises:
            CatalogueFormatError: If the documentation lists no region, or a call has no price.
        """
        if self.SIDEBAR_META in response.meta:
            for request in self._price_doc_pages(response):
                yield request
            return
        region = response.meta.get(self.REGION_META)
        charge = str(response.meta.get(self.CHARGE_META) or "")
        try:
            if not isinstance(region, str):
                regions = self._regions(response)
                self.logger.info("Requesting the %s CVM prices of %d regions.", self.name, len(regions))
                for code in regions:
                    for kind in TencentChargeType:
                        yield self._cvm_request(code, kind)
                for request in self._doc_requests(response):
                    yield request
            else:
                found = 0
                for quota in self._quotas(response, region):
                    for fact in self._quota_prices(quota, region, charge):
                        found += 1
                        yield fact
                self.price_rows += found
                self.logger.debug("%s CVM %s prices of %s: %d prices.", self.name, charge, region, found)
        except CatalogueFormatError:
            self.price_failures.add(response.url)
            raise
        finally:
            self._price_settled()

    async def _catalogue_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the products page, waiting for its cards once the challenge is passed.

        Yields:
            Request: The products page request, then the documentation home page one (lower priority).
        """
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield Request(self.catalogue_url, priority=self.PRIMARY_PRIORITY, wait_selector=self.CARD_SELECTOR)
        for url in self.complement_urls:
            self.logger.debug("Requesting the %s complementary catalogue page %s.", self.name, url)
            yield self._complement_request(url)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the products page cards.

        Args:
            response (Response): The products page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        self.logger.debug("Reading the %s product cards of %s.", self.name, response.url)
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
            self.logger.debug("Reading the %s documentation catalogue %s.", self.name, response.url)
            if (request := self._doc_article_request(response)) is not None:
                yield request
            return
        if self.DOC_ARTICLE in response.meta:
            self.logger.debug("Reading the %s documentation article %s.", self.name, response.url)
            if (product := self._doc_article_product(response)) and (streamed := self._stream(product)) is not None:
                yield streamed
            return
        if self.DOC_ID in response.meta and response.status >= 400:
            self.logger.warning(
                "The %s documentation page %s failed (HTTP %s): its catalogue is read instead.",
                self.name,
                response.url,
                response.status,
            )
            yield self._doc_catalogue_request(response)
            return
        if self.PRODUCT_PAGE not in response.meta and urlparse(response.url).path.startswith("/document/"):
            self.logger.debug("Reading the %s documentation directory %s.", self.name, response.url)
            for request in self._docs_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
