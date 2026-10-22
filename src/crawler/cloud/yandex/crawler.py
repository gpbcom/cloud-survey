from __future__ import annotations

# Standard Library Imports.
import html
import json
import re
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.yandex.enums import (
    YandexHttpHeader,
    YandexLocale,
    YandexPageStateField,
    YandexServiceField,
    YandexServiceGroup,
)
from crawler.exception import CatalogueFormatError

# First Party Imports.
from crawler.tls.ca_bundle import CaBundle
from models.cloud.products.product import CloudProduct


class YandexCloudCrawler(BaseCloudCrawler):
    """Yandex Cloud catalogue crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root.
        SERVICES_URL (ClassVar[str]): The services page of the international (English) website, the main source.
        RUSSIAN_SERVICES_URL (ClassVar[str]): The services page of the Russian website, which lists a few more
            services.
        SITEMAP_URL (ClassVar[str]): The sitemap of the website pages, dating the service pages.
        USER_AGENT (ClassVar[str]): The user agent of the HTTP session, naming the crawler.
        CAPTCHA_PATH (ClassVar[str]): The path prefix of the captcha page the website redirects the bots it
            rejects to.
        STATE_ASSIGNMENT (ClassVar[re.Pattern[str]]): The assignment of the page state (`__DATA__ = {...}`) in the
            page scripts.
        STATE_DECODER (ClassVar[json.JSONDecoder]): The decoder of the page state, which a script statement follows.
        INLINE_TAG (ClassVar[re.Pattern[str]]): The inline HTML tags of the texts, removed (e.g. `<sup>`).
        TAG (ClassVar[re.Pattern[str]]): The other HTML tags of the texts, replaced by a space.
        EXCLUDED_CATEGORIES (ClassVar[FrozenSet[YandexServiceGroup]]): The slugs of the service groups which are not
            categories: the featured services, a selection of the other groups.
        ALL_SERVICES (ClassVar[YandexServiceGroup]): The key of the list of every service available in the region.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The English services page.
        complement_urls (ClassVar[Tuple[str, ...]]): The Russian services page.
        dates_sitemaps (ClassVar[Tuple[str, ...]]): The sitemap of the website pages.
        name_prefixes (ClassVar[Tuple[str, ...]]): The brand prefixes of the service names.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it (none does).

    Notes:
        The website redirects the requests of web browsers (and of any client announcing a browser user agent) to a
        captcha (`/showcaptchafast`), the stealth browser included: the pages are read through an HTTP session
        (`yandex-http`, the default one) announcing the crawler in its user agent, which the website serves. A page
        redirected to the captcha anyway is an error.
        The services page (https://yandex.cloud/en/services) is rendered on the server and embeds its state in a
        script (`__DATA__ = {...}`): `context.servicesData` lists the service groups (`categories`: slug and name,
        e.g. `Data Platform`) and the services of each group (`dataByCategory`, by group slug), plus every service
        of the region (`available-in-region`). A service gives its name, its description (with HTML entities and
        tags, removed) and its page, `/en/services/<slug>`, or an external website (`externalUrl`, e.g. AI Studio).
        The `Featured` group, a selection of the other groups, is not a category. The website groups have no
        sub-groups: a service is filed under the names of the groups listing it, gathered before it is built.
        A service without description is read from its page (meta description), filed under its groups.
        The Russian services page completes the English one with the services it is the only one to list, named
        and described in Russian. The service pages are dated by the last modification the sitemap gives them.
    """

    SITE_URL: ClassVar[str] = "https://yandex.cloud"
    SERVICES_URL: ClassVar[str] = f"{SITE_URL}/en/services"
    RUSSIAN_SERVICES_URL: ClassVar[str] = f"{SITE_URL}/ru/services"
    SITEMAP_URL: ClassVar[str] = f"{SITE_URL}/sitemap_pages.xml"
    USER_AGENT: ClassVar[str] = "Mozilla/5.0 (compatible; poc-crawler/0.1.0)"
    CAPTCHA_PATH: ClassVar[str] = "/showcaptcha"
    STATE_ASSIGNMENT: ClassVar[re.Pattern[str]] = re.compile(r"(?<![\w$])(?:window\.)?__DATA__\s*=\s*(?=\{)")
    STATE_DECODER: ClassVar[json.JSONDecoder] = json.JSONDecoder()
    INLINE_TAG: ClassVar[re.Pattern[str]] = re.compile(r"</?(?:sup|sub|em|strong|b|i|span|a|nobr)\b[^>]*>", re.I)
    TAG: ClassVar[re.Pattern[str]] = re.compile(r"<[^>]*>")
    EXCLUDED_CATEGORIES: ClassVar[FrozenSet[YandexServiceGroup]] = frozenset({YandexServiceGroup.FEATURED})
    ALL_SERVICES: ClassVar[YandexServiceGroup] = YandexServiceGroup.AVAILABLE_IN_REGION

    name = "yandex"
    catalogue_url: ClassVar[str] = SERVICES_URL
    complement_urls: ClassVar[Tuple[str, ...]] = (RUSSIAN_SERVICES_URL,)
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Yandex Cloud ", "Yandex ")
    lazy_browser: ClassVar[bool] = True

    ############################
    # Internal Helpers Methods #
    ############################

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, `yandex-http`.
        """
        return f"{self.name}-http"

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
            value (JsonValue): The JSON value, e.g. `Managed Kubernetes<sup>®</sup> clusters` (with HTML
                entities).

        Returns:
            Optional[str]: The plain text with single spaces, e.g. `Managed Kubernetes® clusters`, `None` when the
                value is not a string or is blank.
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

    def _services_data(self, response: Response) -> Dict[str, JsonValue]:
        """Read the services data of a services page.

        Args:
            response (Response): The services page.

        Returns:
            Dict[str, JsonValue]: The services data (`context.servicesData`), empty when the page has none.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        context = self._as_object(self._page_state(response).get(YandexPageStateField.CONTEXT))
        data = self._as_object(context.get(YandexPageStateField.SERVICES_DATA))
        if not data:
            self.logger.warning("The %s page %s has no services data.", self.name, response.url)
        return data

    def _service_groups(self, data: Dict[str, JsonValue]) -> List[Tuple[Optional[str], List[JsonValue]]]:
        """List the service groups of the services data, with their services.

        Args:
            data (Dict[str, JsonValue]): The services data.

        Returns:
            List[Tuple[Optional[str], List[JsonValue]]]: The name and the services of each group, in the page order
                and without the excluded ones, then the services of the region without group name.
        """
        categories = data.get(YandexServiceField.CATEGORIES)
        by_category = self._as_object(data.get(YandexServiceField.DATA_BY_CATEGORY))
        groups: List[Tuple[Optional[str], List[JsonValue]]] = []
        for category in map(self._as_object, categories if isinstance(categories, list) else []):
            slug = self._as_text(category.get(YandexServiceField.SLUG))
            label = self._plain_text(category.get(YandexServiceField.NAME))
            if not slug or slug in self.EXCLUDED_CATEGORIES:
                self.logger.debug("Skipping the %s service group %r (%s).", self.name, label, slug)
                continue
            services = by_category.get(slug)
            groups.append((label, services if isinstance(services, list) else []))
        everything = by_category.get(self.ALL_SERVICES)
        groups.append((None, everything if isinstance(everything, list) else []))
        self.logger.debug("%d %s service groups found.", len(groups) - 1, self.name)
        return groups

    def _listed_services(self, response: Response) -> List[Tuple[Dict[str, JsonValue], List[str]]]:
        """Gather the services of a services page with the names of all the groups listing them.

        Args:
            response (Response): The services page.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str]]]: Each service once, as first listed, and its groups in their
                page order.

        Raises:
            CatalogueFormatError: If the page embeds no page state.

        Notes:
            The listings of a service are matched by slug, else by name. A listing with neither is kept on its own,
            to be skipped (logged) as an invalid entry.
        """
        entries: List[Tuple[Dict[str, JsonValue], List[str]]] = []
        positions: Dict[str, int] = {}
        for label, services in self._service_groups(self._services_data(response)):
            for service in map(self._as_object, services):
                key = self._as_text(service.get(YandexServiceField.SLUG)) or self._plain_text(
                    service.get(YandexServiceField.NAME)
                )
                position = positions.get(key) if key else None
                if position is None:
                    position = len(entries)
                    entries.append((service, []))
                    if key:
                        positions[key] = position
                if label and label not in entries[position][1]:
                    entries[position][1].append(label)
        self.logger.debug("%d %s services listed by %s.", len(entries), self.name, response.url)
        return entries

    def _service_url(self, service: Dict[str, JsonValue], response: Response) -> Optional[str]:
        """Get the page of a service: its external website, else its page of the website.

        Args:
            service (Dict[str, JsonValue]): The service.
            response (Response): The services page, whose locale (`en`, `ru`) the service page shares.

        Returns:
            Optional[str]: The absolute page URL, e.g. `https://yandex.cloud/en/services/compute`, `None` without
                external website nor slug.
        """
        external = self._as_text(service.get(YandexServiceField.EXTERNAL_URL))
        if external and external.strip():
            return external.strip()
        slug = self._as_text(service.get(YandexServiceField.SLUG))
        if not slug:
            return None
        locale = urlparse(response.url).path.strip("/").split("/")[0] or YandexLocale.ENGLISH
        return f"{self.SITE_URL}/{locale}/services/{slug}"

    def _needs_page(self, description: Optional[str], url: Optional[str]) -> bool:
        """Tell whether a service is read from its page: it has no description but a page of the website.

        Args:
            description (Optional[str]): The service description.
            url (Optional[str]): The service page.

        Returns:
            bool: Whether the service page is requested instead of building the service from the listing.
        """
        return description is None and url is not None and urlparse(url).netloc == urlparse(self.SITE_URL).netloc

    def _service_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the services of a services page, filed under their groups.

        Args:
            response (Response): The services page.

        Yields:
            Iterator[CloudProduct]: Each valid described service, once.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        for service, groups in self._listed_services(response):
            name = self._plain_text(service.get(YandexServiceField.NAME))
            description = self._plain_text(service.get(YandexServiceField.DESCRIPTION))
            url = self._service_url(service, response)
            if self._needs_page(description, url):
                self.logger.debug("The %s service %r has no description, its page %s is read.", self.name, name, url)
                continue
            if product := self._build_product(name, description, url, categories=groups):
                yield product

    def _product_page_request(
        self,
        url: str,
        name: Optional[str] = None,
        updated: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> Optional[Request]:
        """Build the request of a service page, read before the Russian services page (primary priority).

        Args:
            url (str): The absolute service page URL.
            name (Optional[str]): The service name given by the services page.
            updated (Optional[str]): The last modification of the page given by a sitemap.
            categories (Optional[Sequence[str]]): The groups of the service (`PRODUCT_CATEGORIES` meta), if any.

        Returns:
            Optional[Request]: The request, `None` when a product of this page was already streamed.

        Notes:
            The service is then streamed under its English name and page, before the Russian services page lists it.
        """
        request = super()._product_page_request(url, name, updated, categories)
        if request is None:
            return None
        return Request(request.url, meta=request.meta, priority=self.PRIMARY_PRIORITY)

    def _description_requests(self, response: Response) -> List[Request]:
        """Request the pages of the services of a services page without description, not streamed yet.

        Args:
            response (Response): The services page.

        Returns:
            List[Request]: The service page requests, carrying the service name and groups.

        Raises:
            CatalogueFormatError: If the page embeds no page state.
        """
        requests: List[Request] = []
        for service, groups in self._listed_services(response):
            name = self._plain_text(service.get(YandexServiceField.NAME))
            url = self._service_url(service, response)
            if url is None or not self._needs_page(self._plain_text(service.get(YandexServiceField.DESCRIPTION)), url):
                continue
            if name and self._name_key(name) in self.seen_products:
                self.logger.debug("Not requesting the %s page %s, %r is already streamed.", self.name, url, name)
                continue
            if (request := self._product_page_request(url, name, categories=groups)) is not None:
                requests.append(request)
        self.logger.info("%d %s service pages requested for their description.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the stealth browser session (never started) and the HTTP session, the default one.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.

        Notes:
            The HTTP session has the TLS fingerprint of Chrome but announces the crawler (`USER_AGENT`), without the
            browser headers: the website rejects the clients announcing a browser to a captcha.
        """
        super().configure_sessions(manager)
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

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the described services of a services page.

        Args:
            response (Response): The English or Russian services page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        return self._service_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the services of a services page and request the pages of those without description.

        Args:
            response (Response): A services page, a service page (`PRODUCT_PAGE` meta) or the sitemap (`PAGE_DATES`
                meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, then the service page requests.

        Raises:
            CatalogueFormatError: If the page is the captcha, or a services page embeds no page state.
            EmptyCatalogueError: If a services page holds no valid service.
        """
        self._reject_captcha(response)
        async for item in super().parse(response):
            yield item
        if self.PRODUCT_PAGE not in response.meta and self.PAGE_DATES not in response.meta:
            for request in self._description_requests(response):
                yield request
