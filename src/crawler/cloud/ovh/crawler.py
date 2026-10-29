from __future__ import annotations

# Standard Library Imports.
import re
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.ovh.enums import (
    OvhBlobField,
    OvhCapacity,
    OvhCatalogField,
    OvhCommercialUnit,
    OvhHostPrefix,
    OvhIntervalUnit,
    OvhMenuKey,
    OvhMenuUniverse,
    OvhNextDataField,
    OvhPriceCatalog,
    OvhPricingField,
)
from crawler.exception import CatalogueFormatError
from models.cloud.enums import PriceModel, PriceSourceKind, PriceTerm, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


class OVHcloudCrawler(BaseCloudCrawler):
    """OVHcloud catalogue crawler.

    Attributes:
        SITEMAP_URL (ClassVar[str]): The sitemap of the website, listing the product pages.
        NOT_PRODUCT_LABEL (ClassVar[re.Pattern[str]]): The menu labels which are links, not products.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The menu links to use cases, guides and documentation.
        SITEMAP_PRODUCT_PAGE (ClassVar[re.Pattern[str]]): The sitemap pages of the product universes.
        SITEMAP_NOT_PRODUCT (ClassVar[re.Pattern[str]]): The sitemap pages which are not product pages.
        LOCALE (ClassVar[re.Pattern[str]]): The locale segment of the website paths, e.g. `/en-gb/`.
        COLUMN_LABEL (ClassVar[re.Pattern[str]]): The labels of the menu columns, e.g. `[Column 1]`, which are not
            categories.
        PRICES_URL (ClassVar[str]): A public order catalog of the French subsidiary (prices in euros).
        PRICE_CATALOGS (ClassVar[Tuple[OvhPriceCatalog, ...]]): The order catalogs read for the prices.
        PRICE_CATALOG (ClassVar[str]): The request meta holding the catalog.
        PRICE_SCALE (ClassVar[Decimal]): The catalog prices are in hundred millionths of the currency.
        ONE_TIME_CAPACITIES (ClassVar[FrozenSet[str]]): The charges made once (installation, upgrade, detachment).
        COMMERCIAL_UNITS (ClassVar[Dict[OvhCommercialUnit, Tuple[PriceUnit, Decimal]]]): The normalized unit of a
            commercial unit, and the normalized units in one (a token price is per token, `price for one unit`:
            the million of its unit is only how the website shows it).
        COMMITMENT_TERMS (ClassVar[Dict[int, PriceTerm]]): The term of a commitment, in months.
        MONTHS_PER_YEAR (ClassVar[int]): The months of a yearly interval.
        DESCRIPTION_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]]): The unit of a consumption
            from its description (`price for one minute`).
        INSTANCE_TYPE_LENGTH (ClassVar[int]): The longest name kept as instance type (else the plan code is).
        ZONE_SUFFIX (ClassVar[re.Pattern[str]]): The zone group a plan code ends with, e.g. `.consumption.3AZ`,
            `.consumption.LZ.AF`, `.consumption.SGP1`.
        QUOTE_REASON (ClassVar[str]): Why a price set at order (`dynamic`) is not public.
        GLOBAL_REGION (ClassVar[str]): The region of a price of every region.
        category_urls (Set[str]): The URL keys of the menu categories, whose pages are not product pages.
        PRODUCT_PAGE_PRICES (ClassVar[bool]): The catalogue product pages are read too, for their price tables.
        PAGE_TEXT_PRICES (ClassVar[bool]): A product page without price table is read for the prices in its text.

    Notes:
        OVHcloud has no catalogue page. The main source is the products menu embedded in every page (Next.js
        data, `props.pageProps.itemsDesktop`): a tree of universes, columns and groups whose leaves are products,
        once the categories, the use cases, the "About us" section and the "coming soon" entries are filtered out.
        A product is filed under the labels of its parent entries (e.g. `AI` then `Inference Solutions`), the
        columns aside, and under those of every entry listing it.
        The sitemap completes it with the product pages missing from the menu, dated by their sitemap last
        modification (`lastmod`). The menu products are undated.
        In price mode it reads the public order catalogs of the French subsidiary (`PRICE_CATALOGS`): every
        pricing of every plan and addon is a price (its payment mode, commitment, phase and, for a consumption,
        its quantity tier, e.g. the first 1,024 GB of traffic free), with the hardware of its technical
        description (or of its product). Each catalog is a source, versioned by its `catalogId`: an unchanged one
        is not read again. The prices are the same in every region, except the zone groups with plans of their
        own, whose code suffix is their region (`3az`, `lz.eu`, `apac`, `sgp1`).
    """

    SITEMAP_URL: ClassVar[str] = "https://www.ovhcloud.com/en/www.ovhcloud.com_en_sitemap.xml"
    NOT_PRODUCT_LABEL: ClassVar[re.Pattern[str]] = re.compile(
        r"^(all |compare |see the |search for |renew |transfer |how do i|create |host your|what is )", re.IGNORECASE
    )
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(
        r"/use-cases/|/uc-|use-cases-|docs\.ovhcloud\.com|/learn/|/architecture-center/", re.IGNORECASE
    )
    SITEMAP_PRODUCT_PAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"^https://www\.ovhcloud\.com/[a-z]{2}(-[a-z]{2})?/(public-cloud|hosted-private-cloud|storage-solutions|"
        r"network|security|identity-security-operations|emails|public-vcf-aas)/[^?#]+$"
    )
    SITEMAP_NOT_PRODUCT: ClassVar[re.Pattern[str]] = re.compile(
        r"uc-|use-case|price|pricing|configurator|faq|free-|journey-|what-|why-|how-|interview|options|classes|"
        r"config/|definition|choosing|technical-overview|services-included|safety|security-features|partnership|"
        r"migration|create-|comparison|compare|regions|availability|architecture|management-interfaces|"
        r"project-management|discover|partners|applications-services",
        re.IGNORECASE,
    )
    LOCALE: ClassVar[re.Pattern[str]] = re.compile(r"^/[a-z]{2}(-[a-z]{2})?(?=/)")
    COLUMN_LABEL: ClassVar[re.Pattern[str]] = re.compile(r"^\[[^\]]*\]$")

    PRODUCT_PAGE_PRICES: ClassVar[bool] = True
    PAGE_TEXT_PRICES: ClassVar[bool] = True
    name = "ovhcloud"
    catalogue_url: ClassVar[str] = "https://www.ovhcloud.com/en-gb/public-cloud/"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("OVHcloud ",)
    PRICES_URL: ClassVar[str] = "https://eu.api.ovh.com/1.0/order/catalog/public/{catalog}?ovhSubsidiary=FR"
    PRICE_CATALOGS: ClassVar[Tuple[OvhPriceCatalog, ...]] = tuple(OvhPriceCatalog)
    PRICE_CATALOG: ClassVar[str] = "price_catalog"
    PRICE_SCALE: ClassVar[Decimal] = Decimal(100_000_000)
    ONE_TIME_CAPACITIES: ClassVar[FrozenSet[str]] = frozenset(
        {OvhCapacity.INSTALLATION, OvhCapacity.UPGRADE, OvhCapacity.DETACH}
    )
    COMMERCIAL_UNITS: ClassVar[Dict[OvhCommercialUnit, Tuple[PriceUnit, Decimal]]] = {
        OvhCommercialUnit.HOUR: (PriceUnit.HOUR, Decimal(1)),
        OvhCommercialUnit.NODE_HOUR: (PriceUnit.HOUR, Decimal(1)),
        OvhCommercialUnit.GIB_HOUR: (PriceUnit.GIB_HOUR, Decimal(1)),
        OvhCommercialUnit.GIB: (PriceUnit.GIB, Decimal(1)),
        OvhCommercialUnit.TOKENS_INPUT: (PriceUnit.TOKEN, Decimal(1)),
        OvhCommercialUnit.TOKENS_OUTPUT: (PriceUnit.TOKEN, Decimal(1)),
        OvhCommercialUnit.VM_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        OvhCommercialUnit.MONTH_PER_GIB: (PriceUnit.GIB_MONTH, Decimal(1)),
        OvhCommercialUnit.GIB_MONTH: (PriceUnit.GIB_MONTH, Decimal(1)),
        OvhCommercialUnit.KEY_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        OvhCommercialUnit.HOUR_PER_VCORE: (PriceUnit.VCPU_HOUR, Decimal(1)),
        OvhCommercialUnit.DPU_HOUR: (PriceUnit.UNIT_HOUR, Decimal(1)),
        OvhCommercialUnit.CLUSTER_HOUR: (PriceUnit.HOUR, Decimal(1)),
        OvhCommercialUnit.VCPU_HOUR: (PriceUnit.VCPU_HOUR, Decimal(1)),
        OvhCommercialUnit.VCPU_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        OvhCommercialUnit.INSTANCE_MONTH: (PriceUnit.MONTH, Decimal(1)),
        OvhCommercialUnit.MONTH_PER_VCORE: (PriceUnit.UNIT_MONTH, Decimal(1)),
        OvhCommercialUnit.TIB: (PriceUnit.GIB, Decimal(1024)),
        OvhCommercialUnit.VCORE_HOUR: (PriceUnit.VCPU_HOUR, Decimal(1)),
        OvhCommercialUnit.HOUR_PER_GIB: (PriceUnit.GIB_HOUR, Decimal(1)),
        OvhCommercialUnit.HOST_MONTH: (PriceUnit.MONTH, Decimal(1)),
        OvhCommercialUnit.SECRET_VERSION_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
        OvhCommercialUnit.UNIT_MONTH: (PriceUnit.UNIT_MONTH, Decimal(1)),
    }
    COMMITMENT_TERMS: ClassVar[Dict[int, PriceTerm]] = {
        1: PriceTerm.MONTH,
        3: PriceTerm.THREE_MONTHS,
        6: PriceTerm.SIX_MONTHS,
        12: PriceTerm.ONE_YEAR,
        24: PriceTerm.TWO_YEARS,
        36: PriceTerm.THREE_YEARS,
        48: PriceTerm.FOUR_YEARS,
        60: PriceTerm.FIVE_YEARS,
    }
    MONTHS_PER_YEAR: ClassVar[int] = 12
    DESCRIPTION_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit], ...]] = (
        (re.compile(r"\bminute", re.IGNORECASE), PriceUnit.MINUTE),
        (re.compile(r"\bhour", re.IGNORECASE), PriceUnit.HOUR),
        (re.compile(r"\bunit\b", re.IGNORECASE), PriceUnit.UNIT),
    )
    INSTANCE_TYPE_LENGTH: ClassVar[int] = 120
    ZONE_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\.(?:consumption|postpaid)\.([A-Za-z0-9][A-Za-z0-9.-]*)$")
    QUOTE_REASON: ClassVar[str] = "The price is set when ordered (a premium domain name)."
    GLOBAL_REGION: ClassVar[str] = "global"

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.category_urls: Set[str] = set()

    ############################
    # Internal Helpers Methods #
    ############################

    def _url_key(self, url: str) -> str:
        """Compare the website pages whatever their locale (`/en/` and `/en-gb/` pages are the same product).

        Args:
            url (str): The absolute product URL.

        Returns:
            str: The generic URL key, without the locale segment.
        """
        link = urlparse(url.casefold())
        return f"{link.netloc.removeprefix(OvhHostPrefix.WWW)}{self.LOCALE.sub('', link.path).rstrip('/')}"

    def _menu(self, response: Response) -> Dict[str, JsonValue]:
        """Read the products menu embedded in a page.

        Args:
            response (Response): A page of the website.

        Returns:
            Dict[str, JsonValue]: The menu, by universe.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        data = self._next_data(response)
        page_props = self._as_object(self._as_object(data.get(OvhNextDataField.PROPS)).get(OvhNextDataField.PAGE_PROPS))
        menu = self._as_object(page_props.get(OvhNextDataField.ITEMS_DESKTOP))
        if not menu:
            self.logger.error("The %s page %s has no products menu.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the products menu (`itemsDesktop`) is missing")
        self.logger.debug("Products menu of %s found, with the universes %s.", response.url, ", ".join(menu))
        return menu

    def _categories(self, menu: Dict[str, JsonValue]) -> Tuple[Set[str], Set[str]]:
        """Get the labels and links of the menu categories: the top level entries holding products.

        Args:
            menu (Dict[str, JsonValue]): The menu, by universe.

        Returns:
            Tuple[Set[str], Set[str]]: The category labels (case-insensitive) and URL keys.
        """
        labels: Set[str] = set()
        links: Set[str] = set()
        for node in self._walk_objects(menu):
            if node.get(OvhMenuKey.LEVEL) == 1 and node.get(OvhMenuKey.CHILDREN):
                labels.add(self._clean_text(self._as_text(node.get(OvhMenuKey.LABEL))).casefold())
                if link := self._as_text(node.get(OvhMenuKey.LINK)):
                    links.add(self._url_key(link))
        return labels, links

    def _leaves(
        self, value: JsonValue, top: Optional[Dict[str, JsonValue]] = None, path: Tuple[str, ...] = ()
    ) -> Iterator[Tuple[Dict[str, JsonValue], Dict[str, JsonValue], Tuple[str, ...]]]:
        """Walk the menu entries without children, with their top level entry and the labels of their parents.

        Args:
            value (JsonValue): A menu (sub)tree.
            top (Optional[Dict[str, JsonValue]]): The top level entry of the subtree, if already reached.
            path (Tuple[str, ...]): The labels of the entries above the subtree, top level first.

        Yields:
            Tuple[Dict[str, JsonValue], Dict[str, JsonValue], Tuple[str, ...]]: Each leaf, its top level entry and
                the labels of its parents, top level first.
        """
        if isinstance(value, list):
            for child in value:
                yield from self._leaves(child, top, path)
            return
        if not isinstance(value, dict):
            return
        if OvhMenuKey.LEVEL not in value:
            for child in value.values():
                yield from self._leaves(child, top, path)
            return
        top = top if top is not None else value
        children = value.get(OvhMenuKey.CHILDREN)
        if children:
            yield from self._leaves(
                children, top, (*path, self._clean_text(self._as_text(value.get(OvhMenuKey.LABEL))))
            )
        else:
            yield value, top, path

    def _leaf_categories(self, labels: Sequence[str], name: Optional[str]) -> List[str]:
        """Get the categories of a product from the labels of the entries listing it, without the columns.

        Args:
            labels (Sequence[str]): The labels of the parents of its leaves, top level first.
            name (Optional[str]): The product name, which is not one of its categories.

        Returns:
            List[str]: The category labels, in order, e.g. `["AI", "Inference Solutions"]`, without blank, column
                or repeated (case-insensitive) labels.
        """
        categories: List[str] = []
        known = {self._clean_text(name).casefold()}
        for label in labels:
            if label and not self.COLUMN_LABEL.match(label) and label.casefold() not in known:
                categories.append(label)
                known.add(label.casefold())
        return categories

    def _is_product_leaf(
        self,
        leaf: Dict[str, JsonValue],
        top: Dict[str, JsonValue],
        universe: str,
        categories: Tuple[Set[str], Set[str]],
    ) -> bool:
        """Tell whether a menu leaf is a product.

        Args:
            leaf (Dict[str, JsonValue]): The menu leaf.
            top (Dict[str, JsonValue]): Its top level entry.
            universe (str): Its menu universe, e.g. `public-cloud`.
            categories (Tuple[Set[str], Set[str]]): The category labels and URL keys of the menu.

        Returns:
            bool: Whether the leaf is a product, not a category,
                a use case, an "About us" page or a coming entry.
        """
        label = self._clean_text(self._as_text(leaf.get(OvhMenuKey.LABEL)))
        link = self._as_text(leaf.get(OvhMenuKey.LINK)) or ""
        reasons = {
            "about us": "/about-us" in (self._as_text(top.get(OvhMenuKey.LINK)) or ""),
            "coming soon": leaf.get(OvhMenuKey.COMING_SOON) is True,
            "link label": bool(self.NOT_PRODUCT_LABEL.search(label)),
            "use case or documentation": bool(self.NOT_PRODUCT_LINK.search(link)),
            "category": label.casefold() in categories[0]
            or (universe == OvhMenuUniverse.HOME and bool(link) and self._url_key(link) in categories[1]),
        }
        if failed := [reason for reason, matched in reasons.items() if matched]:
            self.logger.debug("Skipping the menu entry %r (%s).", label, ", ".join(failed))
            return False
        return True

    def _menu_entries(self, response: Response) -> List[Tuple[Dict[str, JsonValue], List[str]]]:
        """Gather the product leaves of the menu with all their categories, a product being listed in several ones.

        Args:
            response (Response): A page of the website.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str]]]: The first leaf of each product, by order of appearance,
                and the categories of all its leaves.

        Raises:
            CatalogueFormatError: If the page has no products menu.

        Notes:
            The leaves of a product are matched by name or by link, as the streamed products are.
        """
        menu = self._menu(response)
        categories = self._categories(menu)
        self.category_urls.update(categories[1])
        entries: List[Tuple[Dict[str, JsonValue], List[str]]] = []
        positions: Dict[str, int] = {}
        for universe, tree in menu.items():
            for leaf, top, path in self._leaves(tree):
                description = self._as_text(leaf.get(OvhMenuKey.DESCRIPTION))
                if not (description or "").strip() or not self._is_product_leaf(leaf, top, universe, categories):
                    continue
                link = self._as_text(leaf.get(OvhMenuKey.LINK))
                keys = [f"name:{self._name_key(self._as_text(leaf.get(OvhMenuKey.LABEL)) or '')}"]
                keys += [f"url:{self._url_key(link)}"] if link and link.strip() else []
                position = next((positions[key] for key in keys if key in positions), None)
                if position is None:
                    position = len(entries)
                    entries.append((leaf, []))
                    self.logger.debug("Menu product %r found.", leaf.get(OvhMenuKey.LABEL))
                else:
                    self.logger.debug(
                        "Menu product %r listed again, its categories are merged.", leaf.get(OvhMenuKey.LABEL)
                    )
                first, known = entries[position]
                entries[position] = (
                    first,
                    self._leaf_categories([*known, *path], self._as_text(first.get(OvhMenuKey.LABEL))),
                )
                positions.update(dict.fromkeys(keys, position))
        return entries

    def _menu_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the menu: the leaves with a description, not filtered out, with their categories.

        Args:
            response (Response): A page of the website.

        Yields:
            Iterator[CloudProduct]: Each valid product of the menu, once.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        count = 0
        for leaf, categories in self._menu_entries(response):
            label, link = self._as_text(leaf.get(OvhMenuKey.LABEL)), self._as_text(leaf.get(OvhMenuKey.LINK))
            description = self._as_text(leaf.get(OvhMenuKey.DESCRIPTION))
            if product := self._build_product(label, description, link, categories=categories):
                count += 1
                yield product
        if count:
            self.logger.info("%d %s products read from the menu of %s.", count, self.name, response.url)
        else:
            self.logger.warning("No %s product in the menu of %s.", self.name, response.url)

    def _sitemap_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the sitemap which were not found in the menu, with their last modification.

        Args:
            response (Response): The sitemap.

        Returns:
            List[Request]: The product page requests.

        Raises:
            CatalogueFormatError: If the sitemap lists no page.
        """
        entries = self._sitemap_entries(response)
        pages = [
            url
            for url in entries
            if self.SITEMAP_PRODUCT_PAGE.match(url)
            and not self.SITEMAP_NOT_PRODUCT.search(url)
            and self._url_key(url) not in self.category_urls
        ]
        requests = [
            request for url in pages if (request := self._product_page_request(url, updated=entries[url])) is not None
        ]
        self.logger.info(
            "%d %s product pages to check in the sitemap (%d pages).", len(requests), self.name, len(entries)
        )
        return requests

    def _blob(self, value: JsonValue, *path: str) -> JsonValue:
        """Follow a path of object fields in a catalog description.

        Args:
            value (JsonValue): The description.
            *path (str): The fields, outermost first.

        Returns:
            JsonValue: The value at the end of the path, `None` when a field is missing.
        """
        for field in path:
            if not isinstance(value, dict):
                return None
            value = value.get(field)
        return value

    def _offer_specs(self, technical: JsonValue) -> Tuple[Dict[str, RawValue], Dict[str, JsonValue]]:
        """Read the hardware of a plan or an addon from its technical description.

        Args:
            technical (JsonValue): Its technical description (or that of its product).

        Returns:
            Tuple[Dict[str, RawValue], Dict[str, JsonValue]]: Its `vcpu` (threads, else cores, times the
                processors), `memory_gib`, `storage_gib` (the disks) and `os`, those stated, and its GPUs as
                attributes.
        """
        specs: Dict[str, RawValue] = {}
        attributes: Dict[str, JsonValue] = {}
        cpu = self._blob(technical, OvhBlobField.CPU) or self._blob(technical, OvhBlobField.SERVER, OvhBlobField.CPU)
        if isinstance(cpu, dict):
            count = cpu.get(OvhBlobField.THREADS) or cpu.get(OvhBlobField.CORES)
            number = cpu.get(OvhBlobField.NUMBER)
            if isinstance(count, int) and count > 0:
                specs["vcpu"] = count * (number if isinstance(number, int) and number > 0 else 1)
        memory = self._blob(technical, OvhBlobField.MEMORY, OvhBlobField.SIZE)
        if isinstance(memory, (int, float)) and memory > 0:
            specs["memory_gib"] = Decimal(str(memory))
        disks = self._blob(technical, OvhBlobField.STORAGE, OvhBlobField.DISKS)
        total = Decimal(0)
        for disk in disks if isinstance(disks, list) else []:
            capacity = self._blob(disk, OvhBlobField.CAPACITY)
            number = self._blob(disk, OvhBlobField.NUMBER)
            if isinstance(capacity, (int, float)) and capacity > 0:
                total += Decimal(str(capacity)) * (number if isinstance(number, int) and number > 0 else 1)
        if total > 0:
            specs["storage_gib"] = total
        family = self._blob(technical, OvhBlobField.OS, OvhBlobField.FAMILY)
        if isinstance(family, str) and family:
            specs["os"] = family
        gpu = self._blob(technical, OvhBlobField.GPU)
        if isinstance(gpu, dict):
            attributes.update({f"gpu_{key}": value for key, value in gpu.items() if isinstance(value, (str, int))})
        return specs, attributes

    def _pricing_unit(self, commercial: JsonValue, pricing: Dict[str, JsonValue]) -> Tuple[PriceUnit, Decimal, str]:
        """Normalize what a price of the catalog is per.

        Args:
            commercial (JsonValue): The unit its commercial description writes, e.g. `GiB*h`, if any.
            pricing (Dict[str, JsonValue]): The price.

        Returns:
            Tuple[PriceUnit, Decimal, str]: The unit, the normalized units in one, and the unit as written: a
                one-time charge (installation, upgrade) first, then the commercial unit, then the interval (12
                months are a year), then the description of a consumption (`price for one minute`).
        """
        raw_capacities = pricing.get(OvhPricingField.CAPACITIES)
        capacities: Set[str] = (
            {str(capacity) for capacity in raw_capacities} if isinstance(raw_capacities, list) else set()
        )
        raw_interval = pricing.get(OvhPricingField.INTERVAL)
        interval = raw_interval if isinstance(raw_interval, int) else 0
        unit_name = str(pricing.get(OvhPricingField.INTERVAL_UNIT))
        written = f"{interval} {unit_name}" if interval else "+".join(sorted(capacities))
        if capacities and capacities <= self.ONE_TIME_CAPACITIES:
            return PriceUnit.ONE_TIME, Decimal(1), written
        if isinstance(commercial, str):
            try:
                unit, factor = self.COMMERCIAL_UNITS[OvhCommercialUnit(commercial)]
                return unit, factor, commercial
            except ValueError:
                self.logger.warning("Unknown OVHcloud price unit %r: the interval is used.", commercial)
        if unit_name == OvhIntervalUnit.HOUR and interval:
            return PriceUnit.HOUR, Decimal(interval), written
        if unit_name == OvhIntervalUnit.MONTH and interval == self.MONTHS_PER_YEAR:
            return PriceUnit.YEAR, Decimal(1), written
        if unit_name == OvhIntervalUnit.MONTH and interval:
            return PriceUnit.MONTH, Decimal(interval), written
        description = str(pricing.get(OvhPricingField.DESCRIPTION) or "")
        for pattern, unit in self.DESCRIPTION_UNITS:
            if pattern.search(description):
                return unit, Decimal(1), description
        self.logger.debug("The unit of an OVHcloud price is unknown (%s).", description or written)
        return PriceUnit.OTHER, Decimal(1), description or written

    def _pricing_price(
        self,
        catalog: str,
        kind: str,
        code: str,
        name: str,
        service: str,
        pricing: Dict[str, JsonValue],
        specs: Dict[str, RawValue],
        attributes: Dict[str, JsonValue],
        currency: Optional[str],
        commercial: JsonValue,
    ) -> Iterator[ServicePrice]:
        """Read one price of a plan or an addon.

        Args:
            catalog (str): The catalog.
            kind (str): `plans` or `addons`.
            code (str): The code of the plan or the addon.
            name (str): Its name.
            service (str): The service it belongs to (its product description).
            pricing (Dict[str, JsonValue]): The price.
            specs (Dict[str, RawValue]): Its hardware.
            attributes (Dict[str, JsonValue]): Its other attributes.
            currency (Optional[str]): The currency of the catalog.
            commercial (JsonValue): Its commercial description.

        Yields:
            ServicePrice: The price, when valid: a consumption tier keeps its quantities, a price set at order (a
                premium domain, `dynamic`) is a quote.
        """
        raw = pricing.get(OvhPricingField.PRICE)
        if not isinstance(raw, int):
            self.logger.debug("An OVHcloud price of %s has no amount: skipped.", code)
            return
        price = Decimal(raw) / self.PRICE_SCALE
        unit, factor, written = self._pricing_unit(
            self._blob(commercial, OvhBlobField.PRICE, OvhBlobField.UNIT), pricing
        )
        commitment = pricing.get(OvhPricingField.COMMITMENT)
        commitment = commitment if isinstance(commitment, int) else 0
        capacities = pricing.get(OvhPricingField.CAPACITIES)
        capacities_text = "+".join(str(capacity) for capacity in capacities) if isinstance(capacities, list) else ""
        quantity = pricing.get(OvhPricingField.QUANTITY)
        least = self._blob(quantity, OvhPricingField.MIN)
        most = self._blob(quantity, OvhPricingField.MAX)
        least = least if isinstance(least, int) else 1
        mode = str(pricing.get(OvhPricingField.MODE) or "")
        zone = self.ZONE_SUFFIX.search(code)
        key = "/".join(
            (
                catalog,
                kind,
                code,
                mode,
                capacities_text,
                f"{pricing.get(OvhPricingField.INTERVAL)}{pricing.get(OvhPricingField.INTERVAL_UNIT)}",
                str(commitment),
                str(pricing.get(OvhPricingField.PHASE)),
                str(least),
            )
        )
        fields: Dict[str, RawValue] = {
            "sku_key": key,
            "service": service,
            "family": catalog,
            "region": zone[1].lower() if zone else self.GLOBAL_REGION,
            "attributes": {
                **attributes,
                "plan_code": code,
                OvhPricingField.MODE.value: mode,
                OvhPricingField.CAPACITIES.value: capacities_text,
                OvhPricingField.TYPE.value: pricing.get(OvhPricingField.TYPE),
            },
            "unit": unit,
            "unit_raw": written,
            "unit_factor": factor,
            "price": price,
            "currency": currency,
            "model": (PriceModel.FREE if price == 0 else PriceModel.COMMITMENT if commitment else PriceModel.ON_DEMAND),
            "term": self.COMMITMENT_TERMS.get(commitment, PriceTerm.NONE),
            "source_url": self.PRICES_URL.format(catalog=catalog),
            "source_kind": PriceSourceKind.API,
            **specs,
        }
        if "vcpu" in specs:
            fields["instance_type"] = name if len(name) <= self.INSTANCE_TYPE_LENGTH else code
        if OvhCapacity.DYNAMIC in capacities_text.split("+"):
            fields.update({"price": None, "currency": None, "model": PriceModel.QUOTE, "reason": self.QUOTE_REASON})
        if pricing.get(OvhPricingField.TYPE) == OvhCapacity.CONSUMPTION:
            fields["tier_start"] = max(least - 1, 0)
            fields["tier_end"] = most if isinstance(most, int) and most > least - 1 else None
        fact = self._price_fact(fields)
        if fact is not None:
            yield fact

    def _offer_prices(
        self,
        catalog: str,
        kind: str,
        offer: Dict[str, JsonValue],
        products: Dict[str, Dict[str, JsonValue]],
        currency: Optional[str],
    ) -> Iterator[ServicePrice]:
        """Read the prices of a plan or an addon of a catalog.

        Args:
            catalog (str): The catalog, e.g. `cloud`.
            kind (str): `plans` or `addons`.
            offer (Dict[str, JsonValue]): The plan or the addon.
            products (Dict[str, Dict[str, JsonValue]]): The products of the catalog, by name.
            currency (Optional[str]): The currency of the catalog.

        Yields:
            ServicePrice: One price per pricing of the offer (its modes, commitments, phases and tiers).
        """
        code = offer.get(OvhCatalogField.PLAN_CODE)
        pricings = offer.get(OvhCatalogField.PRICINGS)
        if not isinstance(code, str) or not isinstance(pricings, list):
            self.logger.debug("An OVHcloud %s %s has no code or no prices: skipped.", catalog, kind)
            return
        product_name = offer.get(OvhCatalogField.PRODUCT)
        product = products.get(product_name, {}) if isinstance(product_name, str) else {}
        blobs = offer.get(OvhCatalogField.BLOBS)
        technical = self._blob(blobs, OvhBlobField.TECHNICAL) or self._blob(
            product.get(OvhCatalogField.BLOBS), OvhBlobField.TECHNICAL
        )
        specs, attributes = self._offer_specs(technical)
        commercial = self._blob(blobs, OvhBlobField.COMMERCIAL)
        for field in (OvhBlobField.BRICK, OvhBlobField.BRICK_SUBTYPE):
            value = self._blob(commercial, field)
            if isinstance(value, str) and value:
                attributes[field] = value
        service = product.get(OvhCatalogField.DESCRIPTION) or product_name or catalog
        name = offer.get(OvhCatalogField.INVOICE_NAME) or code
        for pricing in pricings:
            if not isinstance(pricing, dict):
                continue
            yield from self._pricing_price(
                catalog, kind, code, str(name), str(service), pricing, specs, attributes, currency, commercial
            )

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the public order catalogs.

        Yields:
            Request: The request of each catalog.
        """
        self.logger.info("Reading the OVHcloud prices from %d order catalogs.", len(self.PRICE_CATALOGS))
        for catalog in self.PRICE_CATALOGS:
            yield self._price_request(
                self.PRICES_URL.format(catalog=catalog.value), {self.PRICE_CATALOG: catalog.value}
            )

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the prices of a public order catalog, unless its version is the one last read.

        Args:
            response (Response): The catalog.

        Yields:
            PriceFact: The prices of its plans and addons.

        Raises:
            CatalogueFormatError: If the catalog is not a JSON object with plans.
        """
        catalog = str(response.meta.get(self.PRICE_CATALOG) or OvhPriceCatalog.CLOUD.value)
        url = self.PRICES_URL.format(catalog=catalog)
        data = self._json_body(response)
        if not isinstance(data, dict) or not isinstance(data.get(OvhCatalogField.PLANS), list):
            self.logger.error("The OVHcloud catalog %s has no plans.", catalog)
            raise CatalogueFormatError(self.name, response.url, "the catalog has no plans")
        version = data.get(OvhCatalogField.CATALOG_ID)
        version = str(version) if isinstance(version, int) else None
        if self._price_unchanged(url, version=version):
            return
        currency = self._blob(data, OvhCatalogField.LOCALE, OvhCatalogField.CURRENCY_CODE)
        products_list = data.get(OvhCatalogField.PRODUCTS)
        products = {
            str(product[OvhCatalogField.NAME]): product
            for product in (products_list if isinstance(products_list, list) else [])
            if isinstance(product, dict) and isinstance(product.get(OvhCatalogField.NAME), str)
        }
        found = 0
        for kind in (OvhCatalogField.PLANS, OvhCatalogField.ADDONS):
            offers = data.get(kind)
            for offer in offers if isinstance(offers, list) else []:
                if not isinstance(offer, dict):
                    continue
                for fact in self._offer_prices(
                    catalog, kind.value, offer, products, currency if isinstance(currency, str) else None
                ):
                    found += 1
                    yield fact
        self._record_price_source(url, found, version=version)
        self.logger.info("The OVHcloud catalog %s (version %s) is read: %d prices.", catalog, version, found)

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the menu embedded in a page.

        Args:
            response (Response): A page of the website.

        Returns:
            Iterator[CloudProduct]: The valid products of the menu.

        Raises:
            CatalogueFormatError: If the page has no products menu.
        """
        self.logger.debug("Reading the %s products menu of %s.", self.name, response.url)
        return self._menu_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the menu products, request the sitemap product pages, or stream a sitemap product page.

        The product pages are read by the base crawler.

        Args:
            response (Response): The menu page, the sitemap or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each product not streamed yet, or the product page requests.

        Raises:
            CatalogueFormatError: If a page has no products menu,
                or if the sitemap lists no page.
        """
        if response.url == self.SITEMAP_URL and self.PAGE_DATES not in response.meta:
            self.logger.debug("Reading the %s sitemap %s.", self.name, response.url)
            for request in self._sitemap_requests(response):
                yield request
            return
        async for item in super().parse(response):
            yield item
