from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class HuaweiProductSection(StrEnum):
    """Enums representing the sections of the Huawei Cloud products page which are not categories.

    Attributes:
        FEATURED (str): The featured products, also listed under their categories.
    """

    FEATURED = "Featured"


@unique
class HuaweiDocsCategory(StrEnum):
    """Enums representing the Huawei Cloud documentation categories which do not hold services.

    Attributes:
        SOLUTIONS (str): The solutions.
        CLOUD_TRANSFORMATION (str): The cloud adoption guides.
        CLOUD_ECOSYSTEM (str): The partner ecosystem.
        USER_SUPPORT (str): The user support pages.
        OTHERS (str): The miscellaneous documentation.
    """

    SOLUTIONS = "Solutions"
    CLOUD_TRANSFORMATION = "Cloud Transformation"
    CLOUD_ECOSYSTEM = "Cloud Ecosystem"
    USER_SUPPORT = "User Support"
    OTHERS = "Others"


@unique
class HuaweiDocsCode(StrEnum):
    """Enums representing the codes of the Huawei Cloud documentation entries which are guides, not services.

    Attributes:
        SDK (str): The SDK guide.
        API_SIGNING (str): The API request signing guide.
        SECURITY_INFO (str): The security notices.
    """

    SDK = "sdk"
    API_SIGNING = "apisign"
    SECURITY_INFO = "securityInfo"


@unique
class HuaweiDocsCatalogueField(StrEnum):
    """Enums representing the fields of the Huawei Cloud documentation catalogue JSON.

    Attributes:
        DATA (str): The list of the documentation categories.
    """

    DATA = "data"


@unique
class HuaweiDocsCategoryField(StrEnum):
    """Enums representing the fields of a Huawei Cloud documentation category.

    Attributes:
        NAME (str): The name of the category.
        PRODUCTS (str): The list of the documentation entries of the category.
    """

    NAME = "name"
    PRODUCTS = "products"


@unique
class HuaweiDocsEntryField(StrEnum):
    """Enums representing the fields of a Huawei Cloud documentation entry.

    Attributes:
        TITLE (str): The name of the documented service.
        URI (str): The link of the documentation of the service.
        CODE (str): The code of the entry.
        DESCRIPTION (str): The description of the service.
    """

    TITLE = "title"
    URI = "uri"
    CODE = "code"
    DESCRIPTION = "description"


@unique
class HuaweiMarketplaceHeader(StrEnum):
    """Enums representing the request headers sent to the Huawei Cloud KooGallery search API.

    Attributes:
        LANGUAGE (str): The language of the texts of the listings.
    """

    LANGUAGE = "x-language"


@unique
class HuaweiMarketplaceLanguage(StrEnum):
    """Enums representing the languages asked to the Huawei Cloud KooGallery search API.

    Attributes:
        ENGLISH (str): American English.
    """

    ENGLISH = "en-us"


@unique
class HuaweiMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Huawei Cloud KooGallery crawler.

    Attributes:
        PAGE (str): The page number of a search request, from 1.
    """

    PAGE = "page"


@unique
class HuaweiSearchParameter(StrEnum):
    """Enums representing the fields of the body of a Huawei Cloud KooGallery search request.

    Attributes:
        AGGREGATIONS (str): The aggregations asked, none.
        FILTER (str): The filters applied, none.
        FLOW_ID (str): The search flow.
        KEYWORD (str): The searched keyword, empty.
        LIMIT (str): The listings read per page.
        OFFSET (str): The position of the first listing of the page.
    """

    AGGREGATIONS = "aggs"
    FILTER = "filter"
    FLOW_ID = "flow_id"
    KEYWORD = "keyword"
    LIMIT = "limit"
    OFFSET = "offset"


@unique
class HuaweiSearchFlow(StrEnum):
    """Enums representing the search flows of the Huawei Cloud KooGallery search API.

    Attributes:
        MARKETPLACE (str): The search of the marketplace pages.
    """

    MARKETPLACE = "101002"


@unique
class HuaweiSearchPageField(StrEnum):
    """Enums representing the fields of a Huawei Cloud KooGallery search page.

    Attributes:
        TOTAL (str): The total number of listings.
        PAGINATION (str): The page of listings.
        ITEMS (str): The listings of the page, within the pagination.
    """

    TOTAL = "total"
    PAGINATION = "pagination"
    ITEMS = "items"


@unique
class HuaweiListingField(StrEnum):
    """Enums representing the fields of a Huawei Cloud KooGallery listing.

    Attributes:
        TITLE (str): The English title of the listing.
        ABSTRACT (str): The English abstract of the listing.
        PUBLISHER (str): The publisher of the listing.
        CATEGORY (str): The English name of the top category.
        SUBCATEGORY (str): The English name of the sub-category.
        DELIVERY_CODE (str): The delivery code.
        DELIVERY_CODE_EN (str): The English delivery label.
        URL (str): The page link, relative to the marketplace website.
        LISTED_AT (str): The listing date, in epoch milliseconds.
        UPDATED_AT (str): The update date, in epoch milliseconds.
    """

    TITLE = "title"
    ABSTRACT = "content_abstract"
    PUBLISHER = "corporation_name"
    CATEGORY = "type_name_en"
    SUBCATEGORY = "content_type_desc_en"
    DELIVERY_CODE = "delivery_code"
    DELIVERY_CODE_EN = "delivery_code_en"
    URL = "url"
    LISTED_AT = "onshelf_time"
    UPDATED_AT = "update_time"


@unique
class HuaweiMarketplaceCategory(StrEnum):
    """Enums representing the Huawei Cloud KooGallery top categories which hold no software, casefolded.

    Attributes:
        PROFESSIONAL_SERVICES (str): The professional services.
        HARDWARE (str): The hardware.
        DATA (str): The data products.
    """

    PROFESSIONAL_SERVICES = "professional services"
    HARDWARE = "hardware"
    DATA = "data"


@unique
class HuaweiDelivery(StrEnum):
    """Enums representing the Huawei Cloud KooGallery delivery codes and English labels, casefolded.

    Attributes:
        MANUAL_SERVICE (str): A service delivered by hand (code).
        SERVICE (str): A service (label).
        PROFESSIONAL_SERVICES (str): Professional services (label).
        HARDWARE (str): Hardware (label).
        LICENSE (str): A license to download.
        VM_IMAGE (str): A virtual machine image (code).
        IMAGE (str): A virtual machine image (label).
        CLOUD_SERVER (str): A cloud server image (label).
        SAAS (str): A software as a service.
    """

    MANUAL_SERVICE = "manual.service"
    SERVICE = "service"
    PROFESSIONAL_SERVICES = "professional services"
    HARDWARE = "hardware"
    LICENSE = "license"
    VM_IMAGE = "vm.image"
    IMAGE = "image"
    CLOUD_SERVER = "cloud server"
    SAAS = "saas"


@unique
class HuaweiPriceField(StrEnum):
    """Enums representing the fields of the Huawei Cloud price calculator API, read for the prices.

    Attributes:
        MENU_INFOS (str): The categories of the calculator menu.
        PARENT_CATEGORY_NAME (str): The name of a category, e.g. `Compute`.
        SUB_CATEGORY_LISTS (str): Its services.
        CATEGORY_NAME (str): The name of a service, e.g. `Elastic Cloud Server`.
        URL_PATH (str): Its code in the calculator, e.g. `ecs`.
        HAS_CALCULATOR (str): Whether it has a calculator (its prices).
        REGION_ONLINE (str): Its regions.
        REGION_LIST (str): The list of its regions.
        PRODUCT (str): The priced resources of a service in a region, by kind.
        RESOURCE_TYPE (str): The type of a resource, e.g. `hws.resource.type.volume`.
        RESOURCE_SPEC_CODE (str): Its specification, e.g. `m9.6xlarge.8.linux`.
        PRODUCT_SPEC_SYS_DESC (str): Its specification written out (`Memory:196608MB`, `vCPUs:24CORE`, …,
            semicolon-separated).
        PLAN_LIST (str): Its prices.
        BILLING_MODE (str): How a price is charged (`ONDEMAND`, `MONTHLY`, `YEARLY`, `RI`).
        PERIOD_NUM (str): The periods of a subscription.
        MEASURE_UNIT (str): The unit of an on-demand price (a measure identifier).
        AMOUNT (str): The price.
        AMOUNT_TYPE (str): The kind of amount of a reserved price.
        PAYMENT_TYPE_KEY (str): The payment of a reserved price, e.g. `NO_UPFRONT`.
        PLAN_ID (str): The plan of a reserved price.
        PRODUCT_ID (str): The offer of a price.
        USAGE_FACTOR (str): What a usage plan measures, e.g. `upflow` or `downflow` for a bandwidth.
        DIVISION_LIST (str): The tiers of a price.
        DIVISION (str): The bounds of a tier.
        BEGIN_VALUE (str): The quantity from which a tier applies.
        END_VALUE (str): The quantity up to which it applies (-1 without bound).
        BEGIN_UNIT (str): The measure code of the start of a tier.
        END_UNIT (str): The measure code of its end, another one when the tier spans two units (e.g. GB to TB).
    """

    MENU_INFOS = "menuInfos"
    PARENT_CATEGORY_NAME = "parentCategoryName"
    SUB_CATEGORY_LISTS = "subCategoryLists"
    CATEGORY_NAME = "categoryName"
    URL_PATH = "urlPath"
    HAS_CALCULATOR = "hasCalculator"
    REGION_ONLINE = "regionOnline"
    REGION_LIST = "regionList"
    PRODUCT = "product"
    RESOURCE_TYPE = "resourceType"
    RESOURCE_SPEC_CODE = "resourceSpecCode"
    PRODUCT_SPEC_SYS_DESC = "productSpecSysDesc"
    PLAN_LIST = "planList"
    BILLING_MODE = "billingMode"
    PERIOD_NUM = "periodNum"
    MEASURE_UNIT = "measureUnit"
    AMOUNT = "amount"
    AMOUNT_TYPE = "amountType"
    PAYMENT_TYPE_KEY = "paymentTypeKey"
    PLAN_ID = "planId"
    PRODUCT_ID = "productId"
    USAGE_FACTOR = "usageFactor"
    DIVISION_LIST = "divisionList"
    DIVISION = "division"
    BEGIN_VALUE = "beginValue"
    END_VALUE = "endValue"
    BEGIN_UNIT = "beginUnit"
    END_UNIT = "endUnit"


@unique
class HuaweiBillingMode(StrEnum):
    """Enums representing how a Huawei Cloud price is charged.

    Attributes:
        ON_DEMAND (str): Pay as you go.
        MONTHLY (str): A subscription by the month.
        YEARLY (str): A subscription by the year.
        RESERVED (str): A reserved instance.
    """

    ON_DEMAND = "ONDEMAND"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    RESERVED = "RI"


@unique
class HuaweiReservedAmount(StrEnum):
    """Enums representing the amounts of a Huawei Cloud reserved instance price.

    Attributes:
        UPFRONT (str): The upfront price.
        MONTHLY (str): The price per month.
        EFFECTIVE (str): The effective price per hour.
    """

    UPFRONT = "nodeData.price"
    MONTHLY = "nodeData.perPrice"
    EFFECTIVE = "nodeData.perEffectivePrice"
