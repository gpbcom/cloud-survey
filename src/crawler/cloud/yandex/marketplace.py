from __future__ import annotations

# Standard Library Imports.
import html
import json
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.yandex.enums import (
    YandexHttpHeader,
    YandexMarketplaceCategory,
    YandexMarketplaceRequestMeta,
    YandexPageStateField,
    YandexProductField,
    YandexProductType,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler

# First Party Imports.
from crawler.tls.ca_bundle import CaBundle
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class YandexMarketplaceCrawler(BaseMarketplaceCrawler):
    """Yandex Cloud Marketplace crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root.
        MARKETPLACE_URL (ClassVar[str]): The marketplace home page of the international (English) website.
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing every marketplace product page.
        PRODUCT_PATH (ClassVar[str]): The path of the English marketplace product pages.
        USER_AGENT (ClassVar[str]): The user agent of the HTTP session, naming the crawler.
        CAPTCHA_PATH (ClassVar[str]): The path prefix of the captcha page the website redirects the bots it
            rejects to.
        DETAILS_PER_PAGE (ClassVar[int]): The product pages counted as one page of the marketplace for the page
            limit, the products the marketplace shows per page.
        PRODUCT (ClassVar[YandexMarketplaceRequestMeta]): The meta key marking a product page request, holding the
            requested URL.
        SITEMAP (ClassVar[YandexMarketplaceRequestMeta]): The meta key marking the sitemap request.
        STATE_ASSIGNMENT (ClassVar[re.Pattern[str]]): The assignment of the page state (`__DATA__ = {...}`) in the
            page scripts.
        STATE_DECODER (ClassVar[json.JSONDecoder]): The decoder of the page state, which a script statement follows.
        PARAGRAPH (ClassVar[re.Pattern[str]]): The first paragraph of an HTML description.
        INLINE_TAG (ClassVar[re.Pattern[str]]): The inline HTML tags of the texts, removed (e.g. `<em>`).
        TAG (ClassVar[re.Pattern[str]]): The other HTML tags of the texts, replaced by a space.
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[YandexMarketplaceCategory]]): The slugs of the marketplace
            selections which are not categories (recommended products, new arrivals).
        DATA_TYPES (ClassVar[FrozenSet[YandexProductType]]): The product types which are data, not software
            (DataLens datasets and geolayers).
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each product type, keyed by
            `YandexProductType` members.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The marketplace home page.
        complement_urls (ClassVar[Tuple[str, ...]]): The website sitemap.
        download_delay (float): The delay between two requests, in seconds: a product page is read per product.

    Notes:
        The website redirects the requests of web browsers (and of any client announcing a browser user agent) to a
        captcha (`/showcaptchafast`): the pages are read through the HTTP session announcing the crawler in its user
        agent, which the website serves. A page redirected to the captcha anyway is an error.
        The marketplace pages are rendered on the server and embed their state in a script (`__DATA__ = {...}`).
        The JSON API they call to list the products (`POST /api/marketplace/products?localeCode=en`) is
        disallowed by the `robots.txt` rules (no URL with a query), which the crawler obeys: the home page
        (https://yandex.cloud/en/marketplace) shows a few products of each selection
        (`props.pageProps.data.categories[].products`), then every English product page listed by the sitemap
        and not streamed yet is read (`props.pageProps.data`, the same product object), at most `page_limit`
        times `DETAILS_PER_PAGE` of them when the pages are limited.
        A product gives its English name and short description (else the first paragraph of its HTML description),
        its publisher, its type (the delivery method, e.g. `COMPUTE_IMAGE` for a virtual machine image), its
        categories (slug and title) and its creation and update dates (Unix seconds). The update date is that of
        the marketplace entry. Its page is `/en/marketplace/products/<publisher>/<slug>`, after its name. The
        DataLens datasets and geolayers (data) are skipped. The marketplace taxonomy is flat: each category path is
        the category title, identified by its slug (e.g. `os`). The recommended products and new arrivals are
        selections, not categories.
    """

    SITE_URL: ClassVar[str] = "https://yandex.cloud"
    MARKETPLACE_URL: ClassVar[str] = f"{SITE_URL}/en/marketplace"
    SITEMAP_URL: ClassVar[str] = f"{SITE_URL}/sitemap_main.xml"
    PRODUCT_PATH: ClassVar[str] = "/en/marketplace/products/"
    USER_AGENT: ClassVar[str] = "Mozilla/5.0 (compatible; poc-crawler/0.1.0)"
    CAPTCHA_PATH: ClassVar[str] = "/showcaptcha"
    DETAILS_PER_PAGE: ClassVar[int] = 15
    PRODUCT: ClassVar[YandexMarketplaceRequestMeta] = YandexMarketplaceRequestMeta.PRODUCT
    SITEMAP: ClassVar[YandexMarketplaceRequestMeta] = YandexMarketplaceRequestMeta.SITEMAP
    STATE_ASSIGNMENT: ClassVar[re.Pattern[str]] = re.compile(r"(?<![\w$])(?:window\.)?__DATA__\s*=\s*(?=\{)")
    STATE_DECODER: ClassVar[json.JSONDecoder] = json.JSONDecoder()
    PARAGRAPH: ClassVar[re.Pattern[str]] = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
    INLINE_TAG: ClassVar[re.Pattern[str]] = re.compile(r"</?(?:sup|sub|em|strong|b|i|span|a|code|nobr)\b[^>]*>", re.I)
    TAG: ClassVar[re.Pattern[str]] = re.compile(r"<[^>]*>")
    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[YandexMarketplaceCategory]] = frozenset(
        {YandexMarketplaceCategory.RECOMMENDED, YandexMarketplaceCategory.LATEST_PRODUCTS}
    )
    DATA_TYPES: ClassVar[FrozenSet[YandexProductType]] = frozenset(
        {YandexProductType.DATALENS_DATASET, YandexProductType.DATALENS_GEOLAYER}
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        YandexProductType.COMPUTE_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        YandexProductType.BAREMETAL: DeliveryMethod.VIRTUAL_MACHINE,
        YandexProductType.BAREMETAL_EXTEND: DeliveryMethod.VIRTUAL_MACHINE,
        YandexProductType.COS: DeliveryMethod.CONTAINER,
        YandexProductType.K8S: DeliveryMethod.KUBERNETES,
        YandexProductType.SAAS: DeliveryMethod.SAAS,
        YandexProductType.CLOUD_APP: DeliveryMethod.ONE_CLICK_APP,
    }

    name = "yandex-marketplace"
    catalogue_url: ClassVar[str] = MARKETPLACE_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    download_delay: float = 1.5

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)

    ############################
    # Internal Helpers Methods #
    ############################

    def _complement_request(self, url: str) -> Request:
        """Build the sitemap request, read after the home page (`SITEMAP` meta).

        Args:
            url (str): The sitemap.

        Returns:
            Request: The request of the HTTP session.
        """
        return Request(url, sid=self._http_session_id(), meta={self.SITEMAP: True})

    def _reject_captcha(self, response: Response) -> None:
        """Make sure a page is not the captcha the website redirects the rejected clients to.

        Args:
            response (Response): The fetched page.

        Raises:
            CatalogueFormatError: If the page is the captcha.
        """
        if urlparse(response.url).path.startswith(self.CAPTCHA_PATH):
            self.logger.error("The %s page was redirected to the captcha %s.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page is a captcha")

    def _plain_text(self, value: JsonValue) -> Optional[str]:
        """Read a text of the page state, without its HTML tags and entities.

        Args:
            value (JsonValue): The JSON value, e.g. `<p>LLM-Box Base is a private AI server.</p>` (with HTML
                entities).

        Returns:
            Optional[str]: The plain text with single spaces, `None` when the value is not a string or is blank.
        """
        text = self._as_text(value)
        if text is None:
            return None
        plain = html.unescape(self.TAG.sub(" ", self.INLINE_TAG.sub("", text)))
        return self._clean_text(plain) or None

    def _page_state(self, response: Response) -> Dict[str, JsonValue]:
        """Read the state a page embeds in a script (`__DATA__ = {...}`).

        Args:
            response (Response): The page.

        Returns:
            Dict[str, JsonValue]: The page state, holding `props` and `context`.

        Raises:
            CatalogueFormatError: If no script assigns a page state.
        """
        for script in response.css("script::text").getall():
            for match in self.STATE_ASSIGNMENT.finditer(script):
                try:
                    state: JsonValue = self.STATE_DECODER.raw_decode(script, match.end())[0]
                except json.JSONDecodeError as e:
                    self.logger.debug("Ignoring an unreadable state assignment of %s: %s", response.url, e)
                    continue
                if isinstance(state, dict) and YandexPageStateField.PROPS in state:
                    self.logger.debug("Page state of %s read (%d keys).", response.url, len(state))
                    return state
        self.logger.error("The %s page %s embeds no page state.", self.name, response.url)
        raise CatalogueFormatError(self.name, response.url, "the `__DATA__` page state is missing")

    def _page_data(self, response: Response) -> Dict[str, JsonValue]:
        """Read the data of a marketplace page: its selections, or its product.

        Args:
            response (Response): The home page or a product page.

        Returns:
            Dict[str, JsonValue]: The page data (`props.pageProps.data`), empty when the page has none.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        props = self._as_object(self._page_state(response).get(YandexPageStateField.PROPS))
        return self._as_object(
            self._as_object(props.get(YandexPageStateField.PAGE_PROPS)).get(YandexPageStateField.DATA)
        )

    def _description(self, info: Dict[str, JsonValue]) -> Optional[str]:
        """Read the description of a product: its short description, else its first described paragraph.

        Args:
            info (Dict[str, JsonValue]): The marketing information of the product (`marketingInfo`).

        Returns:
            Optional[str]: The description, `None` when the product has none.
        """
        short = self._plain_text(info.get(YandexProductField.SHORT_DESCRIPTION))
        if short:
            return short
        long = self._as_text(info.get(YandexProductField.DESCRIPTION)) or ""
        paragraphs = (self._plain_text(paragraph) for paragraph in self.PARAGRAPH.findall(long))
        return next((paragraph for paragraph in paragraphs if paragraph), None) or self._plain_text(long)

    def _categories(self, product: Dict[str, JsonValue]) -> List[Tuple[str, MarketplaceCategory]]:
        """Read the categories of a product, without the marketplace selections.

        Args:
            product (Dict[str, JsonValue]): The product.

        Returns:
            List[Tuple[str, MarketplaceCategory]]: The title of each category and its taxonomy path, identified by
                the category slug.
        """
        categories = product.get(YandexProductField.CATEGORIES)
        found: List[Tuple[str, MarketplaceCategory]] = []
        for category in map(self._as_object, categories if isinstance(categories, list) else []):
            slug = self._as_text(category.get(YandexProductField.NAME))
            title = self._plain_text(category.get(YandexProductField.TITLE))
            if not title or slug in self.EXCLUDED_CATEGORIES:
                continue
            if (path := self._category([title], slug)) is not None:
                found.append((title, path))
        return found

    def _product_software(self, value: JsonValue) -> Optional[MarketplaceSoftware]:
        """Build the software of a product, unless it is data.

        Args:
            value (JsonValue): The product.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` for data (logged) or an invalid product (logged).
        """
        product = self._as_object(value)
        info = self._as_object(product.get(YandexProductField.MARKETING_INFO))
        name = self._plain_text(info.get(YandexProductField.NAME))
        kind = self._as_text(product.get(YandexProductField.TYPE)) or ""
        if kind in self.DATA_TYPES:
            self.logger.debug("Skipping the %s product %r, not a software (type %s).", self.name, name, kind)
            return None
        publisher = self._as_object(product.get(YandexProductField.PUBLISHER))
        identifier = self._as_text(product.get(YandexProductField.NAME)) or self._as_text(
            product.get(YandexProductField.ID)
        )
        categories = self._categories(product)
        return self._build_software(
            name,
            self._description(info),
            f"{self.SITE_URL}{self.PRODUCT_PATH}{identifier}" if identifier else None,
            self._plain_text(
                self._as_object(publisher.get(YandexProductField.MARKETING_INFO)).get(YandexProductField.NAME)
            )
            or self._as_text(publisher.get(YandexProductField.NAME)),
            self.DELIVERIES.get(kind, DeliveryMethod.OTHER),
            [title for title, _ in categories],
            [path for _, path in categories],
            added_at=self._parse_date(product.get(YandexProductField.CREATED_AT), name),
            updated_at=self._parse_date(product.get(YandexProductField.UPDATED_AT), name),
            updated_caveat=DateCaveat.CATALOGUE_ENTRY,
        )

    def _home_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the products shown by the selections of the home page.

        Args:
            response (Response): The home page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software, duplicates included.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        selections = self._page_data(response).get(YandexProductField.CATEGORIES)
        for selection in map(self._as_object, selections if isinstance(selections, list) else []):
            products = selection.get(YandexProductField.PRODUCTS)
            products = products if isinstance(products, list) else []
            self.logger.debug(
                "%s selection %r: %d products.", self.name, selection.get(YandexProductField.TITLE), len(products)
            )
            for product in products:
                if (software := self._product_software(product)) is not None:
                    yield software

    def _page_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a product page.

        Args:
            response (Response): The product page, requested with the `PRODUCT` meta.

        Yields:
            Iterator[MarketplaceSoftware]: The software, unless the page is missing or holds no valid software.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        if response.status >= 400:
            self.logger.debug("Skipping the %s product page %s (HTTP %s).", self.name, response.url, response.status)
            return
        data = self._page_data(response)
        if not data:
            self.logger.warning("The %s product page %s holds no product.", self.name, response.url)
            return
        if (software := self._product_software(data)) is not None:
            yield software

    def _product_requests(self, response: Response) -> List[Request]:
        """Build the requests of the product pages of the sitemap not streamed yet, within the page limit.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests, which may hold no software.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        pages = [url for url in self._sitemap_urls(response) if urlparse(url).path.startswith(self.PRODUCT_PATH)]
        missing = [url for url in pages if url.casefold().rstrip("/") not in self.software_categories]
        limit = None if self.page_limit is None else self.page_limit * self.DETAILS_PER_PAGE
        if limit is not None and len(missing) > limit:
            self.logger.info("Page limit (%d) reached: %d product pages not requested.", limit, len(missing) - limit)
            missing = missing[:limit]
        self.logger.info("%d %s product pages requested (%d in the sitemap).", len(missing), self.name, len(pages))
        return [
            Request(url, sid=self._http_session_id(), meta={self.PRODUCT: url, self.MAY_BE_EMPTY: True})
            for url in missing
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the stealth browser session (never started) and the HTTP session announcing the crawler.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.

        Notes:
            The HTTP session of the base marketplace crawler announces a browser, which the website rejects to a
            captcha: it is replaced by one with the TLS fingerprint of Chrome which announces the crawler
            (`USER_AGENT`), without the browser headers, still the default session.
        """
        super().configure_sessions(manager)
        manager.pop(self._http_session_id())
        self.logger.debug("Configuring the HTTP session %s (%s).", self._http_session_id(), self.USER_AGENT)
        CaBundle(logger=self.logger).install()
        manager.add(
            self._http_session_id(),
            FetcherSession(
                impersonate="chrome",
                stealthy_headers=False,
                headers={YandexHttpHeader.USER_AGENT: self.USER_AGENT},
                timeout=60,
                retries=self.fetch_retries,
                retry_delay=round(self.retry_delay),
            ),
            default=True,
        )

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the home page selections, or of a product page.

        Args:
            response (Response): The home page, or a product page (`PRODUCT` meta).

        Returns:
            Iterator[MarketplaceSoftware]: The valid software of the page.
        """
        if self.PRODUCT in response.meta:
            self.logger.debug("Reading the %s product page %s.", self.name, response.url)
            return self._page_software(response)
        self.logger.debug("Reading the %s home page %s.", self.name, response.url)
        return self._home_software(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a page, or request the product pages of the sitemap.

        Args:
            response (Response): The home page, a product page (`PRODUCT` meta) or the sitemap (`SITEMAP` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If the page is the captcha, a page embeds no page state or the sitemap lists no
                page.
            EmptyCatalogueError: If the home page holds no software.
        """
        self._reject_captcha(response)
        if response.meta.get(self.SITEMAP):
            self.logger.debug("Reading the %s sitemap %s.", self.name, response.url)
            for request in self._product_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
