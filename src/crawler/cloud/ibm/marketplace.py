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
from crawler.cloud.ibm.enums import (
    IbmCatalogueTag,
    IbmCategoryField,
    IbmOfferField,
    IbmOfferKind,
    IbmScriptVariable,
    IbmStateField,
)
from crawler.enums import TextEncoding
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class IBMMarketplaceCrawler(BaseMarketplaceCrawler):
    """IBM Cloud marketplace crawler: the third party and community software of the IBM Cloud catalogue.

    Attributes:
        CATALOG_HOST (ClassVar[str]): The IBM Cloud console, which serves the catalogue and the offer pages.
        STATE_MARKER (ClassVar[IbmScriptVariable]): The script variable holding the catalogue data.
        KEPT_TAGS (ClassVar[FrozenSet[IbmCatalogueTag]]): The catalogue tags of the offers not created by IBM.
        EXCLUDED_TAGS (ClassVar[FrozenSet[IbmCatalogueTag]]): The catalogue tags of the deprecated and beta offers.
        SERVICE_TAG (ClassVar[IbmCatalogueTag]): The catalogue tag of the professional services.
        CONTENT_KIND (ClassVar[IbmOfferKind]): The kind of the content offers, a professional service when it has the
            `SERVICE_TAG` tag.
        NOT_SOFTWARE (ClassVar[re.Pattern[str]]): The names of the managed, migration and professional services.
        DELIVERIES (ClassVar[Dict[IbmOfferKind, DeliveryMethod]]): The delivery of each offer kind, `OTHER` for the
            others.

    Notes:
        The only source is the IBM Cloud catalogue (https://cloud.ibm.com/catalog), whose data is embedded in the
        page (`window.__PRELOADED_STATE__`): `model.categories[*].items[*]`, an offer being listed in each of its
        categories (their names are merged). The offers tagged `ibm_third_party` or `ibm_community` are kept, without
        the consulting, professional service, managed service, deprecated and beta ones. The publisher is the offer
        author, the delivery comes from the offer kind (SaaS service, VSI image, Terraform, Helm chart, operator).
    """

    CATALOG_HOST: ClassVar[str] = "https://cloud.ibm.com"
    STATE_MARKER: ClassVar[IbmScriptVariable] = IbmScriptVariable.PRELOADED_STATE
    KEPT_TAGS: ClassVar[FrozenSet[IbmCatalogueTag]] = frozenset(
        {IbmCatalogueTag.THIRD_PARTY, IbmCatalogueTag.COMMUNITY}
    )
    EXCLUDED_TAGS: ClassVar[FrozenSet[IbmCatalogueTag]] = frozenset({IbmCatalogueTag.DEPRECATED, IbmCatalogueTag.BETA})
    SERVICE_TAG: ClassVar[IbmCatalogueTag] = IbmCatalogueTag.PROFESSIONAL_SERVICE
    CONTENT_KIND: ClassVar[IbmOfferKind] = IbmOfferKind.CONTENT
    NOT_SOFTWARE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(?:professional|consulting|managed|migrations?) services?\b", re.IGNORECASE
    )
    DELIVERIES: ClassVar[Dict[IbmOfferKind, DeliveryMethod]] = {
        IbmOfferKind.SERVICE: DeliveryMethod.SAAS,
        IbmOfferKind.TERRAFORM: DeliveryMethod.OTHER,
        IbmOfferKind.VSI_IMAGE: DeliveryMethod.VIRTUAL_MACHINE,
        IbmOfferKind.OVA: DeliveryMethod.VIRTUAL_MACHINE,
        IbmOfferKind.HELM: DeliveryMethod.KUBERNETES,
        IbmOfferKind.OPERATOR: DeliveryMethod.KUBERNETES,
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

    def _catalog_items(
        self, response: Response
    ) -> List[Tuple[Dict[str, JsonValue], List[str], List[MarketplaceCategory]]]:
        """Read the catalogue offers once each, with the names and the paths of all their categories.

        Args:
            response (Response): The catalogue page.

        Returns:
            List[Tuple[Dict[str, JsonValue], List[str], List[MarketplaceCategory]]]: The offers, their category names
                and their category paths (one level, identified by the category `id`), in catalogue order.

        Raises:
            CatalogueFormatError: If the page has no catalogue data, or no `model.categories` list.
        """
        categories = self._as_object(self._state(response).get(IbmStateField.MODEL)).get(IbmStateField.CATEGORIES)
        if not isinstance(categories, list):
            self.logger.error("The %s catalogue data of %s has no `model.categories` list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "`model.categories` is not a list")
        items: Dict[str, Tuple[Dict[str, JsonValue], List[str], List[MarketplaceCategory]]] = {}
        for entry in categories:
            category = self._as_object(entry)
            label = self._as_text(category.get(IbmCategoryField.NAME))
            path = self._category([label], self._as_text(category.get(IbmCategoryField.ID)))
            offers = category.get(IbmCategoryField.ITEMS)
            for offer in offers if isinstance(offers, list) else []:
                item = self._as_object(offer)
                key = self._as_text(item.get(IbmOfferField.ID)) or self._as_text(item.get(IbmOfferField.NAME)) or ""
                _, labels, paths = items.setdefault(key, (item, [], []))
                if label and label not in labels:
                    labels.append(label)
                if path is not None and path not in paths:
                    paths.append(path)
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
        tags = item.get(IbmOfferField.ALL_TAGS)
        tag_set = {tag for tag in tags if isinstance(tag, str)} if isinstance(tags, list) else set()
        reasons = {
            f"tag {item.get(IbmOfferField.TAG)!r}": item.get(IbmOfferField.TAG) not in self.KEPT_TAGS,
            "consulting offer": item.get(IbmOfferField.IS_CONSULTING) is True,
            "professional service": item.get(IbmOfferField.KIND) == self.CONTENT_KIND and self.SERVICE_TAG in tag_set,
            "service offer": bool(self.NOT_SOFTWARE.search(self._as_text(item.get(IbmOfferField.NAME)) or "")),
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
        for item, categories, paths in self._catalog_items(response):
            name = self._as_text(item.get(IbmOfferField.NAME))
            if reason := self._skip_reason(item):
                self.logger.debug("Skipping the catalogue offer %r (%s).", name, reason)
                continue
            kind = self._as_text(item.get(IbmOfferField.KIND)) or ""
            link = self._as_text(item.get(IbmOfferField.CATALOG_URL))
            software = self._build_software(
                name,
                self._as_text(item.get(IbmOfferField.DESCRIPTION)),
                url=urljoin(f"{self.CATALOG_HOST}/", link) if link else None,
                publisher=self._as_text(item.get(IbmOfferField.AUTHOR)),
                delivery=self.DELIVERIES[IbmOfferKind(kind)] if kind in self.DELIVERIES else DeliveryMethod.OTHER,
                marketplace_categories=categories,
                marketplace_category_paths=paths,
                updated_at=self._parse_date(item.get(IbmOfferField.LAST_MODIFIED), name),
                updated_caveat=DateCaveat.CATALOGUE_ENTRY,
            )
            if software is not None:
                yield software
