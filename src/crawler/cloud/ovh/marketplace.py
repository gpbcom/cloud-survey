from __future__ import annotations

# Standard Library Imports.
import base64
import binascii
import html
import json
import re
from typing import ClassVar, Dict, FrozenSet, Iterator, List, Optional

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Response

# First Party Imports.
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class OVHcloudMarketplaceCrawler(BaseMarketplaceCrawler):
    """OVHcloud marketplace crawler.

    Attributes:
        PRODUCTS_SCRIPT (ClassVar[str]): The identifier of the script holding the marketplace products.
        ASSET_TYPES_SCRIPT (ClassVar[str]): The identifier of the script holding the top categories (asset types).
        PRODUCT_URL (ClassVar[str]): The product page URL template, filled with the product slug and key.
        SUBCATEGORIES (ClassVar[str]): The name of the product filter group listing its sub-categories.
        SERVICE_TYPE (ClassVar[str]): The name of the product filter group listing its service types.
        EXCLUDED_SERVICE_TYPES (ClassVar[FrozenSet[str]]): The service types of the services, which are not software.
        EXCLUDED_SUBCATEGORIES (ClassVar[FrozenSet[str]]): The sub-categories of the technical support offers.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each software service type.

    Notes:
        The https://marketplace.ovhcloud.com/en/products page embeds every product (no pagination) as base64 JSON
        in its `preloadedProductsData` script, and the top categories in its `preloadedAssetTypesData` script. A
        product belongs to the top category whose field set is its asset type, and lists its sub-categories and
        service types in its filter groups. The support and managed services offers are not software: they are
        skipped.
    """

    PRODUCTS_SCRIPT: ClassVar[str] = "preloadedProductsData"
    ASSET_TYPES_SCRIPT: ClassVar[str] = "preloadedAssetTypesData"
    PRODUCT_URL: ClassVar[str] = "https://marketplace.ovhcloud.com/en/product/{slug}/{key}"
    SUBCATEGORIES: ClassVar[str] = "Subcategories"
    SERVICE_TYPE: ClassVar[str] = "Service type"
    EXCLUDED_SERVICE_TYPES: ClassVar[FrozenSet[str]] = frozenset({"support", "managed services"})
    EXCLUDED_SUBCATEGORIES: ClassVar[FrozenSet[str]] = frozenset(
        {"technical support", "assistance technique ponctuelle"}
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "saas": DeliveryMethod.SAAS,
        "paas": DeliveryMethod.SAAS,
        "software on-prem": DeliveryMethod.DOWNLOAD,
    }

    name = "ovhcloud-marketplace"
    catalogue_url: ClassVar[str] = "https://marketplace.ovhcloud.com/en/products"

    ############################
    # Internal Helpers Methods #
    ############################

    def _preloaded_data(self, response: Response, script: str) -> Dict[str, JsonValue]:
        """Read the base64 JSON data of a script of the products page.

        Args:
            response (Response): The products page.
            script (str): The script identifier.

        Returns:
            Dict[str, JsonValue]: The decoded data.

        Raises:
            CatalogueFormatError: If the script is missing, or does not hold a base64 JSON object.
        """
        raw = response.css(f"script#{script}::text").get()
        if raw is None:
            self.logger.error("The %s page %s has no `%s` script.", self.name, response.url, script)
            raise CatalogueFormatError(self.name, response.url, f"the `{script}` script is missing")
        try:
            # The script declares UTF-16, but its data is UTF-8.
            data: JsonValue = json.loads(base64.b64decode(raw.strip(), validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as e:
            self.logger.error(
                "The `%s` script of the %s page %s is not base64 JSON: %s", script, self.name, response.url, e
            )
            raise CatalogueFormatError(self.name, response.url, f"the `{script}` script is not base64 JSON") from e
        if not isinstance(data, dict):
            self.logger.error("The `%s` script of the %s page %s is not an object.", script, self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, f"the `{script}` script is not a JSON object")
        self.logger.debug("The `%s` script of %s read (%d characters).", script, response.url, len(raw))
        return data

    def _top_categories(self, response: Response) -> Dict[int, str]:
        """Read the top categories of the marketplace, by field set (the asset type of their products).

        Args:
            response (Response): The products page.

        Returns:
            Dict[int, str]: The English name of each top category, by field set identifier.
        """
        types = self._preloaded_data(response, self.ASSET_TYPES_SCRIPT).get("response")
        categories: Dict[int, str] = {}
        for entry in types if isinstance(types, list) else []:
            fields = self._as_object(entry)
            label = self._as_text(fields.get("localizedName")) or self._as_text(fields.get("name"))
            field_set = fields.get("fieldSetID")
            if isinstance(field_set, int) and label:
                categories[field_set] = label
        self.logger.debug("%d top categories read: %s.", len(categories), ", ".join(categories.values()))
        return categories

    def _filters(self, product: Dict[str, JsonValue], group: str) -> List[str]:
        """Read the values of a filter group of a product, e.g. its sub-categories.

        Args:
            product (Dict[str, JsonValue]): The product data.
            group (str): The filter group name.

        Returns:
            List[str]: The filter values, empty when the product has no such group.
        """
        groups = product.get("categories")
        values: List[str] = []
        for entry in groups if isinstance(groups, list) else []:
            fields = self._as_object(entry)
            filters = fields.get("filters")
            if fields.get("categoryName") == group and isinstance(filters, list):
                values.extend(text for text in (self._as_text(value) for value in filters) if text)
        return values

    def _excluded(self, product: Dict[str, JsonValue], service_types: List[str]) -> Optional[str]:
        """Tell why a product is not a software, if it is not.

        Args:
            product (Dict[str, JsonValue]): The product data.
            service_types (List[str]): The service types of the product.

        Returns:
            Optional[str]: The reason, `None` for a software.
        """
        excluded = sorted(self.EXCLUDED_SERVICE_TYPES.intersection(kind.casefold() for kind in service_types))
        if excluded:
            return f"service type {', '.join(excluded)}"
        custom = self._as_text(self._as_object(product.get("customFields")).get("Subcategory")) or ""
        labels = [label.casefold() for label in self._filters(product, self.SUBCATEGORIES)]
        if any(label in self.EXCLUDED_SUBCATEGORIES for label in labels) or any(
            label in custom.casefold() for label in self.EXCLUDED_SUBCATEGORIES
        ):
            return "technical support sub-category"
        return None

    def _description(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Read the description of a product: its search engine description, else its HTML description as text.

        Args:
            product (Dict[str, JsonValue]): The product data.

        Returns:
            Optional[str]: The description, `None` when the product has none.
        """
        seo = self._as_text(self._as_object(product.get("seoElements")).get("description"))
        if seo and seo.strip():
            return seo
        description = self._as_text(product.get("description"))
        return html.unescape(re.sub(r"<[^>]+>", " ", description)) if description else None

    def _delivery(self, service_types: List[str]) -> DeliveryMethod:
        """Get the delivery method of a product from its service types.

        Args:
            service_types (List[str]): The service types of the product, by order of preference.

        Returns:
            DeliveryMethod: The delivery method of its first known service type, `OTHER` without any.
        """
        return next(
            (self.DELIVERIES[kind.casefold()] for kind in service_types if kind.casefold() in self.DELIVERIES),
            DeliveryMethod.OTHER,
        )

    def _product_url(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Build the marketplace page URL of a product.

        Args:
            product (Dict[str, JsonValue]): The product data.

        Returns:
            Optional[str]: The page URL, `None` without slug or key.
        """
        slug, key = self._as_text(product.get("slugName")), self._as_text(product.get("assetEncryptKey"))
        return self.PRODUCT_URL.format(slug=slug, key=key) if slug and key else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the products page, the support and managed services excluded.

        Args:
            response (Response): The products page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page, with its listing (`createdOn`) and update
                (`updatedOn`) dates.

        Raises:
            CatalogueFormatError: If the page data has no products list.
        """
        products = self._as_object(self._preloaded_data(response, self.PRODUCTS_SCRIPT).get("response")).get("assets")
        if not isinstance(products, list):
            self.logger.error("The %s page %s data has no products list.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the page data has no products list")
        top_categories = self._top_categories(response)
        self.logger.info("%d products listed by the %s page %s.", len(products), self.name, response.url)
        for entry in products:
            product = self._as_object(entry)
            name = self._as_text(product.get("name"))
            service_types = self._filters(product, self.SERVICE_TYPE)
            if reason := self._excluded(product, service_types):
                self.logger.debug("Skipping the %s product %r, not a software (%s).", self.name, name, reason)
                continue
            asset_type = product.get("assetTypeID")
            top_category = top_categories.get(asset_type) if isinstance(asset_type, int) else None
            software = self._build_software(
                name,
                self._description(product),
                self._product_url(product),
                self._as_text(product.get("organizationName")),
                self._delivery(service_types),
                [top_category, *self._filters(product, self.SUBCATEGORIES)],
                added_at=self._parse_date(product.get("createdOn"), name),
                updated_at=self._parse_date(product.get("updatedOn"), name),
            )
            if software is not None:
                yield software
