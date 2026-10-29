from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class StackitProductField(StrEnum):
    """Enums representing the fields of the STACKIT marketplace API responses and products.

    Attributes:
        ITEMS (str): The products of a listing page.
        TOTAL_COUNT (str): The number of products of the listing.
        CURSOR (str): The cursor of the next listing page.
        PRODUCT_ID (str): The product identifier.
        NAME (str): The name of a product or of its vendor.
        DELIVERY_METHOD (str): The delivery method of a product.
        SUMMARY (str): The product description.
        VENDOR (str): The product vendor, the publisher.
        CATEGORIES (str): The category labels of a product detail.
    """

    ITEMS = "items"
    TOTAL_COUNT = "totalCount"
    CURSOR = "cursor"
    PRODUCT_ID = "productId"
    NAME = "name"
    DELIVERY_METHOD = "deliveryMethod"
    SUMMARY = "summary"
    VENDOR = "vendor"
    CATEGORIES = "categories"


@unique
class StackitDeliveryMethod(StrEnum):
    """Enums representing the delivery methods of the STACKIT marketplace products.

    Attributes:
        SAAS (str): A software as a service.
        CONTAINER_IMAGE (str): A container image.
        CLOUD_IMAGE (str): A virtual machine image.
        PROFESSIONAL_SERVICE (str): A professional service, not a software.
    """

    SAAS = "SAAS"
    CONTAINER_IMAGE = "CONTAINER_IMAGE"
    CLOUD_IMAGE = "CLOUD_IMAGE"
    PROFESSIONAL_SERVICE = "PROFESSIONAL_SERVICE"


@unique
class StackitRequestMeta(StrEnum):
    """Enums representing the meta keys of the STACKIT marketplace API requests.

    Attributes:
        PAGE (str): The number of a listing page.
        PRODUCT (str): Marks a product detail request, holding the product identifier.
    """

    PAGE = "page"
    PRODUCT = "product"


@unique
class StackitReleaseNoteAttribute(StrEnum):
    """Enums representing the HTML attributes read on the STACKIT release notes page.

    Attributes:
        DATETIME (str): The ISO date of a release note, on its `time` element.
    """

    DATETIME = "datetime"


@unique
class StackitLaunchKeyword(StrEnum):
    """Enums representing the words of a STACKIT release note title announcing a product launch.

    Attributes:
        GA (str): The general availability abbreviation.
        GENERAL_AVAILABILITY (str): The general availability.
        GENERALLY_AVAILABLE (str): Generally available.
        BETA (str): A beta release.
        PUBLIC_PREVIEW (str): A public preview.
        LAUNCH (str): A launch.
        LAUNCHES (str): Launches.
        LAUNCHED (str): Launched.
        NOW_AVAILABLE (str): Now available.
        NEWLY_AVAILABLE (str): Newly available.
        RELEASE (str): A release.
    """

    GA = "GA"
    GENERAL_AVAILABILITY = "general availability"
    GENERALLY_AVAILABLE = "generally available"
    BETA = "beta"
    PUBLIC_PREVIEW = "public preview"
    LAUNCH = "launch"
    LAUNCHES = "launches"
    LAUNCHED = "launched"
    NOW_AVAILABLE = "now available"
    NEWLY_AVAILABLE = "newly available"
    RELEASE = "release"


@unique
class StackitNotLaunchMarker(StrEnum):
    """Enums representing the patterns of a STACKIT release note title which is not a product launch.

    Attributes:
        DEPRECATION (str): A deprecation, e.g. `Kubernetes version 1.33 is getting deprecated`.
        END (str): The end of a phase or of a service, e.g. `End of public preview`.
        DISCONTINUATION (str): A discontinuation.
        REMOVAL (str): A removal.
        DOCUMENTATION (str): A documentation release, ahead of the product.
        MODEL_RELEASE (str): A new model of a model serving product.
        VERSION_RELEASE (str): A version release, e.g. `Release 1.4.0 of KACLS`.
        EXTENSION (str): A product made available with a feature, in a region, on machines or via an interface,
            e.g. `MariaDB is now available with SSL`, a beta or a preview excepted.
    """

    DEPRECATION = r"deprecat"
    END = r"end\s+of\b"
    DISCONTINUATION = r"discontinu"
    REMOVAL = r"remov"
    DOCUMENTATION = r"documentation\b"
    MODEL_RELEASE = r"model\s+release\b"
    VERSION_RELEASE = r"release\s+v?\d"
    EXTENSION = r"available\s+(?:with|in|on|via|for|through)\s+(?!beta\b|public\s+preview\b|preview\b)"


@unique
class StackitSkuField(StrEnum):
    """Enums representing the fields of the STACKIT price list API (PIM SKUs), read for the prices.

    Attributes:
        SERVICES (str): The SKUs of the price list.
        LAST_UPDATED_AT (str): When the price list last changed (its version).
        SKU (str): The SKU, e.g. `ST-0199290`.
        NAME (str): Its name, e.g. `Advanced Support-GLOBAL`.
        REGION (str): Its region (`eu01`, `eu02`, `global`).
        CATEGORY (str): Its category, e.g. `Compute Engine`.
        PRODUCT (str): Its service, e.g. `Help Center`.
        UNIT (str): Its unit, e.g. `Hours`.
        UNIT_BILLING (str): What its price is per, e.g. `per vCPU/hour`.
        PRICE (str): Its price, as text.
        MATURITY (str): Its maturity (`ga`, `beta`, `deprecated`).
        DEPRECATED (str): Whether it is deprecated (`Yes`, `No`).
        PRICE_LIST_VISIBILITY (str): Whether the public price list shows it (`Yes`, `No`).
        ATTRIBUTES (str): Its technical attributes.
    """

    SERVICES = "services"
    LAST_UPDATED_AT = "lastUpdatedAt"
    SKU = "sku"
    NAME = "name"
    REGION = "region"
    CATEGORY = "category"
    PRODUCT = "product"
    UNIT = "unit"
    UNIT_BILLING = "unitBilling"
    PRICE = "price"
    MATURITY = "maturityModelState"
    DEPRECATED = "deprecated"
    PRICE_LIST_VISIBILITY = "priceListVisibility"
    ATTRIBUTES = "attributes"


@unique
class StackitSkuAttribute(StrEnum):
    """Enums representing the technical attributes of a STACKIT SKU read as price fields.

    Attributes:
        VCPU (str): The virtual CPUs.
        RAM (str): The memory, in GB.
        FLAVOR (str): The machine flavor, e.g. `c1.1`.
        OS (str): The operating system.
        TIER_MIN_VALUE (str): The least quantity of a band price (e.g. the vCPUs of a license).
        TIER_MAX_VALUE (str): The most quantity of a band price.
        CF_UNIQUE_IDS (str): The billing identifiers (the SKU again, not kept).
    """

    VCPU = "vCPU"
    RAM = "ram"
    FLAVOR = "flavor"
    OS = "os"
    TIER_MIN_VALUE = "tierMinValue"
    TIER_MAX_VALUE = "tierMaxValue"
    CF_UNIQUE_IDS = "cfUniqueIds"


@unique
class StackitUnitBilling(StrEnum):
    """Enums representing what the prices of the STACKIT price list are per.

    Attributes:
        HOUR (str): An hour.
        DISK_HOUR (str): A disk for an hour.
        GB_HOUR (str): A GB for an hour.
        MONTH (str): A month.
        VCPU_HOUR (str): A vCPU for an hour.
        MB (str): A MB.
        VERSION_HOUR (str): A secret version for an hour.
        AMOUNT (str): A unit.
        INPUT_TOKENS (str): A million input tokens.
        OUTPUT_TOKENS (str): A million output tokens.
        SERVER_HOUR (str): A server for an hour.
        CLUSTER_HOUR (str): A cluster for an hour.
        GB_INGEST (str): A GB ingested.
        GB_RETENTION_DAY (str): A GB kept for a day.
        THOUSAND_REQUESTS (str): A thousand requests.
        MB_RAM_HOUR (str): A MB of memory for an hour.
        GB (str): A GB.
        NODE_HOUR (str): A node for an hour.
        KB (str): A KB.
        SECRET_HOUR (str): A secret for an hour.
        RUNTIME_MINUTE (str): A minute of runtime.
        USER_MONTH (str): A user for a month.
    """

    HOUR = "per hour"
    DISK_HOUR = "per disk/hour"
    GB_HOUR = "per GB/hour"
    MONTH = "per month"
    VCPU_HOUR = "per vCPU/hour"
    MB = "per MB"
    VERSION_HOUR = "per version/hour"
    AMOUNT = "per amount"
    INPUT_TOKENS = "mio input token"
    OUTPUT_TOKENS = "mio output token"
    SERVER_HOUR = "per server/hour"
    CLUSTER_HOUR = "per cluster/hour"
    GB_INGEST = "per GB ingest"
    GB_RETENTION_DAY = "per GB/days of retention"
    THOUSAND_REQUESTS = "per thousand Requests"
    MB_RAM_HOUR = "per Megabyte RAM/hour"
    GB = "per GB"
    NODE_HOUR = "per node/hour"
    KB = "per KB"
    SECRET_HOUR = "per secret/hour"
    RUNTIME_MINUTE = "minutes of runtime"
    USER_MONTH = "per user/month"
