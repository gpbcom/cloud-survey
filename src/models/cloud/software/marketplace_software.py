from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import DeliveryMethod, SoftwareCategory, UrlScheme
from models.cloud.exception import EmptyMandatoryFieldError, InvalidProductUrlError
from models.cloud.software.marketplace_category import MarketplaceCategory


class MarketplaceSoftware(CategorizedItem):
    """Class representing a software listed in the marketplace of a cloud provider.

    Attributes:
        name (str): The software name.
        description (str): The software short description.
        publisher (Optional[str]): The software publisher (vendor), when the marketplace gives it.
        url (Optional[str]): The marketplace page of the software, an absolute http(s) link.
        delivery (DeliveryMethod): How the software is delivered.
        marketplace_categories (List[str]): The categories given by the marketplace itself, as labelled there.
        marketplace_category_paths (Optional[List[MarketplaceCategory]]): The categories of the marketplace itself in
            its own taxonomy, each with the categories above it, `None` when the marketplace gives none. They are not
            content fields: a taxonomy reorganized by the marketplace does not update its software.
        categories (List[SoftwareCategory]): Who the software is meant for, at least one.
        service_categories, service_domains, source_label_ids, categories_source: The unified categorization (see
            `CategorizedItem`).
        added_at, added_from, updated_at, updated_from, deleted_at: The history dates (see `DatedItem`).
    """

    STREAMED_IF_SET: ClassVar[Tuple[str, ...]] = (*CategorizedItem.STREAMED_IF_SET, "marketplace_category_paths")
    CONTENT_FIELDS: ClassVar[Tuple[str, ...]] = (
        "name",
        "description",
        "publisher",
        "url",
        "delivery",
        "marketplace_categories",
    )

    name: str = Field(description="The software name.", max_length=300)
    description: str = Field(description="The software short description.", max_length=1000)
    publisher: Optional[str] = Field(default=None, description="The software publisher.", max_length=300)
    url: Optional[str] = Field(default=None, description="The marketplace page, an absolute link.", max_length=2048)
    delivery: DeliveryMethod = Field(default=DeliveryMethod.OTHER, description="How the software is delivered.")
    marketplace_categories: List[str] = Field(
        default_factory=list, description="The categories given by the marketplace itself."
    )
    marketplace_category_paths: Optional[List[MarketplaceCategory]] = Field(
        default=None, description="The categories of the marketplace in its own taxonomy, with their parents."
    )
    categories: List[SoftwareCategory] = Field(min_length=1, description="Who the software is meant for.")

    @field_validator("name", "description", mode="before")
    def validate_mandatory_fields(cls, value: JsonValue) -> JsonValue:
        """Validate the raw `name` and `description` attributes.

        Args:
            value (JsonValue): The raw value.

        Returns:
            JsonValue: The unchanged value, its type and length are checked by pydantic afterwards.

        Raises:
            EmptyMandatoryFieldError: If the value is missing or blank.
        """
        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise EmptyMandatoryFieldError()
        return value

    @field_validator("publisher", mode="before")
    def validate_publisher(cls, value: JsonValue) -> JsonValue:
        """Validate the raw publisher.

        Args:
            value (JsonValue): The raw publisher.

        Returns:
            JsonValue: The trimmed publisher, `None` when missing or blank.
        """
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("url", mode="before")
    def validate_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw marketplace page URL.

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

    @field_validator("marketplace_categories", "categories", mode="before")
    def validate_labels(cls, value: JsonValue) -> JsonValue:
        """Validate the raw label lists: blank labels and duplicates are dropped, the order is kept.

        Args:
            value (JsonValue): The raw labels.

        Returns:
            JsonValue: The cleaned labels (their values are checked by pydantic afterwards).
        """
        if not isinstance(value, list):
            return value
        labels = [label.strip() if isinstance(label, str) else label for label in value]
        return list(dict.fromkeys(label for label in labels if label != ""))

    @field_validator("marketplace_category_paths", mode="before")
    def validate_category_paths(
        cls, value: Union[JsonValue, Sequence[Union[MarketplaceCategory, Dict[str, JsonValue]]]]
    ) -> Union[JsonValue, Sequence[Union[MarketplaceCategory, Dict[str, JsonValue]]]]:
        """Validate the raw category paths: duplicates and the parents of another category are dropped.

        Args:
            value (Union[JsonValue, Sequence[Union[MarketplaceCategory, Dict[str, JsonValue]]]]): The raw categories,
                as models or dictionaries.

        Returns:
            Union[JsonValue, Sequence[Union[MarketplaceCategory, Dict[str, JsonValue]]]]: The most precise categories
                in their order, `None` when there is none (the invalid entries are reported by pydantic afterwards).
        """
        if not isinstance(value, (list, tuple)):
            return value
        if not value:
            return None
        if not all(isinstance(entry, (MarketplaceCategory, dict)) for entry in value):
            return list(value)
        categories = [
            entry if isinstance(entry, MarketplaceCategory) else MarketplaceCategory.model_validate(entry)
            for entry in value
        ]
        unique = list({tuple(category.path): category for category in reversed(categories)}.values())[::-1]
        return [category for category in unique if not any(category.is_above(other) for other in unique)]

    def identity(self) -> str:
        """Get the identity of the software, the same for the listings of one marketplace page.

        Returns:
            str: Its case-insensitive page URL (without trailing slash), else its case-insensitive name and publisher.
        """
        if self.url:
            return self.url.casefold().rstrip("/")
        return f"{self.name.casefold()}|{(self.publisher or '').casefold()}"

    def match_keys(self) -> List[str]:
        """Get the keys recognizing the software in another crawl: its identity, then its name and publisher.

        Returns:
            List[str]: The identity, then the case-insensitive name and publisher with collapsed spaces.
        """
        name = " ".join(self.name.casefold().split())
        return [f"id:{self.identity()}", f"name:{name}|{(self.publisher or '').casefold()}"]

    def raw_labels(self) -> List[str]:
        """Get the categories the marketplace files the software under.

        Returns:
            List[str]: Its marketplace categories (flat labels), as the provider writes them.
        """
        return list(self.marketplace_categories)

    def delivery_method(self) -> Optional[DeliveryMethod]:
        """Get how the software is delivered.

        Returns:
            Optional[DeliveryMethod]: Its delivery method.
        """
        return self.delivery

    def name_and_description(self) -> Tuple[str, str]:
        """Get the texts the item is classified from.

        Returns:
            Tuple[str, str]: Its name and its description.
        """
        return self.name, self.description
