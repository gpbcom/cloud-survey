from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import Field, JsonValue, SerializerFunctionWrapHandler, field_validator, model_serializer

# First Party Imports.
from models.cloud.dated_item import DATE_FIELDS, DatedItem
from models.cloud.enums import DeliveryMethod
from models.taxonomy.enums import CategorySource


class CategorizedItem(DatedItem):
    """Base class of the crawled items filed in the unified taxonomy (products and software).

    Attributes:
        SERVICE_FIELDS (ClassVar[Tuple[str, ...]]): The fields of the unified categorization, computed by the storage.
        service_categories (List[str]): The taxonomy categories of the item (slugs, several at once).
        service_domains (List[str]): The taxonomy domains of the item: those of its categories, and those its source
            labels tell without a category.
        source_label_ids (List[int]): The identifiers of its source labels (`source_labels.id`), translated and
            de-duplicated by the storage.
        categories_source (Optional[CategorySource]): What gave the item its categories, `None` before the storage
            categorized it.

    Notes:
        - The crawlers leave these fields empty: the storage fills them when it writes the items, from the source
          labels stored in SQL (see `storage.repositories.taxonomy.item_categorizer.ItemCategorizer`).
        - They are not content fields: a change of categorization updates an item without making a new version.
        - They are serialized after the content of the item, before its dates.
    """

    SERVICE_FIELDS: ClassVar[Tuple[str, ...]] = (
        "service_categories",
        "service_domains",
        "source_label_ids",
        "categories_source",
    )
    STREAMED_IF_SET: ClassVar[Tuple[str, ...]] = ("categories_source",)
    STREAMED_IF_FILLED: ClassVar[Tuple[str, ...]] = ("service_categories", "service_domains", "source_label_ids")

    service_categories: List[str] = Field(default_factory=list, description="The taxonomy categories of the item.")
    service_domains: List[str] = Field(default_factory=list, description="The taxonomy domains of the item.")
    source_label_ids: List[int] = Field(default_factory=list, description="The identifiers of its source labels.")
    categories_source: Optional[CategorySource] = Field(default=None, description="What gave the item its categories.")

    @field_validator("service_categories", "service_domains", mode="before")
    def validate_slugs(cls, value: JsonValue) -> JsonValue:
        """Validate the raw slugs: blanks and duplicates dropped, a missing list read as empty.

        Args:
            value (JsonValue): The raw slugs.

        Returns:
            JsonValue: The slugs, in their order, each once (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(item.strip() if isinstance(item, str) else item for item in value if item != ""))
        return value

    @field_validator("source_label_ids", mode="before")
    def validate_source_label_ids(cls, value: JsonValue) -> JsonValue:
        """Validate the raw label identifiers: duplicates dropped, a missing list read as empty.

        Args:
            value (JsonValue): The raw identifiers.

        Returns:
            JsonValue: The identifiers, in their order, each once (checked by pydantic afterwards).
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(value))
        return value

    @model_serializer(mode="wrap")
    def serialize_dates_last(self, handler: SerializerFunctionWrapHandler) -> Dict[str, Union[JsonValue, datetime]]:
        """Serialize the item with its categorization after its content, then its dates, for readable files.

        Args:
            handler (SerializerFunctionWrapHandler): The default serializer.

        Returns:
            Dict[str, Union[JsonValue, datetime]]: The serialized fields: the content, the categorization, the dates.
        """
        data: Dict[str, Union[JsonValue, datetime]] = handler(self)
        service = {key: data.pop(key) for key in self.SERVICE_FIELDS if key in data}
        dates = {key: data.pop(key) for key in DATE_FIELDS if key in data}
        return {**data, **service, **dates}

    ############################
    # Publicly Exposed Methods #
    ############################

    def name_and_description(self) -> Tuple[str, str]:
        """Get the texts the item is classified from.

        Returns:
            Tuple[str, str]: Its name and its description, empty for the base class.
        """
        return "", ""

    def raw_labels(self) -> List[str]:
        """Get the categories the provider files the item under, as it writes them.

        Returns:
            List[str]: The source labels, none for the base class.
        """
        return []

    def delivery_method(self) -> Optional[DeliveryMethod]:
        """Get how the item is delivered, which classifies a software nothing else classifies.

        Returns:
            Optional[DeliveryMethod]: The delivery method of a software, `None` for a catalogue product.
        """
        return None
