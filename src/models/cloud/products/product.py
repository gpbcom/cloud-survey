from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import SoftwareCategory, UrlScheme
from models.cloud.exception import EmptyMandatoryFieldError, InvalidProductUrlError, MissingPricingPolicyError
from models.cloud.products.pricing import ServicePricingPolicy


class CloudProduct(CategorizedItem):
    """Class representing a cloud product extracted from a cloud provider.

    Attributes:
        name (str): The product service name.
        description (str): The product service description.
        pricing_policy (List[ServicePricingPolicy]): The pricing policies associated to the product.
        url (Optional[str]): The product page, an absolute http(s) link.
        catalogue_categories (List[str]): The categories the catalogue of the provider files the product under, as
            labelled there (e.g. `Compute`, `AI & Machine Learning`), empty when it gives none.
        categories (List[SoftwareCategory]): Who the product is meant for: developer tool, end-user software or both
            (classified, see `SoftwareClassifier.classify_product`), empty before it is classified.
        service_categories, service_domains, source_label_ids, categories_source: The unified categorization (see
            `CategorizedItem`).
        added_at, added_from, updated_at, updated_from, deleted_at: The history dates (see `DatedItem`).

    Notes:
        The catalogue categories and the categories are not content fields: a catalogue reorganized by its provider, or
        new classification rules, do not update its products.
    """

    CONTENT_FIELDS: ClassVar[Tuple[str, ...]] = ("name", "description", "pricing_policy", "url")
    STREAMED_IF_FILLED: ClassVar[Tuple[str, ...]] = (
        *CategorizedItem.STREAMED_IF_FILLED,
        "catalogue_categories",
        "categories",
    )

    name: str = Field(description="Name of the cloud product.", max_length=200)
    description: str = Field(description="Description string for the cloud product.", max_length=1000)
    pricing_policy: List[ServicePricingPolicy] = Field(
        default_factory=list, description="The pricing policies associated to the product."
    )
    url: Optional[str] = Field(default=None, description="The product page, an absolute http(s) link.", max_length=2048)
    catalogue_categories: List[str] = Field(
        default_factory=list, description="The categories of the catalogue of the provider, as labelled there."
    )
    categories: List[SoftwareCategory] = Field(
        default_factory=list, description="Who the product is meant for: developers, business users or both."
    )

    @field_validator("url", mode="before")
    def validate_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw product URL.

        Args:
            value (JsonValue): The raw URL.

        Returns:
            JsonValue: The URL, `None` when missing or blank (its type is checked by pydantic afterwards).

        Raises:
            InvalidProductUrlError: If the URL is not an absolute http(s) link.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str):
            link = urlparse(value.strip())
            if link.scheme not in tuple(UrlScheme) or not link.netloc:
                raise InvalidProductUrlError(value)
            return value.strip()
        return value

    @field_validator("catalogue_categories", mode="before")
    def validate_catalogue_categories(cls, value: JsonValue) -> JsonValue:
        """Validate the raw catalogue categories: spaces collapsed, blank labels and duplicates dropped, order kept.

        Args:
            value (JsonValue): The raw labels.

        Returns:
            JsonValue: The cleaned labels, `[]` when missing (their type is checked by pydantic afterwards).
        """
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(label, str) for label in value):
            return value
        labels = [" ".join(label.split()) for label in value if isinstance(label, str)]
        return list(dict.fromkeys(label for label in labels if label != ""))

    @field_validator("categories", mode="before")
    def validate_categories(cls, value: JsonValue) -> JsonValue:
        """Validate the raw categories: duplicates dropped, in enum order.

        Args:
            value (JsonValue): The raw categories.

        Returns:
            JsonValue: The categories in enum order, `[]` when missing (their values are checked by pydantic
                afterwards).
        """
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return value
        order: List[JsonValue] = [category.value for category in SoftwareCategory]
        return sorted(dict.fromkeys(value), key=lambda item: order.index(item) if item in order else len(order))

    @field_validator("name", "description", mode="before")
    def validate_mandatory_fields(cls, value: JsonValue) -> JsonValue:
        """Validate the raw `name` and `description` attributes.

        Args:
            value (JsonValue): The raw value to be validated.

        Returns:
            JsonValue: The unchanged value, its type and length are checked by pydantic afterwards.

        Raises:
            EmptyMandatoryFieldError: If the value is missing or blank.
        """
        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise EmptyMandatoryFieldError()
        return value

    @field_validator("pricing_policy", mode="before")
    def validate_pricing_policy(
        cls, value: Union[JsonValue, Sequence[Union[ServicePricingPolicy, Dict[str, JsonValue]]]]
    ) -> Union[JsonValue, Sequence[Union[ServicePricingPolicy, Dict[str, JsonValue]]]]:
        """Validate the raw pricing policies associated to the current service.

        Args:
            value (Union[JsonValue, Sequence[Union[ServicePricingPolicy, Dict[str, JsonValue]]]]):
                The raw pricing policies, as dictionaries or models.

        Returns:
            Union[JsonValue, Sequence[Union[ServicePricingPolicy, Dict[str, JsonValue]]]]:
                The unchanged value, pydantic converts it into pricing policies afterwards (reporting the invalid
                entries with their position).

        Raises:
            MissingPricingPolicyError: If the pricing policy is missing.
        """
        if value is None:
            raise MissingPricingPolicyError()
        return value

    def match_keys(self) -> List[str]:
        """Get the keys recognizing the product in another crawl: its page, then its name.

        Returns:
            List[str]: The case-insensitive page URL (without trailing slash) when known, then the case-insensitive
                name with collapsed spaces.
        """
        keys = [f"url:{self.url.casefold().rstrip('/')}"] if self.url else []
        return [*keys, f"name:{' '.join(self.name.casefold().split())}"]

    def raw_labels(self) -> List[str]:
        """Get the categories the catalogue of the provider files the product under.

        Returns:
            List[str]: Its catalogue categories, as the provider writes them.
        """
        return list(self.catalogue_categories)

    def name_and_description(self) -> Tuple[str, str]:
        """Get the texts the item is classified from.

        Returns:
            Tuple[str, str]: Its name and its description.
        """
        return self.name, self.description
