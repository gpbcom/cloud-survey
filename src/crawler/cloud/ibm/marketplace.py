from __future__ import annotations

# Standard Library Imports.
import json
import re
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class IBMMarketplaceCrawler(BaseMarketplaceCrawler):
    """IBM Cloud marketplace crawler: the third party and community software of the IBM Cloud catalogue.

    Attributes:
        CATALOG_HOST (ClassVar[str]): The IBM Cloud console, which serves the catalogue and the offer pages.
        STATE_MARKER (ClassVar[str]): The script variable holding the catalogue data.
        KEPT_TAGS (ClassVar[FrozenSet[str]]): The catalogue tags of the offers not created by IBM.
        EXCLUDED_TAGS (ClassVar[FrozenSet[str]]): The catalogue tags of the deprecated and beta offers.
        SERVICE_TAG (ClassVar[str]): The catalogue tag of the professional services.
        CONTENT_KIND (ClassVar[str]): The kind of the content offers, a professional service when it has the
            `SERVICE_TAG` tag.
        NOT_SOFTWARE (ClassVar[re.Pattern[str]]): The names of the managed, migration and professional services.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery of each offer kind, `OTHER` for the others.

    Notes:
        The only source is the IBM Cloud catalogue (https://cloud.ibm.com/catalog), whose data is embedded in the
        page (`window.__PRELOADED_STATE__`): `model.categories[*].items[*]`, an offer being listed in each of its
        categories (their names are merged). The offers tagged `ibm_third_party` or `ibm_community` are kept, without
        the consulting, professional service, managed service, deprecated and beta ones. The publisher is the offer
        author, the delivery comes from the offer kind (SaaS service, VSI image, Terraform, Helm chart, operator).
    """

    CATALOG_HOST: ClassVar[str] = "https://cloud.ibm.com"
    STATE_MARKER: ClassVar[str] = "window.__PRELOADED_STATE__"
    KEPT_TAGS: ClassVar[FrozenSet[str]] = frozenset({"ibm_third_party", "ibm_community"})
    EXCLUDED_TAGS: ClassVar[FrozenSet[str]] = frozenset({"ibm_deprecated", "ibm_beta"})
    SERVICE_TAG: ClassVar[str] = "professional_service"
    CONTENT_KIND: ClassVar[str] = "content"
    NOT_SOFTWARE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:professional|consulting|managed|migrations?) services?\b", re.IGNORECASE
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "service": DeliveryMethod.SAAS,
        "terraform": DeliveryMethod.OTHER,
        "vsi_image": DeliveryMethod.VIRTUAL_MACHINE,
        "ova": DeliveryMethod.VIRTUAL_MACHINE,
        "helm": DeliveryMethod.KUBERNETES,
        "operator": DeliveryMethod.KUBERNETES,
    }

    name = "ibm-marketplace"
    catalogue_url: ClassVar[str] = f"{CATALOG_HOST}/catalog"

    ############################
    # Internal Helpers Methods #
    ############################

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

    def _catalog_items(self, response: Response) -> List[Tuple[Dict[str, JsonValue], List[str]]]:
        """Read the catalogue offers once each, with the names of all their categories.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str]]]: The offers and their category names, in catalogue order.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.
        """
        categories = self._as_object(self._state(response).get("model")).get("categories")
        if not isinstance(categories, list):
            self.logger.error("The %s catalogue data of %s has no `model.categories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`model.categories` is not a list")
        items: Dict[str, Tuple[Dict[str, JsonValue], List[str]]] = {}
        for entry in categories:
            category = self._as_object(entry)
            label = self._as_text(category.get("name"))
            offers = category.get("items")
            for offer in offers if isinstance(offers, list) else []:
                item = self._as_object(offer)
                key = self._as_text(item.get("id")) or self._as_text(item.get("name")) or ""
                labels = items.setdefault(key, (item, []))[1]
                if label and label not in labels:
                    labels.append(label)
        self.logger.debug("%d catalogue offers in %d categories of %s.", len(items), len(categories), response.url)
        return list(items.values())

    def _skip_reason(self, item: Dict[str, JsonValue]) -> Optional[str]:
        """Tell why a catalogue offer is not a marketplace software.

        Args:
            item (Dict[str, JsonValue]): The catalogue offer.

        Returns:
            Optional[str]: The reason (IBM offer, consulting, professional or managed service, deprecated or beta
                offer), `None` for a marketplace software.
        """
        tags = item.get("allTags")
        tag_set = {tag for tag in tags if isinstance(tag, str)} if isinstance(tags, list) else set()
        reasons = {
            f"tag {item.get('tag')!r}": item.get("tag") not in self.KEPT_TAGS,
            "consulting offer": item.get("isConsulting") is True,
            "professional service": item.get("kind") == self.CONTENT_KIND and self.SERVICE_TAG in tag_set,
            "service offer": bool(self.NOT_SOFTWARE.search(self._as_text(item.get("name")) or "")),
            "deprecated or beta": bool(tag_set & self.EXCLUDED_TAGS),
        }
        failed = [reason for reason, matched in reasons.items() if matched]
        return ", ".join(failed) if failed else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the third party and community software of the IBM Cloud catalogue.

        Args:
            response (Response): The catalogue page.

        Yields:
            MarketplaceSoftware: Each valid software of the catalogue, with its update date (`lastModified`), the
                catalogue publishing no listing date.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.
        """
        for item, categories in self._catalog_items(response):
            name = self._as_text(item.get("name"))
            if reason := self._skip_reason(item):
                self.logger.debug("Skipping the catalogue offer %r (%s).", name, reason)
                continue
            kind = self._as_text(item.get("kind")) or ""
            link = self._as_text(item.get("catalogUrl"))
            software = self._build_software(
                name,
                self._as_text(item.get("description")),
                url=urljoin(f"{self.CATALOG_HOST}/", link) if link else None,
                publisher=self._as_text(item.get("author")),
                delivery=self.DELIVERIES.get(kind, DeliveryMethod.OTHER),
                marketplace_categories=categories,
                updated_at=self._parse_date(item.get("lastModified"), name),
            )
            if software is not None:
                yield software
