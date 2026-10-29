from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.prices.exception import (
    InvalidBatchRowsError,
    InvalidDownloadDirError,
    InvalidMaxConcurrencyError,
    InvalidMaxDiskMbError,
    InvalidMaxMemoryMbError,
    InvalidMaxRequestsPerHostError,
    InvalidMergeTimeoutSError,
    InvalidRequestDelayMsError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class PricesSettings(BaseModel):
    """The resource caps of the price crawl (the `prices` block of `conf/settings.yaml`).

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        max_memory_mb (int): The memory the crawl process may use, in MB: above it, its batches shrink.
        max_concurrency (int): The providers read at the same time.
        max_requests_per_host (int): The requests in flight to one host.
        batch_rows (int): The prices written at once.
        max_disk_mb (int): The disk the downloaded price files may take at once, in MB.
        download_dir (str): Where the price files are downloaded, the system temporary directory when empty.
        request_delay_ms (int): The wait between two requests to a price source, in milliseconds.
        merge_timeout_s (int): The longest a database statement of the price crawl may run, in seconds (the merge of
            a large provider writes millions of rows at once).

    Notes:
        The crawl never takes the whole machine: it streams the large price lists to disk and parses them row by
        row, writes them by batches, and slows down rather than grow past its memory cap.
        The price sources are read politely rather than by their `robots.txt` (several providers disallow their
        public price APIs to every robot): one request at a time per crawler, `request_delay_ms` apart.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_memory_mb: int = Field(default=1024, description="The memory the crawl may use, in MB.")
    max_concurrency: int = Field(default=4, description="The providers read at the same time.")
    max_requests_per_host: int = Field(default=2, description="The requests in flight to one host.")
    batch_rows: int = Field(default=10000, description="The prices written at once.")
    max_disk_mb: int = Field(default=4096, description="The disk the downloaded files may take, in MB.")
    download_dir: str = Field(default="", description="Where the price files are downloaded.")
    request_delay_ms: int = Field(default=2000, description="The wait between two price requests, in ms.")
    merge_timeout_s: int = Field(default=3600, description="The longest a price crawl statement may run, in s.")

    @field_validator("max_memory_mb", mode="before")
    def validate_max_memory_mb(cls, value: RawValue) -> RawValue:
        """Validate the raw memory cap: a whole number of 128 MB or more.

        Args:
            value (RawValue): The raw memory cap.

        Returns:
            RawValue: The checked memory cap.

        Raises:
            InvalidMaxMemoryMbError: If it is not a whole number of 128 MB or more.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidMaxMemoryMbError(e.value, e.expected) from e
        if checked is None or checked < 128:
            raise InvalidMaxMemoryMbError(repr(value), "128 MB or more")
        return checked

    @field_validator("max_concurrency", mode="before")
    def validate_max_concurrency(cls, value: RawValue) -> RawValue:
        """Validate the raw provider concurrency: a whole number from 1 to 16.

        Args:
            value (RawValue): The raw concurrency.

        Returns:
            RawValue: The checked concurrency.

        Raises:
            InvalidMaxConcurrencyError: If it is not a whole number from 1 to 16.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidMaxConcurrencyError(e.value, e.expected) from e
        if checked is None or checked > 16:
            raise InvalidMaxConcurrencyError(repr(value), "a whole number from 1 to 16")
        return checked

    @field_validator("max_requests_per_host", mode="before")
    def validate_max_requests_per_host(cls, value: RawValue) -> RawValue:
        """Validate the raw requests per host: a whole number from 1 to 8.

        Args:
            value (RawValue): The raw requests per host.

        Returns:
            RawValue: The checked requests per host.

        Raises:
            InvalidMaxRequestsPerHostError: If it is not a whole number from 1 to 8.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidMaxRequestsPerHostError(e.value, e.expected) from e
        if checked is None or checked > 8:
            raise InvalidMaxRequestsPerHostError(repr(value), "a whole number from 1 to 8")
        return checked

    @field_validator("batch_rows", mode="before")
    def validate_batch_rows(cls, value: RawValue) -> RawValue:
        """Validate the raw batch size: a whole number from 100 to 100,000.

        Args:
            value (RawValue): The raw batch size.

        Returns:
            RawValue: The checked batch size.

        Raises:
            InvalidBatchRowsError: If it is not a whole number from 100 to 100,000.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidBatchRowsError(e.value, e.expected) from e
        if checked is None or not 100 <= checked <= 100_000:
            raise InvalidBatchRowsError(repr(value), "a whole number from 100 to 100,000")
        return checked

    @field_validator("max_disk_mb", mode="before")
    def validate_max_disk_mb(cls, value: RawValue) -> RawValue:
        """Validate the raw disk cap: a whole number of 256 MB or more.

        Args:
            value (RawValue): The raw disk cap.

        Returns:
            RawValue: The checked disk cap.

        Raises:
            InvalidMaxDiskMbError: If it is not a whole number of 256 MB or more.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidMaxDiskMbError(e.value, e.expected) from e
        if checked is None or checked < 256:
            raise InvalidMaxDiskMbError(repr(value), "256 MB or more")
        return checked

    @field_validator("download_dir", mode="before")
    def validate_download_dir(cls, value: RawValue) -> RawValue:
        """Validate the raw download directory: a path of at most 500 characters, or empty.

        Args:
            value (RawValue): The raw directory.

        Returns:
            RawValue: The checked directory, empty for the system temporary directory.

        Raises:
            InvalidDownloadDirError: If it is not a text of at most 500 characters.
        """
        try:
            return cls.CHECK.text(value, 500, minimum=0, collapse=False) or ""
        except PriceCheckError as e:
            raise InvalidDownloadDirError(e.value, e.expected) from e

    @field_validator("request_delay_ms", mode="before")
    def validate_request_delay_ms(cls, value: RawValue) -> RawValue:
        """Validate the raw request delay: a whole number of milliseconds from 500 to 60,000.

        Args:
            value (RawValue): The raw request delay.

        Returns:
            RawValue: The checked request delay.

        Raises:
            InvalidRequestDelayMsError: If it is not a whole number from 500 to 60,000.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidRequestDelayMsError(e.value, e.expected) from e
        if checked is None or not 500 <= checked <= 60_000:
            raise InvalidRequestDelayMsError(repr(value), "a whole number of milliseconds from 500 to 60,000")
        return checked

    @field_validator("merge_timeout_s", mode="before")
    def validate_merge_timeout_s(cls, value: RawValue) -> RawValue:
        """Validate the raw merge timeout: a whole number of seconds from 60 to 7,200.

        Args:
            value (RawValue): The raw merge timeout.

        Returns:
            RawValue: The checked merge timeout.

        Raises:
            InvalidMergeTimeoutSError: If it is not a whole number from 60 to 7,200.
        """
        try:
            checked = cls.CHECK.whole(value, positive=True)
        except PriceCheckError as e:
            raise InvalidMergeTimeoutSError(e.value, e.expected) from e
        if checked is None or not 60 <= checked <= 7200:
            raise InvalidMergeTimeoutSError(repr(value), "a whole number of seconds from 60 to 7,200")
        return checked
