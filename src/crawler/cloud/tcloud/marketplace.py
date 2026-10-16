from __future__ import annotations

# Standard Library Imports.
import html
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class TCloudPublicMarketplaceCrawler(BaseMarketplaceCrawler):
    """T Cloud Public marketplace crawler.

    Attributes:
        CATEGORIES_URL (ClassVar[str]): The marketplace categories API.
        CATEGORIES (ClassVar[str]): The meta key marking the categories request.
        PRODUCT_URL (ClassVar[str]): The product page URL template, filled with the product identifier.
        SERVICE_CATEGORIES (ClassVar[FrozenSet[str]]): The categories of the professional services offers.
        SERVICE_SELLERS (ClassVar[FrozenSet[str]]): The sellers of professional services only.
        NOT_SOFTWARE (ClassVar[re.Pattern[str]]): The names of the consulting offers listed in software categories.
        DELIVERIES (ClassVar[Dict[str, DeliveryMethod]]): The delivery method of each marketplace product type.
        category_names (Dict[str, str]): The name of each marketplace category, by identifier.

    Notes:
        The marketplace is a single page application reading a JSON API: the categories
        (`/api/v1/client/categories`) are requested first, then the products (`/api/v1/client/products`, every
        product at once), whose categories are identifiers. The products whose categories are all professional
        services ones (advisory, build and optimize offers), the T-Systems professional services and the consulting
        offers are skipped. The marketplace `robots.txt` answers HTTP 415: Scrapling then allows every page.
    """

    CATEGORIES_URL: ClassVar[str] = "https://marketplace.t-cloud-public.com/api/v1/client/categories"
    CATEGORIES: ClassVar[str] = "categories"
    PRODUCT_URL: ClassVar[str] = "https://marketplace.t-cloud-public.com/product-offering/{product}"
    SERVICE_CATEGORIES: ClassVar[FrozenSet[str]] = frozenset(
        {"Advisory & Assessment", "Build & Migrate", "Optimize & Secure"}
    )
    SERVICE_SELLERS: ClassVar[FrozenSet[str]] = frozenset({"T-Systems | Cloud Professional Services"})
    NOT_SOFTWARE: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(assessment|advisory|consulting)\b|transformation services", re.IGNORECASE
    )
    DELIVERIES: ClassVar[Dict[str, DeliveryMethod]] = {
        "lead-generation": DeliveryMethod.SAAS,
        "container": DeliveryMethod.CONTAINER,
        "llm-tpm": DeliveryMethod.AI_MODEL,
    }

    name = "tcloud-marketplace"
    catalogue_url: ClassVar[str] = "https://marketplace.t-cloud-public.com/api/v1/client/products"

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
        self.category_names: Dict[str, str] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _json_list(self, response: Response) -> List[JsonValue]:
        """Read a JSON array response of the API.

        Args:
            response (Response): The API response.

        Returns:
            List[JsonValue]: The JSON array.

        Raises:
            CatalogueFormatError: If the response is not a JSON array.
        """
        data = self._json_body(response)
        if not isinstance(data, list):
            self.logger.error("The %s API response %s is not a JSON array.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the response is not a JSON array")
        return data

    def _read_categories(self, response: Response) -> None:
        """Read the names of the marketplace categories.

        Args:
            response (Response): The categories API response.
        """
        for entry in self._json_list(response):
            fields = self._as_object(entry)
            identifier, label = self._as_text(fields.get("id")), self._as_text(fields.get("name"))
            if identifier and label:
                self.category_names[identifier] = label
        self.logger.info("%d %s categories read.", len(self.category_names), self.name)

    def _categories(self, product: Dict[str, JsonValue]) -> List[str]:
        """Get the category names of a product.

        Args:
            product (Dict[str, JsonValue]): The product data.

        Returns:
            List[str]: The names of its known categories.
        """
        identifiers = product.get("categories")
        if not isinstance(identifiers, list):
            return []
        names = (self.category_names.get(self._as_text(identifier) or "") for identifier in identifiers)
        return [label for label in names if label]

    def _excluded(self, name: Optional[str], seller: Optional[str], categories: List[str]) -> Optional[str]:
        """Tell why a product is not a software, if it is not.

        Args:
            name (Optional[str]): The product name.
            seller (Optional[str]): The product seller.
            categories (List[str]): The product category names.

        Returns:
            Optional[str]: The reason, `None` for a software.
        """
        if categories and self.SERVICE_CATEGORIES.issuperset(categories):
            return f"professional services categories {', '.join(categories)}"
        if seller in self.SERVICE_SELLERS:
            return f"professional services seller {seller}"
        if name and self.NOT_SOFTWARE.search(name):
            return "consulting offer"
        return None

    def _description(self, product: Dict[str, JsonValue]) -> Optional[str]:
        """Read the description of a product: its short description, else its long one as text.

        Args:
            product (Dict[str, JsonValue]): The product data.

        Returns:
            Optional[str]: The description, `None` when the product has none.
        """
        short = self._as_text(product.get("description_short"))
        if short and short.strip():
            return short
        description = self._as_text(product.get("description"))
        return html.unescape(re.sub(r"<[^>]+>", " ", description)) if description else None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Start the crawl from the categories, which name the categories of the products.

        Yields:
            Request: The categories request, the products being requested once the categories are read.
        """
        self.logger.debug("Requesting the %s categories %s.", self.name, self.CATEGORIES_URL)
        yield Request(self.CATEGORIES_URL, priority=self.PRIMARY_PRIORITY, meta={self.CATEGORIES: True})

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the products API response, the professional services excluded.

        Args:
            response (Response): The products API response.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the response, with its listing date (`created_at`),
                the API publishing no update date.
        """
        products = self._json_list(response)
        self.logger.info("%d products listed by the %s API %s.", len(products), self.name, response.url)
        for entry in products:
            product = self._as_object(entry)
            name, identifier = self._as_text(product.get("name")), self._as_text(product.get("id"))
            seller = self._as_text(self._as_object(product.get("seller")).get("name"))
            categories = self._categories(product)
            if reason := self._excluded(name, seller, categories):
                self.logger.debug("Skipping the %s product %r, not a software (%s).", self.name, name, reason)
                continue
            software = self._build_software(
                name,
                self._description(product),
                self.PRODUCT_URL.format(product=identifier) if identifier else None,
                seller,
                self.DELIVERIES.get(self._as_text(product.get("type")) or "", DeliveryMethod.OTHER),
                categories,
                added_at=self._parse_date(product.get("created_at"), name),
            )
            if software is not None:
                yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Read the categories then request the products, or stream the software of the products.

        Args:
            response (Response): The categories (`CATEGORIES` meta) or the products API response.

        Yields:
            Union[Dict[str, JsonValue], Request]: The products request, or each software not streamed yet.
        """
        if response.meta.get(self.CATEGORIES):
            self._read_categories(response)
            self.logger.debug("Requesting the %s products %s.", self.name, self.catalogue_url)
            yield self._catalogue_request()
            return
        async for item in super().parse(response):
            yield item
