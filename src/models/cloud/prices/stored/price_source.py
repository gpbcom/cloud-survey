from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider, PriceSourceStatus
from models.cloud.prices.exception import (
    InvalidEtagError,
    InvalidFetchedAtError,
    InvalidLastModifiedError,
    InvalidProviderError,
    InvalidRowsError,
    InvalidSourceKeyError,
    InvalidStatusError,
    InvalidVersionError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class PriceSource(BaseModel):
    """A source of prices of a provider (an offer file, an API listing, a pricing page), as last read.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        provider (CloudProvider): The cloud provider.
        source_key (str): The source, its URL or offer code.
        version (Optional[str]): The version the source states, if any.
        etag (Optional[str]): Its `ETag`, if any.
        last_modified (Optional[str]): Its `Last-Modified`, if any.
        fetched_at (Optional[datetime]): When it was read last, set when it is written.
        rows (int): The prices it gave.
        status (PriceSourceStatus): The outcome of the last read.

    Notes:
        A source unchanged since its last read (same version, `ETag` or `Last-Modified`) is not read again: its
        stored prices stay current, which keeps a crawl of an unchanged price list to a few requests.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The cloud provider.")
    source_key: str = Field(description="The source.")
    version: Optional[str] = Field(default=None, description="Its version.")
    etag: Optional[str] = Field(default=None, description="Its ETag.")
    last_modified: Optional[str] = Field(default=None, description="Its Last-Modified.")
    fetched_at: Optional[datetime] = Field(default=None, description="When it was read last.")
    rows: int = Field(default=0, description="The prices it gave.")
    status: PriceSourceStatus = Field(default=PriceSourceStatus.FETCHED, description="The outcome of the last read.")

    @field_validator("provider", mode="before")
    def validate_provider(cls, value: RawValue) -> RawValue:
        """Validate the raw cloud provider: a `CloudProvider` value.

        Args:
            value (RawValue): The raw cloud provider.

        Returns:
            RawValue: The checked cloud provider.

        Raises:
            InvalidProviderError: If it is not a `CloudProvider` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in CloudProvider])
        except PriceCheckError as e:
            raise InvalidProviderError(e.value, e.expected) from e

    @field_validator("source_key", mode="before")
    def validate_source_key(cls, value: RawValue) -> RawValue:
        """Validate the raw price source key: a text of 1 to 1000 characters.

        Args:
            value (RawValue): The raw price source key.

        Returns:
            RawValue: The checked price source key.

        Raises:
            InvalidSourceKeyError: If it is not a text of 1 to 1000 characters.
        """
        try:
            return cls.CHECK.text(value, 1000, collapse=False)
        except PriceCheckError as e:
            raise InvalidSourceKeyError(e.value, e.expected) from e

    @field_validator("version", mode="before")
    def validate_version(cls, value: RawValue) -> RawValue:
        """Validate the raw source version: a text of 1 to 200 characters, or nothing.

        Args:
            value (RawValue): The raw source version.

        Returns:
            RawValue: The checked source version.

        Raises:
            InvalidVersionError: If it is not a text of 1 to 200 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 200, optional=True, collapse=False)
        except PriceCheckError as e:
            raise InvalidVersionError(e.value, e.expected) from e

    @field_validator("etag", mode="before")
    def validate_etag(cls, value: RawValue) -> RawValue:
        """Validate the raw ETag: a text of 1 to 200 characters, or nothing.

        Args:
            value (RawValue): The raw ETag.

        Returns:
            RawValue: The checked ETag.

        Raises:
            InvalidEtagError: If it is not a text of 1 to 200 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 200, optional=True, collapse=False)
        except PriceCheckError as e:
            raise InvalidEtagError(e.value, e.expected) from e

    @field_validator("last_modified", mode="before")
    def validate_last_modified(cls, value: RawValue) -> RawValue:
        """Validate the raw Last-Modified: a text of 1 to 100 characters, or nothing.

        Args:
            value (RawValue): The raw Last-Modified.

        Returns:
            RawValue: The checked Last-Modified.

        Raises:
            InvalidLastModifiedError: If it is not a text of 1 to 100 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 100, optional=True)
        except PriceCheckError as e:
            raise InvalidLastModifiedError(e.value, e.expected) from e

    @field_validator("fetched_at", mode="before")
    def validate_fetched_at(cls, value: RawValue) -> RawValue:
        """Validate the raw fetch time: a date and time with its time zone, or nothing.

        Args:
            value (RawValue): The raw fetch time.

        Returns:
            RawValue: The checked fetch time.

        Raises:
            InvalidFetchedAtError: If it is not a date and time with its time zone, or nothing.
        """
        try:
            return cls.CHECK.moment(value)
        except PriceCheckError as e:
            raise InvalidFetchedAtError(e.value, e.expected) from e

    @field_validator("rows", mode="before")
    def validate_rows(cls, value: RawValue) -> RawValue:
        """Validate the raw row count: a whole number from 0.

        Args:
            value (RawValue): The raw row count.

        Returns:
            RawValue: The checked row count.

        Raises:
            InvalidRowsError: If it is not a whole number from 0.
        """
        try:
            return cls.CHECK.whole(value)
        except PriceCheckError as e:
            raise InvalidRowsError(e.value, e.expected) from e

    @field_validator("status", mode="before")
    def validate_status(cls, value: RawValue) -> RawValue:
        """Validate the raw source status: a `PriceSourceStatus` value.

        Args:
            value (RawValue): The raw source status.

        Returns:
            RawValue: The checked source status.

        Raises:
            InvalidStatusError: If it is not a `PriceSourceStatus` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceSourceStatus])
        except PriceCheckError as e:
            raise InvalidStatusError(e.value, e.expected) from e
