from __future__ import annotations

# Standard Library Imports.
import html
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlencode, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.yandex.enums import (
    YandexHttpHeader,
    YandexLocale,
    YandexPageStateField,
    YandexPriceField,
    YandexServiceField,
    YandexServiceGroup,
    YandexUnitPart,
)
from crawler.exception import CatalogueFormatError

# First Party Imports.
from crawler.tls.ca_bundle import CaBundle
from models.cloud.enums import PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
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
        PRICE_HEADERS (ClassVar[Dict[str, str]]): The headers of the price session (the crawler named, as for the
            pages).
        PRICES_URL (ClassVar[str]): The public price list API (no key) of the Russian installation, in rubles.
        PRICE_CURRENCY (ClassVar[str]): Its currency.
        UNIT_COUNT (ClassVar[re.Pattern[str]]): The count a pricing unit may start with, e.g. `10k`.
        MULTIPLIERS (ClassVar[Dict[str, Decimal]]): The value of a count multiplier.
        THING_PERIOD_UNITS (ClassVar[Dict[Tuple[str, str], Tuple[PriceUnit, Decimal]]]): The unit of a thing per
            period with a unit of its own (`core*hour`, `gbyte*month`, `server*month`).
        PERIOD_UNITS (ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]]): The unit of another thing per period.
        THING_UNITS (ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]]): The unit of a bare thing or period.
        VAT_ATTRIBUTE (ClassVar[str]): The attribute telling whether the price includes the VAT.
        VAT_INCLUDED (ClassVar[str]): The ruble prices include it.
        price_rows (int): The prices read, in price mode.

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
        In price mode it reads the public price list API (`PRICES_URL`, the crawler named as for the pages): every
        SKU of every service, one price per rate (tier, a free first tier being free), in rubles VAT included,
        page by page (`nextPageToken`). Its pricing unit is normalized from its parts (`10k*request`). The list is
        one source, recorded once its last page is read.
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
    PRICE_HEADERS: ClassVar[Dict[str, str]] = {YandexHttpHeader.USER_AGENT: USER_AGENT}
    PRICES_URL: ClassVar[str] = (
        f"{SITE_URL}/api/priceList/getPriceList?installationCode=ru&currency=RUB&lang=en&pageSize=1000"
    )
    PRICE_CURRENCY: ClassVar[str] = "RUB"
    UNIT_COUNT: ClassVar[re.Pattern[str]] = re.compile(r"^(\d+)([km])?$")
    MULTIPLIERS: ClassVar[Dict[str, Decimal]] = {"k": Decimal(1000), "m": Decimal(1_000_000)}
    THING_PERIOD_UNITS: ClassVar[Dict[Tuple[str, str], Tuple[PriceUnit, Decimal]]] = {
        (YandexUnitPart.CORE, YandexUnitPart.HOUR): (PriceUnit.VCPU_HOUR, Decimal(1)),
        (YandexUnitPart.GBYTE, YandexUnitPart.HOUR): (PriceUnit.GIB_HOUR, Decimal(1)),
        (YandexUnitPart.GBYTE, YandexUnitPart.DAY): (PriceUnit.GIB_HOUR, Decimal(24)),
        (YandexUnitPart.GBYTE, YandexUnitPart.MONTH): (PriceUnit.GIB_MONTH, Decimal(1)),
        (YandexUnitPart.SERVER, YandexUnitPart.MONTH): (PriceUnit.MONTH, Decimal(1)),
    }
    PERIOD_UNITS: ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]] = {
        YandexUnitPart.HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        YandexUnitPart.DAY: (PriceUnit.UNIT_HOUR, Decimal(24)),
        YandexUnitPart.MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
    }
    THING_UNITS: ClassVar[Dict[str, Tuple[PriceUnit, Decimal]]] = {
        YandexUnitPart.GBYTE: (PriceUnit.GIB, Decimal(1)),
        YandexUnitPart.HOUR: (PriceUnit.HOUR, Decimal(1)),
        YandexUnitPart.MONTH: (PriceUnit.MONTH, Decimal(1)),
        YandexUnitPart.MINUTE: (PriceUnit.MINUTE, Decimal(1)),
        YandexUnitPart.SECOND: (PriceUnit.SECOND, Decimal(1)),
        YandexUnitPart.SECONDS: (PriceUnit.SECOND, Decimal(1)),
        YandexUnitPart.FIFTEEN_SECONDS: (PriceUnit.SECOND, Decimal(15)),
        YandexUnitPart.TOKEN: (PriceUnit.TOKEN, Decimal(1)),
        YandexUnitPart.SYMBOL: (PriceUnit.CHARACTER, Decimal(1)),
        YandexUnitPart.SYMBOLS: (PriceUnit.CHARACTER, Decimal(1)),
        YandexUnitPart.IMAGE: (PriceUnit.IMAGE, Decimal(1)),
        **{
            word: (PriceUnit.REQUEST, Decimal(1))
            for word in (
                YandexUnitPart.REQUEST,
                YandexUnitPart.REQUEST_UNIT,
                YandexUnitPart.EVENT,
                YandexUnitPart.MESSAGE,
                YandexUnitPart.INVOCATION,
                YandexUnitPart.CALL,
                YandexUnitPart.PHONE_CALL,
                YandexUnitPart.ROW,
                YandexUnitPart.SCAN,
                YandexUnitPart.OBJECTS,
                YandexUnitPart.EMAIL,
                YandexUnitPart.SMS,
                YandexUnitPart.DIALOG,
                YandexUnitPart.SESSION,
                YandexUnitPart.POINT,
                YandexUnitPart.POINTS,
            )
        },
        **{
            word: (PriceUnit.UNIT, Decimal(1))
            for word in (
                YandexUnitPart.USER,
                YandexUnitPart.UNIT,
                YandexUnitPart.APPLICATION,
                YandexUnitPart.RESOURCE,
            )
        },
    }
    VAT_ATTRIBUTE: ClassVar[str] = "vat"
    VAT_INCLUDED: ClassVar[str] = "included"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.price_rows = 0

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

    def _pricing_unit(self, unit: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize a Yandex Cloud pricing unit, e.g. `core*hour`, `10k*request`, `gbyte*month`.

        Args:
            unit (str): The pricing unit.

        Returns:
            Tuple[PriceUnit, Decimal]: The normalized unit and the normalized units in one: its leading count (`10k`
                is 10,000), a thing per period (`core*hour` a vCPU-hour, `gpu*hour` a unit-hour), or a bare thing
                (`token`, `gbyte`), other when unknown.
        """
        parts = unit.split("*")
        count = self.UNIT_COUNT.match(parts[0]) if len(parts) > 1 else None
        factor = Decimal(1)
        if count is not None:
            factor = Decimal(count[1]) * self.MULTIPLIERS.get(count[2] or "", Decimal(1))
            parts = parts[1:]
        thing, period = (parts[0], parts[-1]) if len(parts) > 1 else (parts[0], None)
        if period is not None:
            if (thing, period) in self.THING_PERIOD_UNITS:
                normalized, scale = self.THING_PERIOD_UNITS[(thing, period)]
                return normalized, factor * scale
            if period in self.PERIOD_UNITS:
                normalized, scale = self.PERIOD_UNITS[period]
                return normalized, factor * scale
        elif thing in self.THING_UNITS:
            normalized, scale = self.THING_UNITS[thing]
            return normalized, factor * scale
        self.logger.debug("The Yandex Cloud pricing unit %r has no known unit: kept as other.", unit)
        return PriceUnit.OTHER, factor

    def _sku_prices(self, sku: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of a SKU of the price list, one per rate (tier).

        Args:
            sku (Dict[str, JsonValue]): The SKU.

        Yields:
            ServicePrice: One price per rate, a free first tier being free (a rate without end ends where the next
                one starts).
        """
        name = sku.get(YandexPriceField.NAME)
        service = sku.get(YandexPriceField.SERVICE)
        service = service if isinstance(service, dict) else {}
        version = sku.get(YandexPriceField.PRICING_VERSION)
        version = version if isinstance(version, dict) else {}
        expression = version.get(YandexPriceField.PRICING_EXPRESSION)
        rates = expression.get(YandexPriceField.RATES) if isinstance(expression, dict) else None
        effective = version.get(YandexPriceField.EFFECTIVE_TIME)
        effective_day = (
            datetime.fromtimestamp(effective / 1000, tz=UTC).date().isoformat() if isinstance(effective, int) else None
        )
        unit_text = str(sku.get(YandexPriceField.PRICING_UNIT) or "")
        unit, factor = self._pricing_unit(unit_text)
        tiers = [rate for rate in rates if isinstance(rate, dict)] if isinstance(rates, list) else []
        for index, rate in enumerate(tiers):
            try:
                price = Decimal(str(rate.get(YandexPriceField.UNIT_PRICE)))
            except ArithmeticError:
                self.logger.debug("A rate of the Yandex Cloud SKU %s has no price: skipped.", name)
                continue
            start = rate.get(YandexPriceField.START_PRICING_QUANTITY)
            end = rate.get(YandexPriceField.END_PRICING_QUANTITY) or (
                tiers[index + 1].get(YandexPriceField.START_PRICING_QUANTITY) if index + 1 < len(tiers) else None
            )
            fields: Dict[str, RawValue] = {
                "sku_key": f"{name}/{index}",
                "service": service.get(YandexPriceField.DESCRIPTION) or service.get(YandexPriceField.NAME),
                "family": service.get(YandexPriceField.GROUP),
                "attributes": {
                    YandexPriceField.TRANSLATED_NAME.value: sku.get(YandexPriceField.TRANSLATED_NAME),
                    YandexPriceField.TRANSLATED_PRICING_UNIT.value: sku.get(YandexPriceField.TRANSLATED_PRICING_UNIT),
                    self.VAT_ATTRIBUTE: self.VAT_INCLUDED,
                },
                "unit": unit,
                "unit_raw": unit_text,
                "unit_factor": factor,
                "price": price,
                "currency": self.PRICE_CURRENCY,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                "tier_start": Decimal(str(start)) if isinstance(start, str) and start else Decimal(0),
                "tier_end": Decimal(str(end)) if isinstance(end, str) and end else None,
                "effective_from": effective_day,
                "source_url": self.PRICES_URL,
                "source_kind": PriceSourceKind.API,
            }
            fact = self._price_fact(fields)
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the price list.

        Yields:
            Request: The request of the first page.
        """
        self.price_rows = 0
        self.logger.info("Reading the Yandex Cloud prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a page of the price list: the next page first, then its prices.

        Args:
            response (Response): The page.

        Yields:
            PriceFact: The request of the next page, then the prices of the page.

        Raises:
            CatalogueFormatError: If the page lists no SKUs.
        """
        data = self._json_body(response)
        skus = data.get(YandexPriceField.SKUS) if isinstance(data, dict) else None
        if not isinstance(data, dict) or not isinstance(skus, list):
            self.logger.error("The Yandex Cloud price list page %s lists no SKUs.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price list page lists no SKUs")
        token = data.get(YandexPriceField.NEXT_PAGE_TOKEN)
        if isinstance(token, str) and token:
            yield self._price_request(f"{self.PRICES_URL}&{urlencode({YandexPriceField.PAGE_TOKEN.value: token})}")
        found = 0
        for sku in skus:
            for fact in self._sku_prices(sku) if isinstance(sku, dict) else iter(()):
                found += 1
                yield fact
        self.price_rows += found
        if not (isinstance(token, str) and token):
            self._record_price_source(self.PRICES_URL, self.price_rows)
            self.logger.info("The Yandex Cloud price list is read whole: %d prices.", self.price_rows)

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
        self.logger.debug("Reading the %s services of %s.", self.name, response.url)
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
            self.logger.debug("Requesting the %s service pages missing a description.", self.name)
            for request in self._description_requests(response):
                yield request
