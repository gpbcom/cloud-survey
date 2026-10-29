from __future__ import annotations

# Standard Library Imports.
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import quote, urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.ibm.enums import (
    IbmCatalogueTag,
    IbmCategoryField,
    IbmGlobalCatalogField,
    IbmGlobalCatalogParameter,
    IbmOfferField,
    IbmOfferType,
    IbmPriceField,
    IbmPriceStage,
    IbmPricingType,
    IbmScriptVariable,
    IbmStateField,
)
from crawler.enums import HtmlAttribute, TextEncoding
from crawler.exception import CatalogueFormatError

# First Party Imports.
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class IBMCloudCrawler(BaseCloudCrawler):
    """IBM Cloud catalogue crawler.

    Attributes:
        CATALOG_HOST (ClassVar[str]): The IBM Cloud console, which serves the catalogue and the product pages.
        PRODUCTS_URL (ClassVar[str]): The "IBM Cloud" product search fragment of the ibm.com products page.
        STATE_MARKER (ClassVar[IbmScriptVariable]): The script variable holding the catalogue data.
        KEPT_TAG (ClassVar[IbmCatalogueTag]): The catalogue tag of the offers created by IBM (not third party or
            community).
        KEPT_TYPES (ClassVar[FrozenSet[IbmOfferType]]): The catalogue types of the services (not content or pillars).
        EXCLUDED_TAGS (ClassVar[FrozenSet[IbmCatalogueTag]]): The catalogue tags of the deprecated and beta services.
        TEST_HOST (ClassVar[re.Pattern[str]]): The hosts of the IBM test environments, whose links are dropped.
        NOT_PRODUCT_CARD (ClassVar[re.Pattern[str]]): The product search cards which are overviews, not products.
        CARD_ALIASES (ClassVar[Dict[str, str]]): The catalogue names of the products named otherwise on ibm.com.
        GLOBAL_CATALOG_URL (ClassVar[str]): The IBM Global Catalog API (no key), dating the launch of the products.
        SEARCH_LIMIT (ClassVar[int]): How many resources a Global Catalog search returns.
        MIGRATION_DAY (ClassVar[date]): The day many Global Catalog resources were created by a bulk migration.
        SERVICES_URL (ClassVar[str]): A page of the services of the Global Catalog.
        PLANS_URL (ClassVar[str]): A page of the plans of a service, with their pricing metadata.
        PRICING_URL (ClassVar[str]): The pricing of a plan or of a deployment.
        DEPLOYMENTS_URL (ClassVar[str]): The deployments (regions) of a plan.
        PRICE_COUNTRY (ClassVar[str]): The country whose price list is read (the dollar one).
        PRICE_CURRENCY (ClassVar[str]): Its currency.
        CHARGE_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]]): The rules normalizing a charge
            unit, in order.
        PROFILE (ClassVar[re.Pattern[str]]): A VPC profile plan name, capturing its vCPUs and memory (`bx2-2x8`).
        PLAN_UNIT (ClassVar[str]): The unit written for a plan without priced metric.
        NO_PRICING_REASON (ClassVar[str]): Why a plan without pricing has no price.
        MISSING_STATUS (ClassVar[int]): The status of a pricing the Global Catalog does not have.
        PRICE_STAGE (ClassVar[str]): The request meta holding the stage of a price request.
        SERVICE_META (ClassVar[str]): The request meta holding the display name of the service.
        SERVICE_NAME_META (ClassVar[str]): The request meta holding the name of the service.
        SERVICE_ID_META (ClassVar[str]): The request meta holding the identifier of the service.
        PLAN_META (ClassVar[str]): The request meta holding the identifier of the plan.
        PLAN_NAME_META (ClassVar[str]): The request meta holding the name of the plan.
        DEPLOYMENT_META (ClassVar[str]): The request meta holding the identifier of the deployment.
        REGION_META (ClassVar[str]): The request meta holding the region.
        OFFSET_META (ClassVar[str]): The request meta holding the offset of a page.
        catalog_ids (Dict[str, str]): The catalogue offer identifier of each catalogue product, by normalized name.
        price_pending (int): The Global Catalog requests not read yet, in price mode.
        price_rows (int): The prices read, in price mode.

    Notes:
        The main source is the IBM Cloud catalogue (https://cloud.ibm.com/catalog), whose data is embedded in the
        page (`window.__PRELOADED_STATE__`): `model.categories[*].items[*]`, an offer being listed in each of its
        categories. Only the services and infrastructure offers created by IBM are kept, without the deprecated,
        beta and consulting ones. An offer is updated by its last modification (`lastModified`), the catalogue giving
        no creation date. The "IBM Cloud" product search of ibm.com completes it with the products missing from the
        catalogue (e.g. the Cloud Paks).
        Each product is dated by the creation (`created`) of its IBM Global Catalog resource (`dates_launches`),
        often its beta rather than its general availability (`CATALOGUE_ENTRY`). A catalogue product is looked up by
        its offer identifier, which is its Global Catalog identifier. Another product, or an identifier the Global
        Catalog does not know, is searched by name (or under the name the launch dates catalogue's aliases give it):
        the earliest resource whose English display name is the product name wins. The resources created on
        2017-08-24 were created by a bulk migration, long after the launch (`WEBSITE_RECORD`). A few resources were
        created again later (e.g. Power Virtual Server, dated 2024), which the launch dates catalogue corrects.
        The categories of an offer are the names of all the catalogue categories listing it. The product search
        cards give no category, only commercial tags ("Buy Now", "Free Trial").
        In price mode it walks the Global Catalog: the active services (a group's services included), the plans
        of each, then the pricing of each priced plan, in dollars, one price per metric and quantity tier. A plan
        priced by region (no plan pricing, HTTP 404) is read region by region from its deployments. A free or lite
        plan is free, a plan without pricing not public. The catalog is one source, recorded once every request
        is read. A VPC profile plan names its vCPUs and memory (`bx2-2x8`).
    """

    CATALOG_HOST: ClassVar[str] = "https://cloud.ibm.com"
    PRODUCTS_URL: ClassVar[str] = (
        "https://www.ibm.com/content/adobe-cms/us/en/products/jcr:content/root/table_of_contents/"
        "product_search_1183165654.search-full.html?field_hierarchy_07[0][0]=IBM%20Cloud&size=100&page=1"
    )
    STATE_MARKER: ClassVar[IbmScriptVariable] = IbmScriptVariable.PRELOADED_STATE
    KEPT_TAG: ClassVar[IbmCatalogueTag] = IbmCatalogueTag.CREATED
    KEPT_TYPES: ClassVar[FrozenSet[IbmOfferType]] = frozenset({IbmOfferType.SERVICE, IbmOfferType.IAAS})
    EXCLUDED_TAGS: ClassVar[FrozenSet[IbmCatalogueTag]] = frozenset({IbmCatalogueTag.DEPRECATED, IbmCatalogueTag.BETA})
    TEST_HOST: ClassVar[re.Pattern[str]] = re.compile(r"(^|\.)test\.")
    NOT_PRODUCT_CARD: ClassVar[re.Pattern[str]] = re.compile(r"\bproducts$", re.IGNORECASE)
    CARD_ALIASES: ClassVar[Dict[str, str]] = {
        "IBM Red Hat OpenShift": "Red Hat OpenShift on IBM Cloud",
        "IBM Openshift Virtualization": "Red Hat OpenShift Virtualization Service on IBM Cloud",
        "Virtual Servers Classic": "Virtual Server for Classic",
        "Hardware Security Module": "Cloud HSM",
        "Private Path": "Private Path Service for VPC",
        "DNS": "DNS Services",
        "Load Balancer": "Load Balancer for VPC",
        "Direct Link": "Direct Link Connect",
        "Red Hat AI on IBM Cloud": "Red Hat AI Inference",
    }

    GLOBAL_CATALOG_URL: ClassVar[str] = "https://globalcatalog.cloud.ibm.com/api/v1"
    SEARCH_LIMIT: ClassVar[int] = 200
    MIGRATION_DAY: ClassVar[date] = date(2017, 8, 24)
    SERVICES_URL: ClassVar[str] = GLOBAL_CATALOG_URL + "?q=kind:service&_limit=200&_offset={offset}"
    PLANS_URL: ClassVar[str] = GLOBAL_CATALOG_URL + "/{id}/plan?_limit=200&_offset={offset}&include=metadata.pricing"
    PRICING_URL: ClassVar[str] = GLOBAL_CATALOG_URL + "/{id}/pricing"
    DEPLOYMENTS_URL: ClassVar[str] = GLOBAL_CATALOG_URL + "/{id}/deployment?_limit=200"
    PRICE_COUNTRY: ClassVar[str] = "USA"
    PRICE_CURRENCY: ClassVar[str] = "USD"
    CHARGE_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]] = (
        (re.compile(r"\btokens?\b", re.IGNORECASE), PriceUnit.TOKEN),
        (re.compile(r"Core[- ]Hour|VCPU_HOUR|vCPU", re.IGNORECASE), PriceUnit.VCPU_HOUR),
        (re.compile(r"(?:Gigabyte|GIGABYTE|\bGB)[-_ ]?(?:Hour|HOUR)", re.IGNORECASE), PriceUnit.GIB_HOUR),
        (re.compile(r"(?:Gigabyte|GIGABYTE|\bGB)[-_ ]?(?:Month|MONTH)", re.IGNORECASE), PriceUnit.GIB_MONTH),
        (re.compile(r"Gigabyte|GIGABYTE|\bGB\b", re.IGNORECASE), PriceUnit.GIB),
        (re.compile(r"\bHours?\b|_HOURS?\b|-Hour", re.IGNORECASE), PriceUnit.HOUR),
        (re.compile(r"\bMonths?\b|_MONTHS?\b|-Month", re.IGNORECASE), PriceUnit.MONTH),
        (re.compile(r"\bMinutes?\b|_MINUTES?\b", re.IGNORECASE), PriceUnit.MINUTE),
        (re.compile(r"\bSeconds?\b|_SECONDS?\b", re.IGNORECASE), PriceUnit.SECOND),
        (
            re.compile(r"API|Calls?|Requests?|Transactions?|Events?|Messages?|Operations?", re.IGNORECASE),
            PriceUnit.REQUEST,
        ),
        (re.compile(r"Items?|Instances?|Users?|Seats?|Units?", re.IGNORECASE), PriceUnit.UNIT),
    )
    PROFILE: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z]+\d*[a-z]*-(\d+)x(\d+)\b")
    PLAN_UNIT: ClassVar[str] = "plan"
    NO_PRICING_REASON: ClassVar[str] = "The IBM Global Catalog states no pricing for the plan."
    MISSING_STATUS: ClassVar[int] = 404
    PRICE_STAGE: ClassVar[str] = "price_stage"
    SERVICE_META: ClassVar[str] = "price_service"
    SERVICE_NAME_META: ClassVar[str] = "price_service_name"
    SERVICE_ID_META: ClassVar[str] = "price_service_id"
    PLAN_META: ClassVar[str] = "price_plan"
    PLAN_NAME_META: ClassVar[str] = "price_plan_name"
    DEPLOYMENT_META: ClassVar[str] = "price_deployment"
    REGION_META: ClassVar[str] = "price_region"
    OFFSET_META: ClassVar[str] = "price_offset"

    name = "ibm"
    catalogue_url: ClassVar[str] = f"{CATALOG_HOST}/catalog"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRODUCTS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("IBM Cloud ", "IBM ", "Cloud ")
    dates_launches: ClassVar[bool] = True

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.catalog_ids: Dict[str, str] = {}
        self.price_pending = 0
        self.price_rows = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare the IBM Cloud console links with their query, which tells some services apart.

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, followed by the query for the console links (e.g. the OpenShift creation page
                `/kubernetes/catalog/create?platformtype=openshift` is not the Kubernetes Service one).
        """
        link = urlparse(url.casefold())
        key = super()._url_key(url)
        return f"{key}?{link.query}" if link.netloc == urlparse(self.CATALOG_HOST).netloc and link.query else key

    def _state(self, response: Response) -> Dict[str, JsonValue]:
        """Read the catalogue data embedded in the catalogue page (`window.__PRELOADED_STATE__ = {...}`).

        Args:
            response (Response): The catalogue page.

        Returns:
            Dict[str, JsonValue]: The catalogue data.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or if it is not a JSON object.
        """
        text = response.body.decode(TextEncoding.UTF_8, errors=TextEncoding.REPLACE)
        marker = text.find(self.STATE_MARKER)
        equal = text.find("=", marker) if marker >= 0 else -1
        if equal < 0:
            self.logger.error("The %s catalogue page %s has no `%s`.", self.name, response.url, self.STATE_MARKER)
            raise CatalogueFormatError(self.name, response.url, f"the `{self.STATE_MARKER}` data is missing")
        start = len(text) - len(text[equal + 1 :].lstrip())
        try:
            data, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError as e:
            self.logger.error("The %s catalogue data of %s is not JSON: %s", self.name, response.url, e)
            raise CatalogueFormatError(self.name, response.url, "the catalogue data is not JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The %s catalogue data of %s is not a JSON object.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the catalogue data is not a JSON object")
        self.logger.debug("Catalogue data of %s read, with the keys %s.", response.url, ", ".join(data))
        return data

    def _catalog_items(self, response: Response) -> List[Tuple[Dict[str, JsonValue], List[str]]]:
        """Read the catalogue offers, once each, as an offer is listed in each of its categories.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str]]]: The offers, in catalogue order, with the names of the
                categories listing them.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.
        """
        categories = self._as_object(self._state(response).get(IbmStateField.MODEL)).get(IbmStateField.CATEGORIES)
        if not isinstance(categories, list):
            self.logger.error("The %s catalogue data of %s has no `model.categories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`model.categories` is not a list")
        items: Dict[str, Tuple[Dict[str, JsonValue], List[str]]] = {}
        for category in categories:
            fields = self._as_object(category)
            label = self._as_text(fields.get(IbmCategoryField.NAME))
            entries = fields.get(IbmCategoryField.ITEMS)
            for entry in entries if isinstance(entries, list) else []:
                item = self._as_object(entry)
                key = self._as_text(item.get(IbmOfferField.ID)) or self._as_text(item.get(IbmOfferField.NAME)) or ""
                labels = items.setdefault(key, (item, []))[1]
                if label and label not in labels:
                    labels.append(label)
        self.logger.debug("%d catalogue offers in %d categories of %s.", len(items), len(categories), response.url)
        return list(items.values())

    def _skip_reason(self, item: Dict[str, JsonValue]) -> Optional[str]:
        """Tell why a catalogue offer is not a product.

        Args:
            item (Dict[str, JsonValue]): The catalogue offer.

        Returns:
            Optional[str]: The reason (third party, content, deprecated, beta or consulting offer), `None` for a
                product.
        """
        tags = item.get(IbmOfferField.ALL_TAGS)
        tag_set = {tag for tag in tags if isinstance(tag, str)} if isinstance(tags, list) else set()
        reasons = {
            f"tag {item.get(IbmOfferField.TAG)!r}": item.get(IbmOfferField.TAG) != self.KEPT_TAG,
            f"type {item.get(IbmOfferField.TYPE)!r}": item.get(IbmOfferField.TYPE) not in self.KEPT_TYPES,
            "deprecated or beta": bool(tag_set & self.EXCLUDED_TAGS),
            "consulting offer": item.get(IbmOfferField.IS_CONSULTING) is True,
        }
        failed = [reason for reason, matched in reasons.items() if matched]
        return ", ".join(failed) if failed else None

    def _catalog_link(self, link: Optional[str]) -> Optional[str]:
        """Get the absolute URL of a catalogue offer, dropping the links to the IBM test environments.

        Args:
            link (Optional[str]): The catalogue link, usually relative to the IBM Cloud console.

        Returns:
            Optional[str]: The absolute URL, `None` when missing or pointing to a test environment.
        """
        if not link:
            return None
        url = urljoin(f"{self.CATALOG_HOST}/", link)
        if self.TEST_HOST.search(urlparse(url).netloc):
            self.logger.debug("Ignoring the test environment link %s.", url)
            return None
        return url

    def _catalog_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the catalogue: the services and infrastructure offers created by IBM.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[CloudProduct]: Each valid product of the catalogue.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.

        Notes:
            The last modification of an offer (`lastModified`) is its update date, with up to 9 fractional digits of
            seconds (e.g. `2026-07-31T13:50:20.900074515-04:00`), truncated to microseconds.
            A link shared by several offers (e.g. the VPC creation page) is only kept for the first one, so that the
            others are not taken for duplicates.
            The offer identifier is remembered by name, as the Global Catalog identifier dating the product.
        """
        links: Set[str] = set()
        for item, categories in self._catalog_items(response):
            name = self._as_text(item.get(IbmOfferField.NAME))
            if reason := self._skip_reason(item):
                self.logger.debug("Skipping the catalogue offer %r (%s).", name, reason)
                continue
            link = self._catalog_link(self._as_text(item.get(IbmOfferField.CATALOG_URL)))
            if link is not None and self._url_key(link) in links:
                self.logger.debug("Ignoring the link %s of %r, shared with a previous catalogue offer.", link, name)
                link = None
            if link is not None:
                links.add(self._url_key(link))
            catalog_id = self._as_text(item.get(IbmOfferField.ID))
            if name and catalog_id:
                self.catalog_ids.setdefault(self._name_key(name), catalog_id)
            description = self._as_text(item.get(IbmOfferField.DESCRIPTION))
            updated_at = self._parse_date(item.get(IbmOfferField.LAST_MODIFIED), name)
            if product := self._build_product(
                name,
                description,
                link,
                updated_at=updated_at,
                updated_caveat=DateCaveat.CATALOGUE_ENTRY,
                categories=categories,
            ):
                yield product

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the ibm.com product search cards, skipping the overviews and known aliases.

        Args:
            response (Response): The product search fragment.

        Yields:
            Iterator[CloudProduct]: Each valid product of the search.
        """
        cards = response.css(".ibm-search__results__card")
        self.logger.debug("%d product search cards in %s.", len(cards), response.url)
        for card in cards:
            heading, copy, link = card.css(".bx--card__heading").first, card.css(".bx--card__copy").first, card.css("a")
            if heading is None:
                continue
            name = self._clean_text(heading.get_all_text(separator=" ", strip=True))
            alias = self.CARD_ALIASES.get(name)
            if self.NOT_PRODUCT_CARD.search(name):
                self.logger.debug("Skipping the product search card %r (overview).", name)
                continue
            if alias is not None and self._name_key(alias) in self.seen_products:
                self.logger.debug("Skipping the product search card %r (catalogue product %r).", name, alias)
                continue
            description = copy.get_all_text(separator=" ", strip=True) if copy is not None else None
            href = link.first.attrib.get(HtmlAttribute.HREF) if link.first is not None else None
            if product := self._build_product(name, description, urljoin(response.url, href) if href else None):
                yield product

    def _created(self, resource: Dict[str, JsonValue]) -> Optional[datetime]:
        """Read the creation of a Global Catalog resource.

        Args:
            resource (Dict[str, JsonValue]): The resource.

        Returns:
            Optional[datetime]: The creation, `None` when missing, unreadable or implausible.
        """
        catalog_id = self._as_text(resource.get(IbmGlobalCatalogField.ID))
        return self._parse_date(resource.get(IbmGlobalCatalogField.CREATED), catalog_id)

    def _display_key(self, resource: Dict[str, JsonValue]) -> Optional[str]:
        """Get the normalized English display name of a Global Catalog resource.

        Args:
            resource (Dict[str, JsonValue]): The resource.

        Returns:
            Optional[str]: The normalized display name, `None` when the resource has none.
        """
        overview = self._as_object(resource.get(IbmGlobalCatalogField.OVERVIEW_UI))
        texts = self._as_object(overview.get(IbmGlobalCatalogField.ENGLISH))
        display_name = self._as_text(texts.get(IbmGlobalCatalogField.DISPLAY_NAME))
        return self._name_key(display_name) if display_name else None

    def _resource_created(self, payload: JsonValue, catalog_id: str) -> Optional[datetime]:
        """Read the creation of the Global Catalog resource of a catalogue offer.

        Args:
            payload (JsonValue): The API response for the resource.
            catalog_id (str): The offer identifier.

        Returns:
            Optional[datetime]: The creation, `None` when the response is not that resource or has no readable
                creation.
        """
        resource = self._as_object(payload)
        if self._as_text(resource.get(IbmGlobalCatalogField.ID)) != catalog_id:
            self.logger.debug("The Global Catalog answer for %r is not its resource.", catalog_id)
            return None
        return self._created(resource)

    def _earliest_match(self, payload: JsonValue, keys: List[str], name: str) -> Optional[datetime]:
        """Read the earliest creation of the Global Catalog resources displayed under a product name.

        Args:
            payload (JsonValue): The API search response.
            keys (List[str]): The normalized names the product may be displayed under.
            name (str): The catalogue name, for the logs.

        Returns:
            Optional[datetime]: The earliest creation, `None` when no resource is displayed under the name.
        """
        resources = self._as_object(payload).get(IbmGlobalCatalogField.RESOURCES)
        if not isinstance(resources, list):
            self.logger.warning("The Global Catalog search for %r holds no resource list.", name)
            return None
        matches = [self._as_object(resource) for resource in resources]
        dates = [self._created(match) for match in matches if self._display_key(match) in keys]
        found = [found_date for found_date in dates if found_date is not None]
        if not found:
            self.logger.debug("No Global Catalog resource of %d is displayed as %r.", len(resources), name)
            return None
        return min(found)

    def _search_query(self, text: str) -> Dict[str, str]:
        """Build the query of a Global Catalog search.

        Args:
            text (str): The free text searched.

        Returns:
            Dict[str, str]: The query parameters.
        """
        return {IbmGlobalCatalogParameter.QUERY: text, IbmGlobalCatalogParameter.LIMIT: str(self.SEARCH_LIMIT)}

    async def _created_by_id(self, catalog_id: str) -> Optional[datetime]:
        """Read the creation of the Global Catalog resource of a catalogue offer, by its identifier.

        Args:
            catalog_id (str): The offer identifier.

        Returns:
            Optional[datetime]: The creation, `None` when the Global Catalog does not know the identifier.

        Raises:
            CatalogueFormatError: If the API response is not JSON.
        """
        self.logger.debug("Reading the %s Global Catalog resource %s.", self.name, catalog_id)
        response = await self._fetch_launch_page(f"{self.GLOBAL_CATALOG_URL}/{quote(catalog_id, safe='')}")
        if response is None:
            self.logger.warning("The %s Global Catalog resource %s could not be read.", self.name, catalog_id)
            return None
        return self._resource_created(self._json_body(response), catalog_id)

    async def _created_by_name(self, name: str, alias: Optional[str]) -> Optional[datetime]:
        """Read the earliest creation of the Global Catalog resources displayed under a product name.

        Args:
            name (str): The catalogue name.
            alias (Optional[str]): The name the launch dates catalogue's aliases give it, if any.

        Returns:
            Optional[datetime]: The earliest creation, `None` when no resource is displayed under the name.

        Raises:
            CatalogueFormatError: If the API response is not JSON.
        """
        keys = [self._name_key(candidate) for candidate in (name, alias) if candidate]
        self.logger.debug("Searching the %s Global Catalog for %r (alias %r).", self.name, name, alias)
        response = await self._fetch_launch_page(self.GLOBAL_CATALOG_URL, self._search_query(alias or name))
        if response is None:
            self.logger.warning("The %s Global Catalog search for %r could not be read.", self.name, name)
            return None
        return self._earliest_match(self._json_body(response), keys, name)

    def _created_caveat(self, created: datetime) -> Tuple[datetime, DateCaveat]:
        """Qualify the creation of a Global Catalog resource as a launch.

        Args:
            created (datetime): The creation.

        Returns:
            Tuple[datetime, DateCaveat]: The launch, `WEBSITE_RECORD` on the bulk migration day, else
                `CATALOGUE_ENTRY`.
        """
        migrated = created.date() == self.MIGRATION_DAY
        if migrated:
            self.logger.debug(
                "The %s creation date %s is the catalogue migration day: it dates the record only.",
                self.name,
                created.date().isoformat(),
            )
        return created, DateCaveat.WEBSITE_RECORD if migrated else DateCaveat.CATALOGUE_ENTRY

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the creation of its IBM Global Catalog resource.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when the Global Catalog has no
                resource for the product or cannot be read.

        Raises:
            CatalogueFormatError: If the API response is not JSON.
        """
        key = self._name_key(product.name)
        catalog_id = self.catalog_ids.get(key)
        created = await self._created_by_id(catalog_id) if catalog_id else None
        if created is None:
            created = await self._created_by_name(product.name, self.launch_aliases.get(key))
        if created is None:
            self.logger.debug("No Global Catalog resource dates %r.", product.name)
            return None
        self.logger.debug("%r created in the Global Catalog on %s.", product.name, created.date().isoformat())
        return self._created_caveat(created)

    def _catalog_request(self, url: str, meta: Dict[str, JsonValue]) -> Request:
        """Build a Global Catalog request of the price crawl, counted until it is read.

        Args:
            url (str): The request URL.
            meta (Dict[str, JsonValue]): Its meta: its stage, and the service, plan and region it is about.

        Returns:
            Request: The request.
        """
        self.price_pending += 1
        return self._price_request(url, meta)

    def _charge_unit(self, metric: Dict[str, JsonValue]) -> Tuple[PriceUnit, Decimal]:
        """Normalize the charge unit of a priced metric.

        Args:
            metric (Dict[str, JsonValue]): The metric.

        Returns:
            Tuple[PriceUnit, Decimal]: The unit of the first matching `CHARGE_UNITS` rule (on the charge unit and
                its code), other when none matches, and the charge units a price is per.
        """
        text = f"{metric.get(IbmPriceField.CHARGE_UNIT) or ''} {metric.get(IbmPriceField.CHARGE_UNIT_NAME) or ''}"
        quantity = metric.get(IbmPriceField.CHARGE_UNIT_QUANTITY)
        factor = Decimal(str(quantity)) if isinstance(quantity, (int, float)) and quantity > 0 else Decimal(1)
        for pattern, unit in self.CHARGE_UNITS:
            if pattern.search(text):
                return unit, factor
        self.logger.debug("The IBM charge unit %r has no known unit: kept as other.", text.strip())
        return PriceUnit.OTHER, factor

    def _plan_specs(self, plan_name: str) -> Dict[str, RawValue]:
        """Read the vCPUs and the memory a VPC profile plan names, e.g. `bx2-2x8`.

        Args:
            plan_name (str): The plan name.

        Returns:
            Dict[str, RawValue]: Its `instance_type`, `vcpu` and `memory_gib`, empty for another plan.
        """
        profile = self.PROFILE.search(plan_name)
        if profile is None:
            return {}
        return {"instance_type": plan_name, "vcpu": int(profile[1]), "memory_gib": int(profile[2])}

    def _unpriced_plan(
        self, meta: Dict[str, JsonValue], model: PriceModel, reason: Optional[str]
    ) -> Optional[ServicePrice]:
        """State the price of a plan without pricing document: free, or not public.

        Args:
            meta (Dict[str, JsonValue]): The plan, as a request meta.
            model (PriceModel): Free, or not public.
            reason (Optional[str]): Why it has no price (not public only).

        Returns:
            Optional[ServicePrice]: The price, `None` when malformed.
        """
        region = str(meta.get(self.REGION_META) or "global")
        free = model is PriceModel.FREE
        return self._price_fact(
            {
                "sku_key": f"{meta.get(self.PLAN_META)}@{region}/plan",
                "service": meta.get(self.SERVICE_META),
                "family": meta.get(self.SERVICE_NAME_META),
                "region": region,
                "attributes": {"plan": meta.get(self.PLAN_NAME_META)},
                "unit": PriceUnit.OTHER,
                "unit_raw": self.PLAN_UNIT,
                "price": Decimal(0) if free else None,
                "currency": self.PRICE_CURRENCY if free else None,
                "model": model,
                "reason": None if free else reason,
                "source_url": self.GLOBAL_CATALOG_URL,
                "source_kind": PriceSourceKind.API,
                **self._plan_specs(str(meta.get(self.PLAN_NAME_META) or "")),
            }
        )

    def _pricing_prices(self, data: Dict[str, JsonValue], meta: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of a pricing document, in dollars.

        Args:
            data (Dict[str, JsonValue]): The pricing of a plan or of a deployment.
            meta (Dict[str, JsonValue]): The request meta: the service, the plan and the region.

        Yields:
            ServicePrice: One price per metric and tier (a tier spans up to its `quantity_tier`, the last one
                unbounded), the plan as not public when the pricing has no metric.
        """
        metrics = data.get(IbmPriceField.METRICS)
        location = data.get(IbmPriceField.DEPLOYMENT_LOCATION)
        if not isinstance(metrics, list) or not metrics:
            region = location if isinstance(location, str) and location else str(meta.get(self.REGION_META) or "global")
            unpriced = self._unpriced_plan(
                {**meta, self.REGION_META: region}, PriceModel.NOT_PUBLIC, self.NO_PRICING_REASON
            )
            if unpriced is not None:
                yield unpriced
            return
        effective = data.get(IbmPriceField.EFFECTIVE_FROM)
        effective_day = effective[:10] if isinstance(effective, str) and len(effective) >= 10 else None
        region = location if isinstance(location, str) and location else str(meta.get(self.REGION_META) or "global")
        plan = str(meta.get(self.PLAN_META) or "")
        plan_name = str(meta.get(self.PLAN_NAME_META) or plan)
        for metric in metrics if isinstance(metrics, list) else []:
            if not isinstance(metric, dict):
                continue
            amounts = metric.get(IbmPriceField.AMOUNTS)
            prices: List[JsonValue] = []
            for amount in amounts if isinstance(amounts, list) else []:
                listed = amount.get(IbmPriceField.PRICES) if isinstance(amount, dict) else None
                if isinstance(amount, dict) and amount.get(IbmPriceField.COUNTRY) == self.PRICE_COUNTRY:
                    prices = listed if isinstance(listed, list) else []
                    break
            unit, factor = self._charge_unit(metric)
            metric_key = metric.get(IbmPriceField.METRIC_ID) or metric.get(IbmPriceField.CHARGE_UNIT_NAME)
            previous = Decimal(0)
            tiers = [tier for tier in prices if isinstance(tier, dict)]
            for index, tier in enumerate(tiers):
                bound = tier.get(IbmPriceField.QUANTITY_TIER)
                value = tier.get(IbmPriceField.PRICE)
                if not isinstance(value, (int, float)):
                    continue
                price = Decimal(str(value))
                last = index == len(tiers) - 1
                end = Decimal(str(bound)) if isinstance(bound, (int, float)) and not last else None
                fields: Dict[str, RawValue] = {
                    "sku_key": f"{plan}@{region}/{metric_key}/{index}",
                    "service": meta.get(self.SERVICE_META),
                    "family": meta.get(self.SERVICE_NAME_META),
                    "region": region,
                    "attributes": {
                        "plan": plan_name,
                        IbmPriceField.RESOURCE_DISPLAY_NAME.value: metric.get(IbmPriceField.RESOURCE_DISPLAY_NAME),
                        IbmPriceField.CHARGE_UNIT_NAME.value: metric.get(IbmPriceField.CHARGE_UNIT_NAME),
                        IbmPriceField.TIER_MODEL.value: metric.get(IbmPriceField.TIER_MODEL),
                    },
                    "unit": unit,
                    "unit_raw": str(
                        metric.get(IbmPriceField.CHARGE_UNIT) or metric.get(IbmPriceField.CHARGE_UNIT_NAME)
                    ),
                    "unit_factor": factor,
                    "price": price,
                    "currency": self.PRICE_CURRENCY,
                    "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                    "tier_start": previous if len(tiers) > 1 else Decimal(0),
                    "tier_end": end if len(tiers) > 1 and end is not None and end > previous else None,
                    "effective_from": effective_day,
                    "source_url": self.GLOBAL_CATALOG_URL,
                    "source_kind": PriceSourceKind.API,
                    **self._plan_specs(plan_name),
                }
                if isinstance(bound, (int, float)):
                    previous = Decimal(str(bound))
                fact = self._price_fact(fields)
                if fact is not None:
                    yield fact

    def _blob_text(self, resource: Dict[str, JsonValue], *path: str) -> Optional[str]:
        """Read the display name under a path of a Global Catalog resource.

        Args:
            resource (Dict[str, JsonValue]): The resource.
            *path (str): The fields leading to the display texts.

        Returns:
            Optional[str]: The display name, `None` when missing.
        """
        value: JsonValue = resource
        for field in path:
            value = value.get(field) if isinstance(value, dict) else None
        name = value.get(IbmGlobalCatalogField.DISPLAY_NAME) if isinstance(value, dict) else None
        return name if isinstance(name, str) and name else None

    def _service_requests(self, services: List[JsonValue]) -> Iterator[Request]:
        """Request the plans of the active services of a page (the services of a group included).

        Args:
            services (List[JsonValue]): The services of the page.

        Yields:
            Request: The plans request of each active service.
        """
        for service in services:
            if not isinstance(service, dict):
                continue
            if service.get(IbmPriceField.GROUP) is True:
                children = service.get(IbmPriceField.CHILDREN)
                yield from self._service_requests(children if isinstance(children, list) else [])
                continue
            identifier = service.get(IbmPriceField.ID)
            if not isinstance(identifier, str) or service.get(IbmPriceField.ACTIVE) is False:
                self.logger.debug("The IBM service %s is inactive: not priced.", service.get(IbmPriceField.NAME))
                continue
            display = self._blob_text(service, IbmGlobalCatalogField.OVERVIEW_UI, IbmGlobalCatalogField.ENGLISH)
            yield self._catalog_request(
                self.PLANS_URL.format(id=identifier, offset=0),
                {
                    self.PRICE_STAGE: IbmPriceStage.PLANS.value,
                    self.SERVICE_META: display or identifier,
                    self.SERVICE_NAME_META: service.get(IbmPriceField.NAME),
                    self.SERVICE_ID_META: identifier,
                },
            )

    def _plan_facts(self, data: Dict[str, JsonValue], meta: Dict[str, JsonValue], url: str) -> Iterator[PriceFact]:
        """Read a page of the plans of a service: the next page, then each plan's pricing (or its price).

        Args:
            data (Dict[str, JsonValue]): The page.
            meta (Dict[str, JsonValue]): Its request meta (the service).
            url (str): Its URL.

        Yields:
            PriceFact: The next page request, the pricing request of each plan (even without pricing metadata: a
                plan may be priced by region), and the price of each free or lite plan.
        """
        plans = data.get(IbmPriceField.RESOURCES)
        plans = plans if isinstance(plans, list) else []
        count = data.get(IbmPriceField.COUNT)
        offset = meta.get(self.OFFSET_META)
        offset = offset if isinstance(offset, int) else 0
        if isinstance(count, int) and offset + len(plans) < count and plans:
            yield self._catalog_request(
                self.PLANS_URL.format(id=meta.get(self.SERVICE_ID_META), offset=offset + len(plans)),
                {**meta, self.OFFSET_META: offset + len(plans)},
            )
        for plan in plans:
            if not isinstance(plan, dict) or not isinstance(plan.get(IbmPriceField.ID), str):
                continue
            plan_meta: Dict[str, JsonValue] = {
                **meta,
                self.PLAN_META: plan[IbmPriceField.ID],
                self.PLAN_NAME_META: plan.get(IbmPriceField.NAME),
            }
            metadata = plan.get(IbmPriceField.METADATA)
            pricing = metadata.get(IbmPriceField.PRICING) if isinstance(metadata, dict) else None
            kind = pricing.get(IbmPriceField.TYPE) if isinstance(pricing, dict) else None
            if isinstance(kind, str) and kind.casefold() in tuple(IbmPricingType):
                fact = self._unpriced_plan(plan_meta, PriceModel.FREE, None)
                if fact is not None:
                    yield fact
                continue
            yield self._catalog_request(
                self.PRICING_URL.format(id=plan[IbmPriceField.ID]),
                {**plan_meta, self.PRICE_STAGE: IbmPriceStage.PRICING.value},
            )
        self.logger.debug("IBM plans page %s: %d plans.", url, len(plans))

    def _deployment_requests(self, data: Dict[str, JsonValue], meta: Dict[str, JsonValue]) -> Iterator[PriceFact]:
        """Request the pricing of each deployment (region) of a plan priced by region.

        Args:
            data (Dict[str, JsonValue]): The deployments of the plan.
            meta (Dict[str, JsonValue]): Its request meta (the plan).

        Yields:
            PriceFact: The pricing request of each deployment, or the plan as not public when it has none.
        """
        listed = data.get(IbmPriceField.RESOURCES)
        deployments: List[Dict[str, JsonValue]] = (
            [item for item in listed if isinstance(item, dict)] if isinstance(listed, list) else []
        )
        if not deployments:
            fact = self._unpriced_plan(meta, PriceModel.NOT_PUBLIC, self.NO_PRICING_REASON)
            if fact is not None:
                yield fact
            return
        for deployment in deployments:
            identifier = deployment.get(IbmPriceField.ID)
            if isinstance(identifier, str):
                yield self._catalog_request(
                    self.PRICING_URL.format(id=identifier),
                    {**meta, self.PRICE_STAGE: IbmPriceStage.PRICING.value, self.DEPLOYMENT_META: identifier},
                )

    def _price_settled(self) -> None:
        """Count a Global Catalog request as read, and record the catalog once every request is read."""
        self.price_pending -= 1
        if self.price_pending == 0 and not self.price_failures:
            self._record_price_source(self.GLOBAL_CATALOG_URL, self.price_rows)
            self.logger.info("The IBM Global Catalog is read whole.")

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the first page of the services of the Global Catalog.

        Yields:
            Request: The request of the first page.
        """
        self.price_pending = 0
        self.price_rows = 0
        self.logger.info("Reading the IBM Cloud prices from %s.", self.GLOBAL_CATALOG_URL)
        yield self._catalog_request(
            self.SERVICES_URL.format(offset=0), {self.PRICE_STAGE: IbmPriceStage.SERVICES.value, self.OFFSET_META: 0}
        )

    async def _price_fallback(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Answer a missing pricing: a plan priced by region is read by region, a region without pricing unpriced.

        Args:
            response (Response): The failed request.

        Yields:
            PriceFact: The deployments request of a plan, or the not public price of a deployment.
        """
        meta: Dict[str, JsonValue] = dict(response.meta)
        if response.status != self.MISSING_STATUS or meta.get(self.PRICE_STAGE) != IbmPriceStage.PRICING:
            return
        self._price_settled()
        if isinstance(meta.get(self.DEPLOYMENT_META), str):
            region = str(meta[self.DEPLOYMENT_META]).split(":", 1)[-1]
            fact = self._unpriced_plan(
                {**meta, self.REGION_META: region}, PriceModel.NOT_PUBLIC, self.NO_PRICING_REASON
            )
            if fact is not None:
                self.price_rows += 1
                yield fact
            return
        yield self._catalog_request(
            self.DEPLOYMENTS_URL.format(id=meta.get(self.PLAN_META)),
            {**meta, self.PRICE_STAGE: IbmPriceStage.DEPLOYMENTS.value},
        )

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read a Global Catalog response of the price crawl, by its stage.

        Args:
            response (Response): A services page, a plans page, a pricing or a deployments listing.

        Yields:
            PriceFact: The requests it leads to, and the prices it states.

        Raises:
            CatalogueFormatError: If the response is not a JSON object.
        """
        data = self._json_body(response)
        if not isinstance(data, dict):
            self.price_failures.add(response.url)
            self._price_settled()
            self.logger.error("The IBM Global Catalog response %s is not an object.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the response is not a JSON object")
        meta: Dict[str, JsonValue] = dict(response.meta)
        stage = meta.get(self.PRICE_STAGE)
        facts: Iterator[PriceFact]
        if stage == IbmPriceStage.SERVICES:
            services = data.get(IbmPriceField.RESOURCES)
            services = services if isinstance(services, list) else []
            count, offset = data.get(IbmPriceField.COUNT), meta.get(self.OFFSET_META)
            offset = offset if isinstance(offset, int) else 0
            if isinstance(count, int) and services and offset + len(services) < count:
                yield self._catalog_request(
                    self.SERVICES_URL.format(offset=offset + len(services)),
                    {**meta, self.OFFSET_META: offset + len(services)},
                )
            self.logger.info("IBM services page %d read: %d services of %s.", offset, len(services), count)
            facts = iter(self._service_requests(services))
        elif stage == IbmPriceStage.PLANS:
            facts = self._plan_facts(data, meta, response.url)
        elif stage == IbmPriceStage.DEPLOYMENTS:
            facts = self._deployment_requests(data, meta)
        else:
            facts = iter(self._pricing_prices(data, meta))
        for fact in facts:
            if not isinstance(fact, Request):
                self.price_rows += 1
            yield fact
        self._price_settled()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the catalogue offer identifiers of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if resuming:
            self.logger.info("%s crawl resumed: %d catalogue offer identifiers kept.", self.name, len(self.catalog_ids))
            return
        self.logger.debug("%s crawl started: the catalogue offer identifiers are forgotten.", self.name)
        self.catalog_ids.clear()

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the IBM Cloud catalogue, or of the ibm.com product search.

        Args:
            response (Response): The catalogue page or the product search fragment.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.

        Raises:
            CatalogueFormatError: If the catalogue page has no catalogue data, or no `model.categories` list.
        """
        if urlparse(response.url).netloc == urlparse(self.PRODUCTS_URL).netloc:
            self.logger.debug("Reading the %s product search cards of %s.", self.name, response.url)
            return self._card_products(response)
        self.logger.debug("Reading the %s catalogue offers of %s.", self.name, response.url)
        return self._catalog_products(response)
