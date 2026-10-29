from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.enums import PriceOrigin
from models.cloud.prices.exception import (
    InvalidDescriptionError,
    InvalidEditedError,
    InvalidItemsError,
    InvalidNameError,
    InvalidOriginError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue
from models.cloud.prices.profiles.usage_item import UsageItem


class UsageProfile(BaseModel):
    """A workload whose monthly cost is compared across the providers: its consumptions.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        name (str): The name of the profile, its key.
        description (str): What workload it stands for.
        items (List[UsageItem]): Its consumptions per month.
        origin (PriceOrigin): Who wrote it.
        edited (bool): Whether a person changed it.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="The name of the profile.")
    description: str = Field(default="", description="What workload it stands for.")
    items: List[UsageItem] = Field(default_factory=list, description="Its consumptions per month.")
    origin: PriceOrigin = Field(default=PriceOrigin.USER, description="Who wrote it.")
    edited: bool = Field(default=False, description="Whether a person changed it.")

    @field_validator("name", mode="before")
    def validate_name(cls, value: RawValue) -> RawValue:
        """Validate the raw profile name: a text of 1 to 120 characters.

        Args:
            value (RawValue): The raw profile name.

        Returns:
            RawValue: The checked profile name.

        Raises:
            InvalidNameError: If it is not a text of 1 to 120 characters.
        """
        try:
            return cls.CHECK.text(value, 120)
        except PriceCheckError as e:
            raise InvalidNameError(e.value, e.expected) from e

    @field_validator("description", mode="before")
    def validate_description(cls, value: RawValue) -> RawValue:
        """Validate the raw profile description: a text of 0 to 1000 characters.

        Args:
            value (RawValue): The raw profile description.

        Returns:
            RawValue: The checked profile description.

        Raises:
            InvalidDescriptionError: If it is not a text of 0 to 1000 characters.
        """
        try:
            return cls.CHECK.text(value, 1000, minimum=0)
        except PriceCheckError as e:
            raise InvalidDescriptionError(e.value, e.expected) from e

    @field_validator("items", mode="before")
    def validate_items(cls, value: RawValue) -> RawValue:
        """Validate the raw usage items: a list.

        Args:
            value (RawValue): The raw usage items.

        Returns:
            RawValue: The checked usage items.

        Raises:
            InvalidItemsError: If it is not a list.
        """
        try:
            return cls.CHECK.items(value)
        except PriceCheckError as e:
            raise InvalidItemsError(e.value, e.expected) from e

    @field_validator("origin", mode="before")
    def validate_origin(cls, value: RawValue) -> RawValue:
        """Validate the raw origin: a `PriceOrigin` value.

        Args:
            value (RawValue): The raw origin.

        Returns:
            RawValue: The checked origin.

        Raises:
            InvalidOriginError: If it is not a `PriceOrigin` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceOrigin])
        except PriceCheckError as e:
            raise InvalidOriginError(e.value, e.expected) from e

    @field_validator("edited", mode="before")
    def validate_edited(cls, value: RawValue) -> RawValue:
        """Validate the raw edited flag: true or false.

        Args:
            value (RawValue): The raw edited flag.

        Returns:
            RawValue: The checked edited flag.

        Raises:
            InvalidEditedError: If it is not true or false.
        """
        try:
            return cls.CHECK.flag(value)
        except PriceCheckError as e:
            raise InvalidEditedError(e.value, e.expected) from e
