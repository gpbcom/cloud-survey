from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import (
    CloudProvider,
    DateCaveat,
    DeliveryMethod,
    SoftwareAudience,
    SoftwareCategory,
)
from models.storage.enums import ItemSort
from models.storage.filters.date_filter import DateFilter


class ItemQuery(BaseModel):
    """A page of stored items to read: the filters, the order and the page bounds.

    Attributes:
        providers (List[CloudProvider]): The cloud providers of the items, every provider when empty (unless
            `restrict_providers`).
        restrict_providers (bool): Whether `providers` applies even when empty (every provider excluded by the
            filters): the items of no provider then match. `False` reads an empty `providers` as every provider.
        search (Optional[str]): Text contained in the item name (or the software publisher), case-insensitive.
        search_description (bool): Whether the text is searched in the descriptions too (slower: not indexed).
        include_deleted (bool): Whether the items deleted from the websites are read too.
        categories (List[SoftwareCategory]): Software meant for one of these audiences only (ignored for the
            products).
        deliveries (List[DeliveryMethod]): Software delivered one of these ways only (ignored for the products).
        name (Optional[str]): Text contained in the item name only, case-insensitive.
        description (Optional[str]): Text contained in the item description only, case-insensitive.
        url (Optional[str]): Text contained in the item page address only, case-insensitive.
        publishers (List[str]): Software of one of these publishers only (ignored for the products).
        audiences (List[SoftwareAudience]): Items meant for one of these audiences only: developer tool only,
            end-user software only, or both (the products and the software).
        service_categories (List[str]): Items filed under one of these categories or domains of the unified taxonomy
            only (slugs, the products and the software).
        source_labels (List[int]): Items carrying one of these source labels (or one of their aliases) only.
        added (DateFilter): The filter on the date the items were added.
        updated (DateFilter): The filter on the date the items were last updated.
        deleted (DateFilter): The filter on the date the items were deleted (a bound reads the deleted items).
        approximate (Optional[bool]): The items with an approximate date (`True`), only exact ones (`False`), `None`
            for both.
        caveats (List[DateCaveat]): The items whose added or updated date has one of these caveats only.
        sort (ItemSort): The order of the items.
        descending (bool): Whether the order is reversed.
        offset (int): The number of items skipped.
        limit (int): The largest number of items read.
        with_total (bool): Whether the number of items matching the filters is counted too.
    """

    model_config = ConfigDict(frozen=True)

    providers: List[CloudProvider] = Field(default_factory=list, description="The cloud providers of the items.")
    restrict_providers: bool = Field(
        default=False, description="Whether `providers` applies even when empty: no provider then matches no item."
    )
    search: Optional[str] = Field(default=None, max_length=200, description="Text contained in the item name.")
    search_description: bool = Field(default=False, description="Whether the descriptions are searched too.")
    include_deleted: bool = Field(default=False, description="Whether the deleted items are read too.")
    categories: List[SoftwareCategory] = Field(default_factory=list, description="Software for these audiences.")
    deliveries: List[DeliveryMethod] = Field(default_factory=list, description="Software delivered these ways.")
    name: Optional[str] = Field(default=None, max_length=200, description="Text contained in the item name.")
    description: Optional[str] = Field(default=None, max_length=200, description="Text contained in the description.")
    url: Optional[str] = Field(default=None, max_length=200, description="Text contained in the item page address.")
    publishers: List[str] = Field(default_factory=list, description="Software of one of these publishers only.")
    audiences: List[SoftwareAudience] = Field(default_factory=list, description="Items for one of these audiences.")
    service_categories: List[str] = Field(
        default_factory=list, description="Items under one of these taxonomy categories or domains only."
    )
    source_labels: List[int] = Field(default_factory=list, description="Items carrying one of these source labels.")
    added: DateFilter = Field(default_factory=DateFilter, description="The filter on the added date.")
    updated: DateFilter = Field(default_factory=DateFilter, description="The filter on the updated date.")
    deleted: DateFilter = Field(default_factory=DateFilter, description="The filter on the deletion date.")
    approximate: Optional[bool] = Field(default=None, description="The items with an approximate date, or not.")
    caveats: List[DateCaveat] = Field(default_factory=list, description="The items whose dates have these caveats.")
    sort: ItemSort = Field(default=ItemSort.ID, description="The order of the items.")
    descending: bool = Field(default=False, description="Whether the order is reversed.")
    offset: int = Field(default=0, ge=0, description="The number of items skipped.")
    limit: int = Field(default=200, ge=1, le=5000, description="The largest number of items read.")
    with_total: bool = Field(default=True, description="Whether the matching items are counted too.")

    @field_validator("search", "name", "description", "url", mode="before")
    def validate_search(cls, value: JsonValue) -> JsonValue:
        """Validate the raw searched texts.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text with collapsed spaces, `None` when missing or blank.
        """
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value

    @field_validator(
        "publishers",
        "service_categories",
        mode="before",
    )
    def validate_labels(cls, value: JsonValue) -> JsonValue:
        """Validate the raw lists of labels (publishers, taxonomy slugs).

        Args:
            value (JsonValue): The raw labels.

        Returns:
            JsonValue: The trimmed labels, the blank ones dropped.
        """
        if isinstance(value, list):
            labels = [label.strip() if isinstance(label, str) else label for label in value]
            return [label for label in labels if label != ""]
        return value

    @field_validator("source_labels", mode="before")
    def validate_source_labels(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source label identifiers.

        Args:
            value (JsonValue): The raw identifiers.

        Returns:
            JsonValue: The identifiers, each once, in their order (checked by pydantic afterwards).
        """
        if isinstance(value, list):
            return list(dict.fromkeys(value))
        return value

    def page(self, offset: int, limit: Optional[int] = None) -> ItemQuery:
        """Get the same query for another page.

        Args:
            offset (int): The number of items skipped.
            limit (Optional[int]): The largest number of items read, unchanged by default.

        Returns:
            ItemQuery: The query of the page.
        """
        return self.model_copy(update={"offset": offset, "limit": self.limit if limit is None else limit})
