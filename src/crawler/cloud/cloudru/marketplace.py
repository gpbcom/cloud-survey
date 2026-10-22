from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.cloudru.enums import (
    CloudRuCardField,
    CloudRuMarketplaceCategory,
    CloudRuProductType,
    CloudRuRequestMeta,
)
from crawler.cloud.next_flight_data import NextFlightData
from crawler.exception import CatalogueFormatError, EmptyCatalogueError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class CloudRuMarketplaceCrawler(BaseMarketplaceCrawler):
    """Cloud.ru marketplace crawler.

    Attributes:
        SITE_URL (ClassVar[str]): The website root, the links being relative to it.
        PRODUCT_URL (ClassVar[str]): The marketplace page of a software, filled with its slug.
        CARD (ClassVar[CloudRuRequestMeta]): The meta key of a software page request, holding the listing card of the
            software.
        TAXONOMY (ClassVar[CloudRuRequestMeta]): The meta key of a software page request, holding the labels of the
            categories of its card, by slug.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace product type,
            keyed by `CloudRuProductType` members.
        CATEGORY_DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of the software without
            product type, by the slug of their marketplace category (`CloudRuMarketplaceCategory` members).
        name (str): The crawler name.
        catalogue_url (ClassVar[str]): The marketplace home page, listing every software.
        flight (NextFlightData): The reader of the Next.js flight data of the pages.

    Notes:
        The https://cloud.ru/marketplace page (slow, read over HTTP) is rendered by the Next.js App Router: its
        flight data (see `NextFlightData`) holds the whole marketplace in an object with a `categories` list (the
        taxonomy, e.g. `MCP-серверы` for `mcp-servers`) and a `cards` list, with no pagination. Each card gives the
        software name (`displayName`), description (`previewText`), category slugs (`categories`), product types
        (`productTypes`, e.g. `vm-image`) and, for the AI agents and MCP servers, their selections (`selection`,
        e.g. `Бизнес`, a sub-category of their category) and their page in the console (`redirectUrl`). The
        software published by Cloud.ru partners have a marketplace page instead (`/marketplace/products/<slug>`):
        it is requested (`CARD` meta), for its licence owner (`license.owner`, the publisher, often blank) and the
        dates of its marketplace record (`createdAt`, the listing, and `updatedAt`, any edit of the record). The
        cards give no publisher. The texts are kept as written (in Russian). The category paths are the category,
        or the category then each selection, identified by the category slug or the selection.
    """

    SITE_URL: ClassVar[str] = "https://cloud.ru/"
    PRODUCT_URL: ClassVar[str] = "https://cloud.ru/marketplace/products/{slug}"
    CARD: ClassVar[CloudRuRequestMeta] = CloudRuRequestMeta.CARD
    TAXONOMY: ClassVar[CloudRuRequestMeta] = CloudRuRequestMeta.TAXONOMY
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        CloudRuProductType.VM_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        CloudRuProductType.DOCKER_IMAGE: DeliveryMethod.CONTAINER,
        CloudRuProductType.ADDONS: DeliveryMethod.KUBERNETES,
    }
    CATEGORY_DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        CloudRuMarketplaceCategory.MCP_SERVERS: DeliveryMethod.API,
        CloudRuMarketplaceCategory.AI_AGENTS: DeliveryMethod.SAAS,
    }

    name = "cloudru-marketplace"
    catalogue_url: ClassVar[str] = "https://cloud.ru/marketplace"

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
        self.flight = NextFlightData(self.name, self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _listing(self, response: Response) -> Tuple[List[Dict[str, JsonValue]], Dict[str, str]]:
        """Read the cards and the taxonomy of the marketplace held by the flight data of the page.

        Args:
            response (Response): The marketplace page.

        Returns:
            Tuple[List[Dict[str, JsonValue]], Dict[str, str]]: The cards, in order, and the category labels by slug.

        Raises:
            CatalogueFormatError: If the flight data holds no marketplace listing.
            EmptyCatalogueError: If the listing has no card.
        """
        listing = self.flight.find(self.flight.documents(response), CloudRuCardField.CARDS, CloudRuCardField.CATEGORIES)
        if listing is None:
            self.logger.error("The %s page %s holds no marketplace listing.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the flight data holds no marketplace listing")
        listed, categories = listing.get(CloudRuCardField.CARDS), listing.get(CloudRuCardField.CATEGORIES)
        cards = [card for card in listed if isinstance(card, dict)] if isinstance(listed, list) else []
        if not cards:
            self.logger.error("The %s marketplace page %s lists no software.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        taxonomy: Dict[str, str] = {}
        for value in categories if isinstance(categories, list) else []:
            category = self._as_object(value)
            slug, label = (
                self._as_text(category.get(CloudRuCardField.SLUG)),
                self._as_text(category.get(CloudRuCardField.DISPLAY_NAME)),
            )
            if slug and label:
                taxonomy[slug] = label
        self.logger.info(
            "%d cards and %d categories in the %s page %s.", len(cards), len(taxonomy), self.name, response.url
        )
        return cards, taxonomy

    def _texts(self, value: JsonValue, key: CloudRuCardField) -> List[str]:
        """Read the texts of a JSON list, or the texts of a field of the objects of a JSON list.

        Args:
            value (JsonValue): The JSON list, e.g. the category slugs or the product types of a card.
            key (CloudRuCardField): The field read from the objects of the list, e.g. `id`.

        Returns:
            List[str]: The non-blank texts, in order.
        """
        texts: List[str] = []
        for element in value if isinstance(value, list) else []:
            text = (
                self._as_text(element) if isinstance(element, str) else self._as_text(self._as_object(element).get(key))
            )
            if text and text.strip():
                texts.append(text.strip())
        return texts

    def _card_categories(
        self, card: Dict[str, JsonValue], taxonomy: Dict[str, str]
    ) -> Tuple[List[str], List[Optional[MarketplaceCategory]]]:
        """Read the marketplace categories of a card: its categories, then its selections.

        Args:
            card (Dict[str, JsonValue]): The card.
            taxonomy (Dict[str, str]): The category labels, by slug.

        Returns:
            Tuple[List[str], List[Optional[MarketplaceCategory]]]: The flat labels (categories, then selections) and
                the category paths (each category, or each category then each selection).
        """
        selections = self._texts(card.get(CloudRuCardField.SELECTION), CloudRuCardField.NAME)
        labels: List[str] = []
        paths: List[Optional[MarketplaceCategory]] = []
        for slug in self._texts(card.get(CloudRuCardField.CATEGORIES), CloudRuCardField.SLUG):
            label = taxonomy.get(slug)
            if label is None:
                self.logger.debug(
                    "Ignoring the unknown %s category %r of %r.",
                    self.name,
                    slug,
                    card.get(CloudRuCardField.DISPLAY_NAME),
                )
                continue
            labels.append(label)
            if selections:
                paths.extend(self._category([label, selection], selection) for selection in selections)
            else:
                paths.append(self._category([label], slug))
        return list(dict.fromkeys([*labels, *selections])), paths

    def _delivery(self, card: Dict[str, JsonValue]) -> DeliveryMethod:
        """Get how the software of a card is delivered.

        Args:
            card (Dict[str, JsonValue]): The card.

        Returns:
            DeliveryMethod: The method of its first known product type, else of its first category with one, else
                `other`.
        """
        for product_type in self._texts(card.get(CloudRuCardField.PRODUCT_TYPES), CloudRuCardField.ID):
            if product_type in self.DELIVERIES:
                return self.DELIVERIES[product_type]
        for slug in self._texts(card.get(CloudRuCardField.CATEGORIES), CloudRuCardField.SLUG):
            if slug in self.CATEGORY_DELIVERIES:
                return self.CATEGORY_DELIVERIES[slug]
        return DeliveryMethod.OTHER

    def _page_url(self, card: Dict[str, JsonValue]) -> Optional[str]:
        """Get the marketplace page of the software of a card, when it has one on the website.

        Args:
            card (Dict[str, JsonValue]): The card.

        Returns:
            Optional[str]: The `/marketplace/products/<slug>` page, `None` for a console software (`redirectUrl`) or
                a card without slug.
        """
        slug = (self._as_text(card.get(CloudRuCardField.SLUG)) or "").strip()
        if (self._as_text(card.get(CloudRuCardField.REDIRECT_URL)) or "").strip() or not slug:
            return None
        return self.PRODUCT_URL.format(slug=slug)

    def _card_software(
        self, card: Dict[str, JsonValue], taxonomy: Dict[str, str], detail: Optional[Dict[str, JsonValue]] = None
    ) -> Optional[MarketplaceSoftware]:
        """Build the software of a card, completed by its marketplace page if any.

        Args:
            card (Dict[str, JsonValue]): The card.
            taxonomy (Dict[str, str]): The category labels, by slug.
            detail (Optional[Dict[str, JsonValue]]): The software record of its marketplace page, if read.

        Returns:
            Optional[MarketplaceSoftware]: The software, `None` (logged) when the card is invalid.
        """
        record = detail or {}
        name = self._as_text(card.get(CloudRuCardField.DISPLAY_NAME))
        redirect = (self._as_text(card.get(CloudRuCardField.REDIRECT_URL)) or "").strip()
        url = urljoin(self.SITE_URL, redirect) if redirect else self._page_url(card)
        labels, paths = self._card_categories(card, taxonomy)
        return self._build_software(
            name,
            self._as_text(card.get(CloudRuCardField.PREVIEW_TEXT)),
            url,
            self._as_text(self._as_object(record.get(CloudRuCardField.LICENSE)).get(CloudRuCardField.OWNER)),
            self._delivery(card),
            labels,
            paths,
            added_at=self._parse_date(record.get(CloudRuCardField.CREATED_AT), name),
            updated_at=self._parse_date(record.get(CloudRuCardField.UPDATED_AT), name),
            updated_caveat=DateCaveat.CATALOGUE_ENTRY,
        )

    def _page_request(self, card: Dict[str, JsonValue], taxonomy: Dict[str, str], url: str) -> Optional[Request]:
        """Build the request of the marketplace page of a card, unless its software was already streamed.

        Args:
            card (Dict[str, JsonValue]): The card.
            taxonomy (Dict[str, str]): The category labels, by slug.
            url (str): The marketplace page of the software.

        Returns:
            Optional[Request]: The request, carrying the card and the labels of its categories, `None` when the
                software was already streamed.
        """
        if url.casefold().rstrip("/") in self.software_categories:
            self.logger.debug("Not requesting the %s page %s again.", self.name, url)
            return None
        slugs = self._texts(card.get(CloudRuCardField.CATEGORIES), CloudRuCardField.SLUG)
        labels: Dict[str, JsonValue] = {slug: taxonomy[slug] for slug in slugs if slug in taxonomy}
        return Request(url, meta={self.CARD: card, self.TAXONOMY: labels, self.MAY_BE_EMPTY: True})

    def _record(self, response: Response, slug: str) -> Optional[Dict[str, JsonValue]]:
        """Read the software record of a marketplace page.

        Args:
            response (Response): The marketplace page.
            slug (str): The slug of the software.

        Returns:
            Optional[Dict[str, JsonValue]]: The record (with its `license`), `None` when the page has none (logged).
        """
        try:
            documents = self.flight.documents(response)
        except CatalogueFormatError:
            self.logger.warning("The %s page %s holds no flight data: its card is kept alone.", self.name, response.url)
            return None
        for value in self.flight.objects(documents):
            if value.get(CloudRuCardField.SLUG) == slug and isinstance(value.get(CloudRuCardField.LICENSE), dict):
                return value
        self.logger.warning("No software record in the %s page %s: its card is kept alone.", self.name, response.url)
        return None

    def _listing_software(
        self, cards: List[Dict[str, JsonValue]], taxonomy: Dict[str, str]
    ) -> Iterator[MarketplaceSoftware]:
        """Build the software of the cards without marketplace page.

        Args:
            cards (List[Dict[str, JsonValue]]): The cards.
            taxonomy (Dict[str, str]): The category labels, by slug.

        Yields:
            MarketplaceSoftware: Each valid software of a card without marketplace page (a console software).
        """
        for card in cards:
            if self._page_url(card) is None and (software := self._card_software(card, taxonomy)):
                yield software

    def _requests(self, cards: List[Dict[str, JsonValue]], taxonomy: Dict[str, str]) -> Iterator[Request]:
        """Build the requests of the marketplace pages of the cards which have one.

        Args:
            cards (List[Dict[str, JsonValue]]): The cards.
            taxonomy (Dict[str, str]): The category labels, by slug.

        Yields:
            Request: Each marketplace page request, unless its software was already streamed.
        """
        for card in cards:
            url = self._page_url(card)
            if url and (request := self._page_request(card, taxonomy, url)):
                yield request

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a marketplace page, or of the cards of the listing without one.

        Args:
            response (Response): The marketplace page of a software (`CARD` meta), or the listing.

        Yields:
            Iterator[MarketplaceSoftware]: The software of the page, from its card and its record, or each valid
                software of the listing without marketplace page.
        """
        card = response.meta.get(self.CARD)
        if not isinstance(card, dict):
            yield from self._listing_software(*self._listing(response))
            return
        labels = self._as_object(response.meta.get(self.TAXONOMY))
        taxonomy = {slug: label for slug, label in labels.items() if isinstance(label, str)}
        record: Optional[Dict[str, JsonValue]] = None
        if response.status >= 400:
            self.logger.debug("The %s page %s is missing (HTTP %s).", self.name, response.url, response.status)
        else:
            record = self._record(response, self._as_text(card.get(CloudRuCardField.SLUG)) or "")
        if software := self._card_software(card, taxonomy, record):
            yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of the listing without marketplace page and request the other pages.

        Args:
            response (Response): The listing, or the marketplace page of a software (`CARD` meta).

        Yields:
            Union[Dict[str, JsonValue], Request]: Each software not streamed yet, then the marketplace page requests
                of the listing.
        """
        if self.CARD in response.meta:
            async for page_item in super().parse(response):
                yield page_item
            return
        self.logger.debug("Parsing the %s listing %s (HTTP %s).", self.name, response.url, response.status)
        cards, taxonomy = self._listing(response)
        streamed = requested = 0
        for software in self._listing_software(cards, taxonomy):
            if (item := self._stream_software(software)) is not None:
                streamed += 1
                yield item
        for request in self._requests(cards, taxonomy):
            requested += 1
            yield request
        self.logger.info(
            "%s listing %s parsed: %d software streamed, %d marketplace pages requested.",
            self.name,
            response.url,
            streamed,
            requested,
        )
