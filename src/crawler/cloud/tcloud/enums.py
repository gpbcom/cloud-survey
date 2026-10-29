from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class TCloudRequestMeta(StrEnum):
    """Enums representing the request meta keys of the T Cloud Public marketplace crawler.

    Attributes:
        CATEGORIES (str): Marks the categories API request.
    """

    CATEGORIES = "categories"


@unique
class TCloudApiField(StrEnum):
    """Enums representing the keys of the T Cloud Public marketplace API objects (categories and products).

    Attributes:
        ID (str): The identifier of a category or a product.
        NAME (str): The name of a category, a product or a seller.
        CATEGORIES (str): The category identifiers of a product.
        DESCRIPTION_SHORT (str): The short description of a product.
        DESCRIPTION (str): The long (HTML) description of a product.
        SELLER (str): The seller object of a product.
        TYPE (str): The type of a product, giving its delivery method.
        CREATED_AT (str): The listing date of a product.
    """

    ID = "id"
    NAME = "name"
    CATEGORIES = "categories"
    DESCRIPTION_SHORT = "description_short"
    DESCRIPTION = "description"
    SELLER = "seller"
    TYPE = "type"
    CREATED_AT = "created_at"


@unique
class TCloudServiceCategory(StrEnum):
    """Enums representing the T Cloud Public marketplace categories of the professional services offers.

    Attributes:
        ADVISORY_ASSESSMENT (str): The advisory and assessment offers.
        BUILD_MIGRATE (str): The build and migration offers.
        OPTIMIZE_SECURE (str): The optimization and security offers.
    """

    ADVISORY_ASSESSMENT = "Advisory & Assessment"
    BUILD_MIGRATE = "Build & Migrate"
    OPTIMIZE_SECURE = "Optimize & Secure"


@unique
class TCloudServiceSeller(StrEnum):
    """Enums representing the T Cloud Public marketplace sellers of professional services only.

    Attributes:
        T_SYSTEMS_PROFESSIONAL_SERVICES (str): The T-Systems cloud professional services.
    """

    T_SYSTEMS_PROFESSIONAL_SERVICES = "T-Systems | Cloud Professional Services"


@unique
class TCloudProductType(StrEnum):
    """Enums representing the T Cloud Public marketplace product types.

    Attributes:
        LEAD_GENERATION (str): A software sold by the vendor itself, delivered as a service.
        CONTAINER (str): A container image.
        LLM_TPM (str): A large language model billed by tokens per minute.
    """

    LEAD_GENERATION = "lead-generation"
    CONTAINER = "container"
    LLM_TPM = "llm-tpm"


@unique
class TCloudPriceField(StrEnum):
    """Enums representing the fields of the T Cloud Public price API, read for the prices.

    Attributes:
        RESPONSE (str): The response.
        RESULT (str): The prices of a page, by service.
        STATS (str): The counts of the listing.
        MAX_PAGES (str): Its pages.
        ID (str): The identifier of a price, its region included, unique.
        ID_GROUP_TIERED (str): The group of the tiers of a tiered price.
        PRODUCT_ID (str): The service, e.g. `API Gateway`.
        OPI_FLAVOUR (str): The flavor, e.g. `s3.large.2`.
        PRODUCT_NAME (str): The name of the priced product.
        OS_UNIT (str): Its operating system, e.g. `Standard`, `Windows`.
        PRICE_AMOUNT (str): The price, as text, e.g. `0.117000 EUR`.
        UNIT (str): What the price is per, e.g. `h`, `GB/month`.
        VCPU (str): The vCPUs.
        RAM (str): The memory, e.g. `8 GiB`.
        PRODUCT_FAMILY (str): The family, e.g. `Application`.
        PRODUCT_SECTION (str): The priced part, e.g. `main`, `storage`.
        FROM_ON (str): The quantity from which a tier applies.
        UP_TO (str): The quantity up to which it applies.
        REGION (str): The region, e.g. `eu-de`.
        RESERVED_12 (str): The monthly price reserved for 12 months.
        RESERVED_24 (str): The monthly price reserved for 24 months.
        RESERVED_36 (str): The monthly price reserved for 36 months.
        UPFRONT_12 (str): The monthly price reserved for 12 months, paid upfront.
        UPFRONT_24 (str): The monthly price reserved for 24 months, paid upfront.
        UPFRONT_36 (str): The monthly price reserved for 36 months, paid upfront.
    """

    RESPONSE = "response"
    RESULT = "result"
    STATS = "stats"
    MAX_PAGES = "maxPages"
    ID = "id"
    ID_GROUP_TIERED = "idGroupTiered"
    PRODUCT_ID = "productId"
    OPI_FLAVOUR = "opiFlavour"
    PRODUCT_NAME = "productName"
    OS_UNIT = "osUnit"
    PRICE_AMOUNT = "priceAmount"
    UNIT = "unit"
    VCPU = "vCpu"
    RAM = "ram"
    PRODUCT_FAMILY = "productFamily"
    PRODUCT_SECTION = "productSection"
    FROM_ON = "fromOn"
    UP_TO = "upTo"
    REGION = "region"
    RESERVED_12 = "R12"
    RESERVED_24 = "R24"
    RESERVED_36 = "R36"
    UPFRONT_12 = "RU12"
    UPFRONT_24 = "RU24"
    UPFRONT_36 = "RU36"


@unique
class TCloudPriceUnit(StrEnum):
    """Enums representing the units the T Cloud Public prices are per.

    Attributes:
        HOUR (str): An hour.
        HOUR_PER_MONTH (str): An hour (billed monthly).
        MONTH (str): A month.
        GB (str): A GB.
        GB_MONTH (str): A GB for a month.
        REQUEST (str): A request.
        RESTORE (str): A restore.
        MILLION_ITEMS_MONTH (str): A million items a month.
        ITEM_MONTH (str): An item for a month.
        RULES_HOUR (str): A rule for an hour.
        MBIT_HOUR (str): A Mbit/s for an hour.
        REQUESTS (str): A request.
        THOUSAND_REQUESTS (str): A thousand requests.
        CORES_BROKERS_HOUR (str): A core of a broker for an hour.
        GB_MONTH_CAPITAL (str): A GB for a month.
        LCU_HOUR_ZONE (str): A load balancer capacity unit for an hour, per zone.
        PIECE (str): A piece.
        PIECES (str): Pieces.
        GB_HOURS (str): A GB for an hour.
        ITEM_ONE_TIME (str): An item, once.
    """

    HOUR = "h"
    HOUR_PER_MONTH = "h/month"
    MONTH = "month"
    GB = "GB"
    GB_MONTH = "GB/month"
    REQUEST = "Request"
    RESTORE = "Restore"
    MILLION_ITEMS_MONTH = "Item pro 1.000.000/month"
    ITEM_MONTH = "Item/month"
    RULES_HOUR = "rules/h"
    MBIT_HOUR = "Mbit/h"
    REQUESTS = "Requests"
    THOUSAND_REQUESTS = "1000 Requests"
    CORES_BROKERS_HOUR = "Cores/Brokers/h"
    GB_MONTH_CAPITAL = "GB/Month"
    LCU_HOUR_ZONE = "LCU/h/zone"
    PIECE = "pc"
    PIECES = "pcs"
    GB_HOURS = "GB hours"
    ITEM_ONE_TIME = "Item/ot"
