from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, Optional

# Third Party Imports.
from pydantic import Field, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import PriceOrigin
from models.cloud.prices.exception import (
    InvalidEditedError,
    InvalidFingerprintError,
    InvalidIdError,
    InvalidOriginError,
    InvalidProductIdError,
    InvalidValidFromError,
    InvalidValidToError,
    PriceCheckError,
)
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class StoredPrice(ServicePrice):
    """A stored price: a price as published, for the time it applied.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        id (Optional[int]): The row identifier, `None` before it is written.
        product_id (Optional[int]): The catalogue product it prices, once linked.
        fingerprint (str): The hash of its fields, compared from crawl to crawl.
        origin (PriceOrigin): Who wrote it: a crawl or a person.
        edited (bool): Whether a person changed it (a crawl never replaces it).
        valid_from (Optional[datetime]): Since when it applies, set when it is written.
        valid_to (Optional[datetime]): Until when it applied, `None` while it is current.

    Notes:
        A change of a price closes its current row (`valid_to`) and opens a new one: the rows of a `sku_key` are its
        history.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    id: Optional[int] = Field(default=None, description="The row identifier.")
    product_id: Optional[int] = Field(default=None, description="The catalogue product it prices.")
    fingerprint: str = Field(description="The hash of its priced fields.")
    origin: PriceOrigin = Field(default=PriceOrigin.CRAWLER, description="Who wrote it.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
    valid_from: Optional[datetime] = Field(default=None, description="Since when it applies.")
    valid_to: Optional[datetime] = Field(default=None, description="Until when it applied.")

    @field_validator("id", mode="before")
    def validate_id(cls, value: RawValue) -> RawValue:
        """Validate the raw row identifier: a whole number above 0, or nothing.

        Args:
            value (RawValue): The raw row identifier.

        Returns:
            RawValue: The checked row identifier.

        Raises:
            InvalidIdError: If it is not a whole number above 0, or nothing.
        """
        try:
            return cls.CHECK.whole(value, positive=True, optional=True)
        except PriceCheckError as e:
            raise InvalidIdError(e.value, e.expected) from e

    @field_validator("product_id", mode="before")
    def validate_product_id(cls, value: RawValue) -> RawValue:
        """Validate the raw product identifier: a whole number above 0, or nothing.

        Args:
            value (RawValue): The raw product identifier.

        Returns:
            RawValue: The checked product identifier.

        Raises:
            InvalidProductIdError: If it is not a whole number above 0, or nothing.
        """
        try:
            return cls.CHECK.whole(value, positive=True, optional=True)
        except PriceCheckError as e:
            raise InvalidProductIdError(e.value, e.expected) from e

    @field_validator("fingerprint", mode="before")
    def validate_fingerprint(cls, value: RawValue) -> RawValue:
        """Validate the raw fingerprint: a text of 1 to 32 characters.

        Args:
            value (RawValue): The raw fingerprint.

        Returns:
            RawValue: The checked fingerprint.

        Raises:
            InvalidFingerprintError: If it is not a text of 1 to 32 characters.
        """
        try:
            return cls.CHECK.text(value, 32, collapse=False)
        except PriceCheckError as e:
            raise InvalidFingerprintError(e.value, e.expected) from e

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

    @field_validator("valid_from", mode="before")
    def validate_valid_from(cls, value: RawValue) -> RawValue:
        """Validate the raw validity start: a date and time with its time zone, or nothing.

        Args:
            value (RawValue): The raw validity start.

        Returns:
            RawValue: The checked validity start.

        Raises:
            InvalidValidFromError: If it is not a date and time with its time zone, or nothing.
        """
        try:
            return cls.CHECK.moment(value)
        except PriceCheckError as e:
            raise InvalidValidFromError(e.value, e.expected) from e

    @field_validator("valid_to", mode="before")
    def validate_valid_to(cls, value: RawValue, info: ValidationInfo) -> RawValue:
        """Validate the raw validity end: a date and time with its time zone, not before the validity start, or nothing.

        Args:
            value (RawValue): The raw validity end.
            info (ValidationInfo): The fields validated so far (the validity start).

        Returns:
            RawValue: The checked validity end.

        Raises:
            InvalidValidToError: If it is not a date and time with its time zone, or is before the validity start.
        """
        try:
            end = cls.CHECK.moment(value)
        except PriceCheckError as e:
            raise InvalidValidToError(e.value, e.expected) from e
        start = info.data.get("valid_from")
        if end is not None and isinstance(start, datetime) and end < start:
            raise InvalidValidToError(repr(value), f"a time from the validity start {start.isoformat()}")
        return end
