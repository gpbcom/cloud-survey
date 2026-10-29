from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar


class PriceModelError(ValueError):
    """Base class for every validation error of the price models (prices, free tiers, sources, profiles, quotes).

    Attributes:
        message (str): Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class PriceFieldError(PriceModelError):
    """Base class of the errors of one field of a price model: its value and what is expected.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
        value (str): The rejected value.
        expected (str): What is expected.
    """

    FIELD: ClassVar[str] = "field"

    def __init__(self, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected value.
            expected (str): What is expected.
        """
        self.value, self.expected = value[:200], expected
        super().__init__(f"The {self.FIELD} {self.value!r} is invalid: {expected} is expected.")


class PriceCheckError(PriceModelError):
    """Raised by a check of a raw field: each field's validator turns it into the error of that field.

    Attributes:
        value (str): The rejected value.
        expected (str): What is expected.
    """

    def __init__(self, value: str, expected: str) -> None:
        """Initialize the error.

        Args:
            value (str): The rejected value.
            expected (str): What is expected.
        """
        self.value, self.expected = value[:200], expected
        super().__init__(f"The value {self.value!r} is invalid: {expected} is expected.")


class InconsistentPriceError(PriceModelError):
    """Raised when the fields of a price contradict each other.

    Notes:
        A priced model needs a price and a currency, a service without public price needs no price and a reason.

    Attributes:
        sku_key (str): The priced dimension.
        reason (str): What contradicts what.
    """

    def __init__(self, sku_key: str, reason: str) -> None:
        """Initialize the error.

        Args:
            sku_key (str): The priced dimension.
            reason (str): What contradicts what.
        """
        self.sku_key, self.reason = sku_key, reason
        super().__init__(f"The price {sku_key!r} is inconsistent: {reason}.")


class InvalidProviderError(PriceFieldError):
    """Raised when the `provider` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "cloud provider"


class InvalidSkuKeyError(PriceFieldError):
    """Raised when the `sku_key` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "SKU key"


class InvalidServiceError(PriceFieldError):
    """Raised when the `service` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "service"


class InvalidFamilyError(PriceFieldError):
    """Raised when the `family` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "price family"


class InvalidRegionError(PriceFieldError):
    """Raised when the `region` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "region"


class InvalidInstanceTypeError(PriceFieldError):
    """Raised when the `instance_type` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "instance type"


class InvalidVcpuError(PriceFieldError):
    """Raised when the `vcpu` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "virtual CPU count"


class InvalidMemoryGibError(PriceFieldError):
    """Raised when the `memory_gib` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "memory"


class InvalidStorageGibError(PriceFieldError):
    """Raised when the `storage_gib` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "included storage"


class InvalidOsError(PriceFieldError):
    """Raised when the `os` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "operating system"


class InvalidAttributesError(PriceFieldError):
    """Raised when the `attributes` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "attributes"


class InvalidUnitError(PriceFieldError):
    """Raised when the `unit` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "unit"


class InvalidUnitRawError(PriceFieldError):
    """Raised when the `unit_raw` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "raw unit"


class InvalidUnitFactorError(PriceFieldError):
    """Raised when the `unit_factor` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "unit factor"


class InvalidPriceError(PriceFieldError):
    """Raised when the `price` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "price"


class InvalidCurrencyError(PriceFieldError):
    """Raised when the `currency` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "currency"


class InvalidModelError(PriceFieldError):
    """Raised when the `model` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "pricing model"


class InvalidTermError(PriceFieldError):
    """Raised when the `term` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "commitment term"


class InvalidTierStartError(PriceFieldError):
    """Raised when the `tier_start` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "tier start"


class InvalidTierEndError(PriceFieldError):
    """Raised when the `tier_end` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "tier end"


class InvalidBillingIncrementSError(PriceFieldError):
    """Raised when the `billing_increment_s` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "billing increment"


class InvalidMinimumQuantityError(PriceFieldError):
    """Raised when the `minimum_quantity` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "minimum quantity"


class InvalidMinimumDurationDaysError(PriceFieldError):
    """Raised when the `minimum_duration_days` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "minimum duration"


class InvalidEffectiveFromError(PriceFieldError):
    """Raised when the `effective_from` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "effective date"


class InvalidSourceUrlError(PriceFieldError):
    """Raised when the `source_url` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "source URL"


class InvalidSourceKindError(PriceFieldError):
    """Raised when the `source_kind` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "source kind"


class InvalidCapturedError(PriceFieldError):
    """Raised when the `captured` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "capture date"


class InvalidReasonError(PriceFieldError):
    """Raised when the `reason` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "reason"


class InvalidFreeKeyError(PriceFieldError):
    """Raised when the `free_key` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "free offer key"


class InvalidKindError(PriceFieldError):
    """Raised when the `kind` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "free offer kind"


class InvalidQuantityError(PriceFieldError):
    """Raised when the `quantity` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "quantity"


class InvalidPeriodError(PriceFieldError):
    """Raised when the `period` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "renewal period"


class InvalidDurationDaysError(PriceFieldError):
    """Raised when the `duration_days` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "duration"


class InvalidRegionScopeError(PriceFieldError):
    """Raised when the `region_scope` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "region scope"


class InvalidConditionsError(PriceFieldError):
    """Raised when the `conditions` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "conditions"


class InvalidIdError(PriceFieldError):
    """Raised when the `id` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "row identifier"


class InvalidProductIdError(PriceFieldError):
    """Raised when the `product_id` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "product identifier"


class InvalidFingerprintError(PriceFieldError):
    """Raised when the `fingerprint` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "fingerprint"


class InvalidOriginError(PriceFieldError):
    """Raised when the `origin` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "origin"


class InvalidEditedError(PriceFieldError):
    """Raised when the `edited` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "edited flag"


class InvalidValidFromError(PriceFieldError):
    """Raised when the `valid_from` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "validity start"


class InvalidValidToError(PriceFieldError):
    """Raised when the `valid_to` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "validity end"


class InvalidSourceKeyError(PriceFieldError):
    """Raised when the `source_key` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "price source key"


class InvalidVersionError(PriceFieldError):
    """Raised when the `version` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "source version"


class InvalidEtagError(PriceFieldError):
    """Raised when the `etag` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "ETag"


class InvalidLastModifiedError(PriceFieldError):
    """Raised when the `last_modified` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "Last-Modified"


class InvalidFetchedAtError(PriceFieldError):
    """Raised when the `fetched_at` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "fetch time"


class InvalidRowsError(PriceFieldError):
    """Raised when the `rows` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "row count"


class InvalidStatusError(PriceFieldError):
    """Raised when the `status` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "source status"


class InvalidLabelError(PriceFieldError):
    """Raised when the `label` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "usage label"


class InvalidConceptError(PriceFieldError):
    """Raised when the `concept` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "service concept"


class InvalidMinimumsError(PriceFieldError):
    """Raised when the `minimums` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "attribute minimums"


class InvalidNameError(PriceFieldError):
    """Raised when the `name` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "profile name"


class InvalidDescriptionError(PriceFieldError):
    """Raised when the `description` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "profile description"


class InvalidItemsError(PriceFieldError):
    """Raised when the `items` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "usage items"


class InvalidProfileError(PriceFieldError):
    """Raised when the `profile` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "quote profile"


class InvalidOptionsError(PriceFieldError):
    """Raised when the `options` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "costing options"


class InvalidMonthlyTotalError(PriceFieldError):
    """Raised when the `monthly_total` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "monthly total"


class InvalidBreakdownError(PriceFieldError):
    """Raised when the `breakdown` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "cost breakdown"


class InvalidComputedAtError(PriceFieldError):
    """Raised when the `computed_at` of a price model is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "computation time"


class InvalidMaxMemoryMbError(PriceFieldError):
    """Raised when the `max_memory_mb` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "memory cap"


class InvalidMaxConcurrencyError(PriceFieldError):
    """Raised when the `max_concurrency` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "provider concurrency"


class InvalidMaxRequestsPerHostError(PriceFieldError):
    """Raised when the `max_requests_per_host` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "requests per host"


class InvalidBatchRowsError(PriceFieldError):
    """Raised when the `batch_rows` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "batch size"


class InvalidMaxDiskMbError(PriceFieldError):
    """Raised when the `max_disk_mb` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "disk cap"


class InvalidDownloadDirError(PriceFieldError):
    """Raised when the `download_dir` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "download directory"


class InvalidRequestDelayMsError(PriceFieldError):
    """Raised when the `request_delay_ms` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "request delay"


class InvalidMergeTimeoutSError(PriceFieldError):
    """Raised when the `merge_timeout_s` of the price crawl settings is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "merge timeout"


class InvalidCoverageProductError(PriceFieldError):
    """Raised when the `product` of a coverage statement is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "covered product"


class InvalidCoverageModelError(PriceFieldError):
    """Raised when the `model` of a coverage statement is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage model"


class InvalidCoverageReasonError(PriceFieldError):
    """Raised when the `reason` of a coverage statement is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage reason"


class InvalidCoverageSourceError(PriceFieldError):
    """Raised when the `source` of a coverage statement is malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage evidence"


class InvalidCoverageLinksError(PriceFieldError):
    """Raised when the `links` of a coverage catalogue are malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage links"


class InvalidCoverageStatementsError(PriceFieldError):
    """Raised when the `statements` of a coverage catalogue are malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage statements"


class InvalidCoverageRowLinksError(PriceFieldError):
    """Raised when the `row_links` of a coverage catalogue are malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage row links"


class InvalidCoveragePagesError(PriceFieldError):
    """Raised when the `pages` of a coverage catalogue are malformed.

    Attributes:
        FIELD (ClassVar[str]): What the field is, in the message.
    """

    FIELD: ClassVar[str] = "coverage price pages"
