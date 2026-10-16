from __future__ import annotations

# Standard Library Imports.
import json
import re
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from models.cloud.product import CloudProduct


class IBMCloudCrawler(BaseCloudCrawler):
    """IBM Cloud catalogue crawler.

    Attributes:
        CATALOG_HOST (ClassVar[str]): The IBM Cloud console, which serves the catalogue and the product pages.
        PRODUCTS_URL (ClassVar[str]): The "IBM Cloud" product search fragment of the ibm.com products page.
        STATE_MARKER (ClassVar[str]): The script variable holding the catalogue data.
        KEPT_TAG (ClassVar[str]): The catalogue tag of the offers created by IBM (not third party or community).
        KEPT_TYPES (ClassVar[FrozenSet[str]]): The catalogue types of the services (not content or pillars).
        EXCLUDED_TAGS (ClassVar[FrozenSet[str]]): The catalogue tags of the deprecated and beta services.
        TEST_HOST (ClassVar[re.Pattern[str]]): The hosts of the IBM test environments, whose links are dropped.
        NOT_PRODUCT_CARD (ClassVar[re.Pattern[str]]): The product search cards which are overviews, not products.
        CARD_ALIASES (ClassVar[Dict[str, str]]): The catalogue names of the products named otherwise on ibm.com.

    Notes:
        The main source is the IBM Cloud catalogue (https://cloud.ibm.com/catalog), whose data is embedded in the
        page (`window.__PRELOADED_STATE__`): `model.categories[*].items[*]`, an offer being listed in each of its
        categories. Only the services and infrastructure offers created by IBM are kept, without the deprecated,
        beta and consulting ones. An offer is dated by its last modification (`lastModified`), the catalogue giving
        no creation date. The "IBM Cloud" product search of ibm.com completes it with the products missing from the
        catalogue (e.g. the Cloud Paks), undated.
    """

    CATALOG_HOST: ClassVar[str] = "https://cloud.ibm.com"
    PRODUCTS_URL: ClassVar[str] = (
        "https://www.ibm.com/content/adobe-cms/us/en/products/jcr:content/root/table_of_contents/"
        "product_search_1183165654.search-full.html?field_hierarchy_07[0][0]=IBM%20Cloud&size=100&page=1"
    )
    STATE_MARKER: ClassVar[str] = "window.__PRELOADED_STATE__"
    KEPT_TAG: ClassVar[str] = "ibm_created"
    KEPT_TYPES: ClassVar[FrozenSet[str]] = frozenset({"service", "iaas"})
    EXCLUDED_TAGS: ClassVar[FrozenSet[str]] = frozenset({"ibm_deprecated", "ibm_beta"})
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

    name = "ibm"
    catalogue_url: ClassVar[str] = f"{CATALOG_HOST}/catalog"
    complement_urls: ClassVar[Tuple[str, ...]] = (PRODUCTS_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("IBM Cloud ", "IBM ", "Cloud ")

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
        text = response.body.decode("utf-8", errors="replace")
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

    def _catalog_items(self, response: Response) -> List[Dict[str, JsonValue]]:
        """Read the catalogue offers, once each, as an offer is listed in each of its categories.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Dict[str, JsonValue]]: The offers, in catalogue order.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.
        """
        categories = self._as_object(self._state(response).get("model")).get("categories")
        if not isinstance(categories, list):
            self.logger.error("The %s catalogue data of %s has no `model.categories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`model.categories` is not a list")
        items: Dict[str, Dict[str, JsonValue]] = {}
        for category in categories:
            entries = self._as_object(category).get("items")
            for entry in entries if isinstance(entries, list) else []:
                item = self._as_object(entry)
                key = self._as_text(item.get("id")) or self._as_text(item.get("name")) or ""
                items.setdefault(key, item)
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
        tags = item.get("allTags")
        tag_set = {tag for tag in tags if isinstance(tag, str)} if isinstance(tags, list) else set()
        reasons = {
            f"tag {item.get('tag')!r}": item.get("tag") != self.KEPT_TAG,
            f"type {item.get('type')!r}": item.get("type") not in self.KEPT_TYPES,
            "deprecated or beta": bool(tag_set & self.EXCLUDED_TAGS),
            "consulting offer": item.get("isConsulting") is True,
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
        """
        links: Set[str] = set()
        for item in self._catalog_items(response):
            name = self._as_text(item.get("name"))
            if reason := self._skip_reason(item):
                self.logger.debug("Skipping the catalogue offer %r (%s).", name, reason)
                continue
            link = self._catalog_link(self._as_text(item.get("catalogUrl")))
            if link is not None and self._url_key(link) in links:
                self.logger.debug("Ignoring the link %s of %r, shared with a previous catalogue offer.", link, name)
                link = None
            if link is not None:
                links.add(self._url_key(link))
            description = self._as_text(item.get("description"))
            updated_at = self._parse_date(item.get("lastModified"), name)
            if product := self._build_product(name, description, link, updated_at=updated_at):
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
            href = link.first.attrib.get("href") if link.first is not None else None
            if product := self._build_product(name, description, urljoin(response.url, href) if href else None):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

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
            return self._card_products(response)
        return self._catalog_products(response)
