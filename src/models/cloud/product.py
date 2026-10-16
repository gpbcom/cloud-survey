from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

# Third Party Imports.
from pydantic import Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.cloud.exception import EmptyMandatoryFieldError, InvalidProductUrlError, MissingPricingPolicyError
from models.cloud.pricing import ServicePricingPolicy


class CloudProduct(DatedItem):
    """Class representing a cloud product extracted from a cloud provider.

    Attributes:
        name (str): The product service name.
        description (str): The product service description.
        pricing_policy (List[ServicePricingPolicy]): The pricing policies associated to the product.
        url (Optional[str]): The product page, an absolute http(s) link.
        added_at, added_from, updated_at, updated_from, deleted_at: The history dates (see `DatedItem`).
    """

    CONTENT_FIELDS: ClassVar[Tuple[str, ...]] = ("name", "description", "pricing_policy", "url")

    name: str = Field(description="Name of the cloud product.", max_length=200)
    description: str = Field(description="Description string for the cloud product.", max_length=1000)
    pricing_policy: List[ServicePricingPolicy] = Field(
        default_factory=list, description="The pricing policies associated to the product."
    )
    url: Optional[str] = Field(default=None, description="The product page, an absolute http(s) link.", max_length=2048)

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
            if link.scheme not in ("http", "https") or not link.netloc:
                raise InvalidProductUrlError(value)
            return value.strip()
        return value

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
