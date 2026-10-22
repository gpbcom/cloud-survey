from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.ctyun.enums import (
    ChinaTelecomClass,
    ChinaTelecomClassField,
    ChinaTelecomDataField,
    ChinaTelecomDeliverMode,
    ChinaTelecomMarketplaceMeta,
    ChinaTelecomOfferDisplay,
    ChinaTelecomOfferField,
    ChinaTelecomOfferState,
    ChinaTelecomOwnerField,
    ChinaTelecomResponseField,
    ChinaTelecomSubclass,
)
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class ChinaTelecomMarketplaceCrawler(BaseMarketplaceCrawler):
    """China Telecom Cloud marketplace (天翼云云市场) crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The marketplace website.
        LIST_URL (ClassVar[str]): The offer catalog API, formatted with the offset and the page size.
        CLASS_URL (ClassVar[str]): The class tree API: the classes and their sub-classes.
        PAGE_SIZE (ClassVar[int]): The offers read per page.
        PAGE (ClassVar[ChinaTelecomMarketplaceMeta]): The meta key holding the page number, from 1.
        CLASSES (ClassVar[ChinaTelecomMarketplaceMeta]): The meta key marking the class tree response.
        CLASS_NAMES (ClassVar[Dict[str, str]]): The names of the classes (`ChinaTelecomClass`) of the marketplace
            menu, used when the class tree is not read.
        EXCLUDED_CLASSES (ClassVar[FrozenSet[ChinaTelecomClass]]): The classes which hold no software (courses).
        EXCLUDED_SUBCLASSES (ClassVar[FrozenSet[ChinaTelecomSubclass]]): The sub-classes which hold no software
            (professional services, hardware).
        EXCLUDED_DELIVERIES (ClassVar[FrozenSet[ChinaTelecomDeliverMode]]): The delivery modes of the offers which
            are not software (offline delivered services).
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each delivery mode
            (`ChinaTelecomDeliverMode`).
        CLASS_FIELDS (ClassVar[Tuple[ChinaTelecomOfferField, ...]]): The offer fields of the class then the
            sub-class identifiers.
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The first page of the offer catalog.
        class_names (Dict[str, str]): The name of each class and sub-class, by identifier.

    Notes:
        The marketplace pages read the offers from a JSON catalog API (`offset`, `limit`), giving the `total` and the
        offers (`data.item`): name, note, owner (the store selling the offer), class and sub-class identifiers,
        delivery mode and page link. The class tree API (read first) names the classes and sub-classes, the menu
        class names being used when it is not read. The courses, the offline delivered services, the professional
        services, the hardware and the offers which are not online are skipped. The customer service contact of an
        offer (`offerCseName`) is a person or a team, not its publisher. The website has no `robots.txt`. The names
        and descriptions are in Chinese.
    """

    SITE_URL: ClassVar[str] = "https://market.ctyun.cn"
    LIST_URL: ClassVar[str] = SITE_URL + "/gw/offer/catalog/Query?offset={offset}&limit={limit}"
    CLASS_URL: ClassVar[str] = f"{SITE_URL}/gw/util/class/GetDetail"
    PAGE_SIZE: ClassVar[int] = 50
    PAGE: ClassVar[ChinaTelecomMarketplaceMeta] = ChinaTelecomMarketplaceMeta.PAGE
    CLASSES: ClassVar[ChinaTelecomMarketplaceMeta] = ChinaTelecomMarketplaceMeta.CLASSES
    CLASS_NAMES: ClassVar[Dict[str, str]] = {
        ChinaTelecomClass.APPLICATION: "企业应用",
        ChinaTelecomClass.INDUSTRY: "行业应用",
        ChinaTelecomClass.BASIC: "基础软件",
        ChinaTelecomClass.SITE_BUILD: "建站工具",
        ChinaTelecomClass.DEVOPS: "开发运维",
        ChinaTelecomClass.COURSE: "精品课程",
    }
    EXCLUDED_CLASSES: ClassVar[FrozenSet[ChinaTelecomClass]] = frozenset({ChinaTelecomClass.COURSE})
    EXCLUDED_SUBCLASSES: ClassVar[FrozenSet[ChinaTelecomSubclass]] = frozenset(ChinaTelecomSubclass)
    EXCLUDED_DELIVERIES: ClassVar[FrozenSet[ChinaTelecomDeliverMode]] = frozenset({ChinaTelecomDeliverMode.SERVICE})
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        ChinaTelecomDeliverMode.SAAS: DeliveryMethod.SAAS,
        ChinaTelecomDeliverMode.IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        ChinaTelecomDeliverMode.MIRROR: DeliveryMethod.VIRTUAL_MACHINE,
        ChinaTelecomDeliverMode.API: DeliveryMethod.API,
        ChinaTelecomDeliverMode.LICENSE: DeliveryMethod.DOWNLOAD,
        ChinaTelecomDeliverMode.SOFTWARE: DeliveryMethod.DOWNLOAD,
    }
    CLASS_FIELDS: ClassVar[Tuple[ChinaTelecomOfferField, ...]] = (
        ChinaTelecomOfferField.CLASS,
        ChinaTelecomOfferField.SUBCLASS,
    )

    name = "ctyun-marketplace"
    catalogue_url: ClassVar[str] = LIST_URL.format(offset=0, limit=PAGE_SIZE)

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
        self.class_names: Dict[str, str] = dict(self.CLASS_NAMES)

    ############################
    # Internal Helpers Methods #
    ############################

    def _list_request(self, page: int) -> Request:
        """Build the request of a page of offers.

        Args:
            page (int): The page number, from 1.

        Returns:
            Request: The request, whose page may be empty after the first one.
        """
        meta: Dict[str, JsonValue] = {self.PAGE: page}
        if page > 1:
            meta[self.MAY_BE_EMPTY] = True
        url = self.LIST_URL.format(offset=(page - 1) * self.PAGE_SIZE, limit=self.PAGE_SIZE)
        return self._api_request(url, meta=meta, priority=self.PRIMARY_PRIORITY)

    def _catalogue_request(self) -> Request:
        """Build the request of the first page of offers.

        Returns:
            Request: The request of the first page.
        """
        return self._list_request(1)

    def _data(self, response: Response, field: ChinaTelecomDataField) -> Tuple[Dict[str, JsonValue], List[JsonValue]]:
        """Read the `data` of an API response and its list.

        Args:
            response (Response): The API response.
            field (ChinaTelecomDataField): The field of the list in `data`, e.g. `item`.

        Returns:
            Tuple[Dict[str, JsonValue], List[JsonValue]]: The data and its list.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no such list.
        """
        data = self._as_object(self._as_object(self._json_body(response)).get(ChinaTelecomResponseField.DATA))
        entries = data.get(field)
        if not isinstance(entries, list):
            self.logger.error("The %s API response %s has no `data.%s` list.", self.name, response.url, field)
            raise CatalogueFormatError(self.name, response.url, f"the response has no `data.{field}` list")
        return data, entries

    def _read_classes(self, response: Response) -> None:
        """Read the names of the classes and sub-classes.

        Args:
            response (Response): The class tree.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no class list.
        """
        _, classes = self._data(response, ChinaTelecomDataField.LIST)
        for entry in self._walk_objects(classes):
            identifier = self._as_text(entry.get(ChinaTelecomClassField.SUBCLASS_ID)) or self._as_text(
                entry.get(ChinaTelecomClassField.CLASS_ID)
            )
            label = self._clean_text(self._as_text(entry.get(ChinaTelecomClassField.NAME)))
            if identifier and label:
                self.class_names[identifier] = label
        self.logger.info("%d %s class names read from %s.", len(self.class_names), self.name, response.url)

    def _category_path(self, identifiers: List[str]) -> Optional[MarketplaceCategory]:
        """Build the marketplace category path of an offer, from its class and sub-class.

        Args:
            identifiers (List[str]): The class then the sub-class identifiers of the offer, empty when missing.

        Returns:
            Optional[MarketplaceCategory]: The class then the sub-class names, identified by the deepest named one
                (the sub-class, else the class), `None` when none is named.
        """
        named = [identifier for identifier in identifiers if identifier and self.class_names.get(identifier)]
        if not named:
            self.logger.debug("No %s class name known for the classes %s.", self.name, "/".join(identifiers))
            return None
        return self._category([self.class_names[identifier] for identifier in named], named[-1])

    def _offer_software(self, offer: Dict[str, JsonValue]) -> Optional[MarketplaceSoftware]:
        """Build the software of an offer, unless it is a course, a service, hardware or not online.

        Args:
            offer (Dict[str, JsonValue]): The offer.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` for a skipped (logged) or invalid offer.
        """
        name = self._as_text(offer.get(ChinaTelecomOfferField.NAME))
        identifiers = [self._clean_text(self._as_text(offer.get(field))) for field in self.CLASS_FIELDS]
        delivery = self._clean_text(self._as_text(offer.get(ChinaTelecomOfferField.DELIVER_MODE))).casefold()
        state = self._as_text(offer.get(ChinaTelecomOfferField.STATE))
        if (
            state != ChinaTelecomOfferState.ONLINE
            or offer.get(ChinaTelecomOfferField.DISPLAY) == ChinaTelecomOfferDisplay.HIDDEN
        ):
            self.logger.debug("Skipping the %s offer %r, not online (%s).", self.name, name, state)
            return None
        if identifiers[0] in self.EXCLUDED_CLASSES or identifiers[1] in self.EXCLUDED_SUBCLASSES:
            self.logger.debug("Skipping the %s offer %r, not a software (%s).", self.name, name, "/".join(identifiers))
            return None
        if delivery in self.EXCLUDED_DELIVERIES:
            self.logger.debug(
                "Skipping the %s offer %r, a service (%s).",
                self.name,
                name,
                offer.get(ChinaTelecomOfferField.DELIVER_NAME),
            )
            return None
        link = self._as_text(offer.get(ChinaTelecomOfferField.DETAIL_URL))
        return self._build_software(
            name,
            self._as_text(offer.get(ChinaTelecomOfferField.NOTE)),
            link.rstrip("?").replace("http://", "https://", 1) if link else None,
            self._as_text(self._as_object(offer.get(ChinaTelecomOfferField.OWNER)).get(ChinaTelecomOwnerField.NAME)),
            self.DELIVERIES.get(delivery, DeliveryMethod.OTHER),
            [self.class_names.get(identifier, "") for identifier in identifiers if identifier],
            marketplace_category_paths=[self._category_path(identifiers)],
        )

    def _next_request(self, response: Response) -> Optional[Request]:
        """Build the request of the page after a page of offers, if there are more offers and pages may be read.

        Args:
            response (Response): The page of offers.

        Returns:
            Optional[Request]: The next page request, `None` after the last page or at the page limit.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no offer list.
        """
        data, offers = self._data(response, ChinaTelecomDataField.ITEM)
        total = data.get(ChinaTelecomDataField.TOTAL)
        total = int(total) if isinstance(total, str) and total.isdigit() else total
        page = response.meta.get(self.PAGE)
        number = page if isinstance(page, int) else 1
        if not offers or not isinstance(total, int) or number * self.PAGE_SIZE >= total:
            self.logger.info("Last %s page reached (page %d, %s offers).", self.name, number, total)
            return None
        if not self._within_page_limit(number + 1):
            return None
        self.logger.info("Requesting the %s page %d (%d offers).", self.name, number + 1, total)
        return self._list_request(number + 1)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Reset the class names to those of the menu, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.class_names = dict(self.CLASS_NAMES)

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the class tree, then the first page of offers.

        Yields:
            Request: The class tree request (read first), then the first page request.
        """
        self.logger.debug("Requesting the %s class tree %s.", self.name, self.CLASS_URL)
        yield self._api_request(
            self.CLASS_URL, meta={self.CLASSES: True, self.MAY_BE_EMPTY: True}, priority=self.PRIMARY_PRIORITY + 1
        )
        async for request in super().start_requests():
            yield request

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a page of offers.

        Args:
            response (Response): The page of offers.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page.

        Raises:
            CatalogueFormatError: If the response is not JSON or has no offer list.
        """
        data, offers = self._data(response, ChinaTelecomDataField.ITEM)
        self.logger.info(
            "%s page %s: %d offers (%s in total).",
            self.name,
            response.url,
            len(offers),
            data.get(ChinaTelecomDataField.TOTAL),
        )
        for offer in map(self._as_object, offers):
            if (software := self._offer_software(offer)) is not None:
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Read the class tree, or stream the software of a page of offers then request the next page.

        Args:
            response (Response): The class tree (`CLASSES` meta) or a page of offers.

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, then the next page request.

        Raises:
            CatalogueFormatError: If a response is not JSON or has no list.
            EmptyCatalogueError: If the first page holds no software.
        """
        if response.meta.get(self.CLASSES):
            self._read_classes(response)
            return
        async for item in super().parse(response):
            yield item
        if (request := self._next_request(response)) is not None:
            yield request
