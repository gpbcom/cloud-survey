from __future__ import annotations

# Standard Library Imports.
import html
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.fetchers import AsyncStealthySession
from scrapling.spiders import Request, Response, Spider
from scrapling.spiders.session import SessionManager

# First Party Imports.
from crawler.enums import HtmlAttribute, PageMetaName, RequestMeta, TextEncoding
from crawler.exception import CatalogueFormatError, CrawlerError, EmptyCatalogueError, ParseNotImplementedError
from models.cloud.dated_item import DatedItem
from models.cloud.enums import DateCaveat, UrlScheme
from models.cloud.products.product import CloudProduct


class BaseCloudCrawler(Spider):
    """Base class for cloud provider catalogue crawlers.

    Attributes:
        PRIMARY_PRIORITY (ClassVar[int]): The priority of the main catalogue requests, crawled before the complements.
        DATES_PRIORITY (ClassVar[int]): The priority of the sitemaps read for their dates, crawled first.
        PAGE_DATES (ClassVar[str]): The meta key marking a sitemap request read for the last modification of its
            pages.
        PRODUCT_PAGE (ClassVar[str]): The meta key marking a product page request, holding the requested URL.
        PRODUCT_NAME (ClassVar[str]): The meta key holding the product name given by a listing, if any.
        PRODUCT_UPDATED (ClassVar[str]): The meta key holding the last modification of a product page given by a
            sitemap, if any.
        PRODUCT_CATEGORIES (ClassVar[str]): The meta key holding the catalogue categories of a product page given by
            a listing, if any.
        ADDED_META (ClassVar[Tuple[PageMetaName, ...]]): The `meta` tags giving the publication date of a page.
        UPDATED_META (ClassVar[Tuple[PageMetaName, ...]]): The `meta` tags giving the last modification of a page.
        EARLIEST_DATE (ClassVar[datetime]): The earliest plausible date of a product: an earlier one is an error of
            the website.
        SAME_DAY_LIMIT (ClassVar[int]): From how many pages a sitemap dating them all the same day is ignored: its
            dates are then the generation date of the sitemap.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The URL the catalogue crawl starts from: the main product listing.
        complement_urls (ClassVar[Tuple[str, ...]]): Secondary sources, crawled after the main listing, which only
            add the products not found yet.
        dates_sitemaps (ClassVar[Tuple[str, ...]]): The sitemaps giving the last modification of the product pages,
            read before anything else so that every product with a listed page is dated.
        name_prefixes (ClassVar[Tuple[str, ...]]): Brand prefixes ignored when comparing product names, e.g. `AWS `.
        robots_txt_obey (bool): Whether the `robots.txt` rules of the provider are respected.
        solve_cloudflare (ClassVar[bool]): Whether the browser solves the Cloudflare challenges. Off by default: no
            provider shows one, and the check waits for each page to be idle and logs an error when there is none.
        lazy_browser (ClassVar[bool]): Whether the stealth browser is only started when a request uses it.
        fetch_retries (ClassVar[int]): How many times a failed page fetch is attempted.
        retry_delay (ClassVar[float]): The delay between two attempts of a failed fetch, in seconds.
        DESCRIPTION_LIMIT (ClassVar[int]): The longest description kept, longer ones are shortened.
        concurrent_requests (int): The maximum number of requests in flight.
        download_delay (float): The delay between two requests, in seconds.
        seen_products (Set[str]): The normalized names (and aliases) of the products already streamed by the crawl.
        seen_urls (Set[str]): The normalized URLs of the products already streamed by the crawl.
        page_dates (Dict[str, str]): The last modification (raw) of each page listed by the `dates_sitemaps`, by
            normalized URL.

    Notes:
        A product is streamed once: it is skipped when its normalized name or URL was already seen.
        The `allowed_domains` attribute, inherited from `Spider`, is set to the domains of the catalogue URLs.
        The scrapling spider logger (`scrapling.spiders.<name>`), also used by the crawl engine, is routed to the
        application logging configuration.
        When a listing only gives the product names or links, each product page is requested (`PRODUCT_PAGE` meta)
        and its product is read from its title and meta description, filed under the categories the listing gave
        (`PRODUCT_CATEGORIES` meta).
        A listing filing a product under several categories lists it once per category: `_merge_categories` gathers
        these occurrences into one product holding all their categories.
    """

    PRIMARY_PRIORITY: ClassVar[int] = 10
    DATES_PRIORITY: ClassVar[int] = 20
    PAGE_DATES: ClassVar[str] = RequestMeta.PAGE_DATES
    SAME_DAY_LIMIT: ClassVar[int] = 10
    EARLIEST_DATE: ClassVar[datetime] = datetime(1990, 1, 1, tzinfo=UTC)
    PRODUCT_PAGE: ClassVar[str] = RequestMeta.PRODUCT_PAGE
    PRODUCT_NAME: ClassVar[str] = RequestMeta.PRODUCT_NAME
    PRODUCT_UPDATED: ClassVar[str] = RequestMeta.PRODUCT_UPDATED
    PRODUCT_CATEGORIES: ClassVar[str] = RequestMeta.PRODUCT_CATEGORIES
    ADDED_META: ClassVar[Tuple[PageMetaName, ...]] = (PageMetaName.ARTICLE_PUBLISHED_TIME, PageMetaName.DATE_PUBLISHED)
    UPDATED_META: ClassVar[Tuple[PageMetaName, ...]] = (
        PageMetaName.ARTICLE_MODIFIED_TIME,
        PageMetaName.OG_UPDATED_TIME,
        PageMetaName.DATE_MODIFIED,
        PageMetaName.CPP_LAST_MODIFIED_TIME,
    )

    name: str = "default-crawler"
    catalogue_url: ClassVar[str] = ""
    complement_urls: ClassVar[Tuple[str, ...]] = ()
    dates_sitemaps: ClassVar[Tuple[str, ...]] = ()
    name_prefixes: ClassVar[Tuple[str, ...]] = ()
    robots_txt_obey: bool = True
    solve_cloudflare: ClassVar[bool] = False
    lazy_browser: ClassVar[bool] = False
    fetch_retries: ClassVar[int] = 3
    retry_delay: ClassVar[float] = 1.0
    DESCRIPTION_LIMIT: ClassVar[int] = 1000
    concurrent_requests: int = 1
    download_delay: float = 1.0

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        urls = [url for url in (self.catalogue_url, *self.complement_urls) if url]
        self.allowed_domains = {urlparse(url).netloc for url in urls}
        self.seen_products: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.page_dates: Dict[str, str] = {}
        self.logger.debug(
            "%s crawler ready: catalogue %s, allowed domains %s.", self.name, self.catalogue_url, self.allowed_domains
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _use_application_logging(self) -> None:
        """Hand the spider logger over to the application logging configuration.

        Notes:
            Scrapling isolates the spider logger with its own console handler:
            it is removed (the log counter used by the
            crawl stats, and the log file if any, are kept)
            and the records are propagated to the application handlers.
        """
        for handler in list(self.logger.handlers):
            if type(handler) is logging.StreamHandler:
                self.logger.removeHandler(handler)
        self.logger.propagate = True

    def _clean_text(self, text: Optional[str]) -> str:
        """Collapse the whitespaces (including non-breaking spaces) of a scraped text.

        Args:
            text (Optional[str]): The scraped text.

        Returns:
            str: The text with single spaces, empty when missing.
        """
        return " ".join((text or "").split())

    def _as_object(self, value: JsonValue) -> Dict[str, JsonValue]:
        """Read a JSON value expected to be an object.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            Dict[str, JsonValue]: The object, empty when the value is not an object.
        """
        return value if isinstance(value, dict) else {}

    def _as_text(self, value: JsonValue) -> Optional[str]:
        """Read a JSON value expected to be a string.

        Args:
            value (JsonValue): The JSON value.

        Returns:
            Optional[str]: The string, `None` when the value is not a string.
        """
        return value if isinstance(value, str) else None

    def _walk_objects(self, value: JsonValue) -> Iterator[Dict[str, JsonValue]]:
        """Walk every JSON object of a JSON document, depth first.

        Args:
            value (JsonValue): The JSON document.

        Yields:
            Dict[str, JsonValue]: Each object, parents before their children.
        """
        children: List[JsonValue] = []
        if isinstance(value, dict):
            yield value
            children = list(value.values())
        elif isinstance(value, list):
            children = value
        for child in children:
            yield from self._walk_objects(child)

    def _name_key(self, name: str) -> str:
        """Normalize a product name to compare it: brand prefix, parenthesized notes and punctuation are ignored.

        Args:
            name (str): The product name.

        Returns:
            str: The comparison key, e.g. `apprunner` for `AWS App Runner`, `云服务器bcc` for `云服务器 BCC`.
        """
        text = re.sub(r"[(\uff08][^)\uff09]*[)\uff09]", " ", self._clean_text(name).casefold())
        for prefix in sorted(self.name_prefixes, key=len, reverse=True):
            if text.startswith(prefix.casefold()):
                text = text[len(prefix) :]
                break
        return re.sub(r"[\W_]+", "", text) or self._clean_text(name).casefold()

    def _url_key(self, url: str) -> str:
        """Normalize a product URL to compare it: scheme, `www.`, query, fragment and trailing slash are ignored.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The comparison key, e.g. `azure.microsoft.com/en-us/products/functions`.
        """
        link = urlparse(url.casefold())
        return f"{link.netloc.removeprefix('www.')}{link.path.rstrip('/')}"

    def _remember(self, names: Iterable[str]) -> None:
        """Mark product names (e.g. the former names of a product) as already streamed.

        Args:
            names (Iterable[str]): The product names.
        """
        self.seen_products.update(self._name_key(name) for name in names if self._clean_text(name))

    def _is_new(self, product: CloudProduct) -> bool:
        """Tell whether a product was not streamed yet, and mark it as streamed.

        Args:
            product (CloudProduct): The product.

        Returns:
            bool: Whether neither its normalized name nor its normalized URL was seen before.
        """
        name_key = self._name_key(product.name)
        url_key = self._url_key(product.url) if product.url else None
        if name_key in self.seen_products or (url_key is not None and url_key in self.seen_urls):
            return False
        self.seen_products.add(name_key)
        if url_key is not None:
            self.seen_urls.add(url_key)
        return True

    def _browser_session_id(self) -> str:
        """Get the identifier of the stealth browser session.

        Returns:
            str: The session identifier, e.g. `aws-session`.
        """
        return f"{self.name}-session"

    def _catalogue_request(self) -> Request:
        """Build the request of the main catalogue page, crawled first (primary priority).

        Returns:
            Request: The request, with the default session options.
        """
        return Request(self.catalogue_url, priority=self.PRIMARY_PRIORITY)

    def _complement_request(self, url: str) -> Request:
        """Build the request of a complementary catalogue page, after the main listing (lower priority).

        Args:
            url (str): The complementary catalogue page.

        Returns:
            Request: The request, with the default session options.
        """
        return Request(url)

    def _stream(self, product: CloudProduct) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a product not streamed yet, and log it.

        Args:
            product (CloudProduct): The extracted product.

        Returns:
            Optional[Dict[str, JsonValue]]: The product as a dictionary, `None` when it was already streamed.
        """
        if not self._is_new(product):
            self.logger.debug("Skipping the duplicated product %r.", product.name)
            return None
        self.logger.info("Product extracted from %s: %s - %s", self.name, product.name, product.description)
        return product.item_dump()

    def _shorten(self, text: str) -> str:
        """Shorten a text over the description limit: at its last sentence end, else at a word, with an ellipsis.

        Args:
            text (str): The text, whitespaces collapsed.

        Returns:
            str: The text, unchanged when it is within the limit.
        """
        if len(text) <= self.DESCRIPTION_LIMIT:
            return text
        head = text[: self.DESCRIPTION_LIMIT]
        ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)|[\u3002\uff01\uff1f]", head)]
        if ends and ends[-1] >= self.DESCRIPTION_LIMIT // 2:
            shortened = head[: ends[-1]]
        else:
            shortened = head[: self.DESCRIPTION_LIMIT - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "\u2026"
        self.logger.debug("Description shortened from %d to %d characters.", len(text), len(shortened))
        return shortened

    def _valid_url(self, url: Optional[str], name: Optional[str]) -> Optional[str]:
        """Get a scraped page URL, if it is an absolute http(s) link.

        Args:
            url (Optional[str]): The scraped URL.
            name (Optional[str]): The name of the catalogue entry, for the logs.

        Returns:
            Optional[str]: The trimmed URL, `None` (logged) when it is missing or invalid.
        """
        if not url or not url.strip():
            return None
        link = urlparse(url.strip())
        if link.scheme not in tuple(UrlScheme) or not link.netloc:
            self.logger.debug("Ignoring the invalid URL %r of the catalogue entry %r.", url, name)
            return None
        return url.strip()

    def _parse_date(self, value: JsonValue, name: Optional[str] = None) -> Optional[datetime]:
        """Parse a date published by a website, leniently: an unreadable date is dropped, not its item.

        Args:
            value (JsonValue): The raw date: an ISO 8601 text, or a Unix timestamp in seconds or milliseconds.
            name (Optional[str]): The item the date belongs to, for the logs.

        Returns:
            Optional[datetime]: The timezone-aware date, `None` when missing, unreadable or implausible (before 1990
                or in the future, logged).
        """
        try:
            date = DatedItem.model_validate({"added_at": value}).added_at
        except ValidationError:
            self.logger.debug("Ignoring the unreadable date %r of the entry %r.", value, name)
            return None
        if date is not None and not self.EARLIEST_DATE <= date <= datetime.now(UTC) + timedelta(days=1):
            self.logger.debug("Ignoring the implausible date %s of the entry %r.", date.isoformat(), name)
            return None
        return date

    def _build_product(
        self,
        name: Optional[str],
        description: Optional[str],
        url: Optional[str] = None,
        added_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        added_caveat: Optional[DateCaveat] = None,
        updated_caveat: Optional[DateCaveat] = None,
        categories: Optional[Sequence[Optional[str]]] = None,
    ) -> Optional[CloudProduct]:
        """Build a product from scraped texts, with collapsed whitespaces and a description within the limit.

        Args:
            name (Optional[str]): The scraped product name.
            description (Optional[str]): The scraped product description.
            url (Optional[str]): The product page, dropped (not the product) when it is not an absolute http(s) link.
            added_at (Optional[datetime]): When the website says the product was added, if it does.
            updated_at (Optional[datetime]): When the website says the product was last updated, if it does. Else,
                the last modification of its page given by a `dates_sitemaps` sitemap, if any.
            added_caveat (Optional[DateCaveat]): Why `added_at` may not be the launch, if it may not.
            updated_caveat (Optional[DateCaveat]): Why `updated_at` may not be a change of the product, if it may not.
            categories (Optional[Sequence[Optional[str]]]): The categories the catalogue files the product under, as
                labelled there (blank ones dropped), `None` when it gives none.

        Returns:
            Optional[CloudProduct]: The product, or `None` (logged) when the scraped texts are invalid.
        """
        url = self._valid_url(url, name)
        if updated_at is None and url and self._url_key(url) in self.page_dates:
            updated_at = self._parse_date(self.page_dates[self._url_key(url)], name)
            updated_caveat = DateCaveat.PAGE_MODIFIED
        try:
            return CloudProduct.model_validate(
                {
                    "name": self._clean_text(name),
                    "description": self._shorten(self._clean_text(description)),
                    "url": url,
                    "catalogue_categories": [self._clean_text(category) for category in categories or []],
                    "added_at": added_at,
                    "added_caveat": added_caveat if added_at else None,
                    "updated_at": updated_at,
                    "updated_caveat": updated_caveat if updated_at else None,
                }
            )
        except ValidationError as e:
            reasons = "; ".join(
                f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in e.errors()
            )
            self.logger.warning("Skipping the invalid catalogue entry %r (%s).", name, reasons)
            return None

    def _merge_categories(self, products: Iterable[CloudProduct]) -> List[CloudProduct]:
        """Merge the occurrences of the same product (same normalized name or URL) of a listing.

        Args:
            products (Iterable[CloudProduct]): The products of the listing, an occurrence per category.

        Returns:
            List[CloudProduct]: Each product once, as first listed, with the categories of all its occurrences in
                their first-occurrence order.

        Notes:
            An occurrence matches a product kept before when its normalized name or URL is one of those of the
            first occurrence, as `_is_new` compares the streamed products.
            The merged product is validated again, so that its categories are cleaned like those of a built product.
            Should it be invalid, the first occurrence is kept unchanged (logged).
        """
        merged: List[CloudProduct] = []
        positions: Dict[str, int] = {}
        count = 0
        for product in products:
            count += 1
            keys = [self._name_key(product.name)] + ([self._url_key(product.url)] if product.url else [])
            position = next((positions[key] for key in keys if key in positions), None)
            if position is None:
                positions.update(dict.fromkeys(keys, len(merged)))
                merged.append(product)
                continue
            first = merged[position]
            categories = [*first.catalogue_categories, *product.catalogue_categories]
            try:
                merged[position] = type(first).model_validate(
                    {**first.model_dump(), "catalogue_categories": categories}
                )
            except ValidationError as e:
                self.logger.warning("Keeping the categories of the first %r listing (%s).", first.name, e)
        self.logger.debug("%d distinct products out of %d listed entries.", len(merged), count)
        return merged

    def _next_data(self, response: Response) -> Dict[str, JsonValue]:
        """Read the Next.js data embedded in a page (`__NEXT_DATA__` script).

        Args:
            response (Response): The page.

        Returns:
            Dict[str, JsonValue]: The page data.

        Raises:
            CatalogueFormatError: If the script is missing or does not hold a JSON object.
        """
        self.logger.debug("Reading the Next.js data of %s.", response.url)
        raw = response.css("script#__NEXT_DATA__::text").get()
        if raw is None:
            self.logger.error("The %s page %s has no `__NEXT_DATA__` script.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is missing")
        try:
            data: JsonValue = json.loads(raw)
        except json.JSONDecodeError as e:
            self.logger.error("The %s page %s `__NEXT_DATA__` is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The `__NEXT_DATA__` script of the %s page %s is not an object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the `__NEXT_DATA__` script is not a JSON object")
        self.logger.debug("Next.js data of %s read (%d characters).", response.url, len(raw))
        return data

    def _json_body(self, response: Response) -> JsonValue:
        """Read a JSON response (the raw body, not a rendered page).

        Args:
            response (Response): The JSON response.

        Returns:
            JsonValue: The JSON document.

        Raises:
            CatalogueFormatError: If the response is not JSON.
        """
        try:
            data: JsonValue = json.loads(response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE))
        except json.JSONDecodeError as e:
            self.logger.error("The %s page %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the page is not JSON") from e
        return data

    def _sitemap_entries(self, response: Response) -> Dict[str, Optional[str]]:
        """Read the pages listed by a sitemap with their last modification, in order and without duplicates.

        Args:
            response (Response): The sitemap.

        Returns:
            Dict[str, Optional[str]]: The last modification (`lastmod`, raw) of each page URL, `None` when not given.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        body = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        blocks = re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", body, re.DOTALL) or [body]
        entries: Dict[str, Optional[str]] = {}
        for block in blocks:
            lastmod = re.search(r"<lastmod>\s*([^<\s]+)", block)
            for url in re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)", block):
                entries.setdefault(html.unescape(url), lastmod.group(1) if lastmod else None)
        if not entries:
            self.logger.error("The %s sitemap %s lists no page.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the sitemap lists no page")
        self.logger.debug("%d pages listed by the %s sitemap %s.", len(entries), self.name, response.url)
        return entries

    def _sitemap_urls(self, response: Response) -> List[str]:
        """Read the pages listed by a sitemap, in order and without duplicates.

        Args:
            response (Response): The sitemap.

        Returns:
            List[str]: The page URLs.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        return list(self._sitemap_entries(response))

    def _meta_content(self, response: Response, *names: str) -> Optional[str]:
        """Read the first non-empty `meta` tag content of a page among some names, case-insensitively.

        Args:
            response (Response): The page.
            *names (str): The `name` or `property` values, by order of preference, e.g. `description`.

        Returns:
            Optional[str]: The content, `None` when no tag holds one.
        """
        contents: Dict[str, str] = {}
        for tag in response.css("meta[content]"):
            key = (tag.attrib.get(HtmlAttribute.NAME) or tag.attrib.get(HtmlAttribute.PROPERTY) or "").casefold()
            content = self._clean_text(tag.attrib.get(HtmlAttribute.CONTENT))
            if key and content and key not in contents:
                contents[key] = content
        return next((contents[name.casefold()] for name in names if name.casefold() in contents), None)

    def _page_title(self, title: str) -> str:
        """Clean the product name read from a product page title, e.g. to remove a brand suffix.

        Args:
            title (str): The page title.

        Returns:
            str: The product name.
        """
        return self._clean_text(title)

    def _page_name(self, response: Response) -> Optional[str]:
        """Read the product name of a product page: its Open Graph title, else its first heading.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The product name, `None` when the page has none.
        """
        title = self._meta_content(response, PageMetaName.OG_TITLE)
        if title is None and (heading := response.css("h1").first) is not None:
            title = heading.get_all_text(separator=" ", strip=True)
        return self._page_title(title) if title else None

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the product description of a product page: its meta description, else its Open Graph one.

        Args:
            response (Response): The product page.

        Returns:
            Optional[str]: The description, `None` when the page has none.
        """
        return self._meta_content(response, PageMetaName.DESCRIPTION, PageMetaName.OG_DESCRIPTION)

    def _product_page_request(
        self,
        url: str,
        name: Optional[str] = None,
        updated: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> Optional[Request]:
        """Build the request of a product page, whose product is read from the page (`PRODUCT_PAGE` meta).

        Args:
            url (str): The absolute product page URL.
            name (Optional[str]): The product name given by the listing,
                preferred to the page title.
            updated (Optional[str]): The last modification of the page given by a sitemap, preferred to the page
                `meta` tags.
            categories (Optional[Sequence[str]]): The categories the listing files the product under, carried by the
                request (`PRODUCT_CATEGORIES` meta) when there are some.

        Returns:
            Optional[Request]: The request, `None` when a product
                of this page was already streamed.
        """
        if self._url_key(url) in self.seen_urls:
            self.logger.debug("Not requesting the product page %s, its product is already streamed.", url)
            return None
        meta: Dict[str, Union[str, List[str]]] = {self.PRODUCT_PAGE: url}
        if name and self._clean_text(name):
            meta[self.PRODUCT_NAME] = self._clean_text(name)
        if updated:
            meta[self.PRODUCT_UPDATED] = updated
        if categories:
            meta[self.PRODUCT_CATEGORIES] = list(categories)
        return Request(url, meta=meta)

    def _page_categories(self, response: Response) -> List[str]:
        """Read the catalogue categories a request carries, e.g. a product page request.

        Args:
            response (Response): The page, requested with the `PRODUCT_CATEGORIES` meta, if any.

        Returns:
            List[str]: The categories (`PRODUCT_CATEGORIES` meta), empty when the request carries none.
        """
        categories = response.meta.get(self.PRODUCT_CATEGORIES)
        if not isinstance(categories, list):
            return []
        return [str(category) for category in categories if category]

    def _page_product(self, response: Response) -> Optional[CloudProduct]:
        """Extract the product of a product page: its name and description, filed under the request categories.

        Args:
            response (Response): The product page, requested with the `PRODUCT_PAGE` meta.

        Returns:
            Optional[CloudProduct]: The product, `None` for a missing page (HTTP error),
                a redirected (retired) page or an article page.

        Notes:
            A redirected page is a retired product, unless
            the product is named by a listing and its page moved
            within the same website (not to its home page):
            the product is then kept with its new page.
        """
        requested = str(response.meta.get(self.PRODUCT_PAGE, response.url))
        if response.status >= 400:
            self.logger.debug("Skipping %s, the page is missing (HTTP %s).", requested, response.status)
            return None
        listed = response.meta.get(self.PRODUCT_NAME)
        if self._url_key(response.url) != self._url_key(requested):
            final, origin = urlparse(response.url), urlparse(requested)
            if not listed or final.netloc != origin.netloc or not final.path.strip("/"):
                self.logger.debug("Skipping %s, redirected to %s (retired product).", requested, response.url)
                return None
            self.logger.debug("The product page %s moved to %s.", requested, response.url)
        name = str(listed) if listed else self._page_name(response)
        if not name or (not listed and (":" in name or "?" in name)):
            self.logger.debug("Skipping %s, not a product page (title %r).", response.url, name)
            return None
        added = self._meta_content(response, *self.ADDED_META)
        updated = response.meta.get(self.PRODUCT_UPDATED) or self._meta_content(response, *self.UPDATED_META)
        return self._build_product(
            name,
            self._page_description(response),
            response.url,
            self._parse_date(added, name) if added else None,
            self._parse_date(str(updated), name) if updated else None,
            DateCaveat.PAGE_PUBLISHED,
            DateCaveat.PAGE_MODIFIED,
            categories=self._page_categories(response),
        )

    def _record_page_dates(self, response: Response) -> None:
        """Remember the last modification of the pages listed by a sitemap, unless they are all of the same day.

        Args:
            response (Response): A `dates_sitemaps` sitemap.

        Notes:
            Some websites date every page of their sitemap
            with the generation date of the sitemap: such dates tell
            nothing about the pages and are ignored.
        """
        dates = {url: lastmod for url, lastmod in self._sitemap_entries(response).items() if lastmod}
        days = {lastmod[:10] for lastmod in dates.values()}
        if len(dates) >= self.SAME_DAY_LIMIT and len(days) == 1:
            self.logger.info(
                "The %s sitemap %s dates its %d pages %s, its generation date: its dates are ignored.",
                self.name,
                response.url,
                len(dates),
                days.pop(),
            )
            return
        self.page_dates.update({self._url_key(url): lastmod for url, lastmod in dates.items()})
        self.logger.info("%d page dates read from the %s sitemap %s.", len(dates), self.name, response.url)

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure stealth crawler session.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.

        Notes:
            It is the first hook scrapling calls once the spider
            logger is created: the logger is handed over to the
            application logging configuration here, so that even
            the spider initialization is logged through it.
        """
        self._use_application_logging()
        self.logger.debug("Configuring the stealth browser session %s.", self._browser_session_id())
        manager.add(
            self._browser_session_id(),
            AsyncStealthySession(
                timeout=120000,
                wait=2000,
                headless=False,
                load_dom=True,
                solve_cloudflare=self.solve_cloudflare,
                retries=self.fetch_retries,
                retry_delay=self.retry_delay,
            ),
            lazy=self.lazy_browser,
        )

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the products of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if resuming:
            self.logger.info(
                "Resuming the %s catalogue crawl (%d products already streamed).", self.name, len(self.seen_products)
            )
        else:
            self.seen_products.clear()
            self.seen_urls.clear()
            self.page_dates.clear()
            self.logger.info("Starting the %s catalogue crawl from %s.", self.name, self.catalogue_url)

    async def on_error(self, request: Request, error: Exception) -> None:
        """Log the failed requests.

        Args:
            request (Request): The failed request.
            error (Exception): The error.

        Notes:
            The crawl engine already logs the errors raised
            while parsing a page (the crawler errors), not the fetch
            errors (network, browser, ...).
        """
        await super().on_error(request, error)
        if isinstance(error, CrawlerError):
            self.logger.debug("The %s catalogue page %s was not processed: %s", self.name, request.url, error)
        else:
            self.logger.error("Fetching the %s catalogue page %s failed: %r", self.name, request.url, error)

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        self.logger.info("The %s catalogue crawl is over: %d products streamed.", self.name, len(self.seen_products))

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the catalogue URL.

        Yields:
            Request: The `dates_sitemaps` requests (first), the main catalogue page request,
                then the complementary pages ones (lower priority, a sitemap already read for its dates is
                requested again, not filtered out as a duplicate).
        """
        for url in self.dates_sitemaps:
            self.logger.debug("Requesting the %s sitemap %s for the dates of the product pages.", self.name, url)
            yield Request(url, priority=self.DATES_PRIORITY, dont_filter=True, meta={self.PAGE_DATES: url})
        self.logger.debug("Requesting the %s catalogue page %s.", self.name, self.catalogue_url)
        yield self._catalogue_request()
        for url in self.complement_urls:
            self.logger.debug("Requesting the %s complementary catalogue page %s.", self.name, url)
            request = self._complement_request(url)
            if url in self.dates_sitemaps:
                request.dont_filter = True
            yield request

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of a catalogue page.

        Args:
            response (Response): The catalogue page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page, duplicates included.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the catalogue extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the products of a catalogue page, or the product of a product page.

        Args:
            response (Response): The catalogue page, or a product page (`PRODUCT_PAGE` meta).

        Yields:
            Dict[str, JsonValue]: Each product not streamed yet, as a dictionary.

        Raises:
            EmptyCatalogueError: If a catalogue page holds no valid product at all.
        """
        self.logger.debug("Parsing the %s catalogue page %s (HTTP %s).", self.name, response.url, response.status)
        if self.PAGE_DATES in response.meta:
            if response.status < 400:
                self._record_page_dates(response)
            else:
                self.logger.warning(
                    "The %s sitemap %s is unavailable (HTTP %s).", self.name, response.url, response.status
                )
            return
        if self.PRODUCT_PAGE in response.meta:
            product = self._page_product(response)
            if product is not None and (page_item := self._stream(product)) is not None:
                yield page_item
            return
        found = duplicates = 0
        for product in self.extract_products(response):
            found += 1
            item = self._stream(product)
            if item is None:
                duplicates += 1
                continue
            yield item
        if not found:
            self.logger.error("The %s catalogue page %s holds no product.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        self.logger.info(
            "%s catalogue page %s parsed: %d new products, %d duplicates skipped.",
            self.name,
            response.url,
            found - duplicates,
            duplicates,
        )
