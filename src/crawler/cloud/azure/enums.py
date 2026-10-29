from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class AzureHtmlTag(StrEnum):
    """Enums representing the HTML elements compared by the Azure catalogue crawler.

    Attributes:
        H2 (str): A category heading of the products page.
        DIV (str): A section of the Microsoft Learn directory.
    """

    H2 = "h2"
    DIV = "div"


@unique
class AzureCssClass(StrEnum):
    """Enums representing the CSS classes compared by the Azure catalogue crawler.

    Attributes:
        BOX (str): A Microsoft Learn directory section listing the products of a category.
    """

    BOX = "box"


@unique
class AzureLearnLabel(StrEnum):
    """Enums representing the Microsoft Learn directory card labels compared by the Azure catalogue crawler.

    Attributes:
        ALL_PREFIX (str): The prefix of the "All ... services" cards, which are not products (case folded).
    """

    ALL_PREFIX = "all "


@unique
class AzureTilesParameter(StrEnum):
    """Enums representing the query parameters of the Microsoft Marketplace tiles API.

    Attributes:
        REVIEWS_MY_COMMENTS_FILTER (str): Whether the reviews of the user are filtered.
        COUNTRY (str): The country of the marketplace.
        ENTITY_TYPE (str): The kind of entity listed.
        REGION (str): The region of the marketplace.
        PAGE (str): The page number, from 1.
        CATEGORY (str): The category filter, by its URL key.
        SUBCATEGORIES (str): The subcategory filter, by its URL key.
    """

    REVIEWS_MY_COMMENTS_FILTER = "ReviewsMyCommentsFilter"
    COUNTRY = "country"
    ENTITY_TYPE = "entityType"
    REGION = "region"
    PAGE = "page"
    CATEGORY = "category"
    SUBCATEGORIES = "subcategories"


@unique
class AzureTilesParameterValue(StrEnum):
    """Enums representing the values of the Microsoft Marketplace tiles API parameters.

    Attributes:
        TRUE (str): A true flag.
        UNITED_STATES (str): The United States marketplace.
        APP (str): The apps.
        ALL_REGIONS (str): Every region.
    """

    TRUE = "true"
    UNITED_STATES = "US"
    APP = "App"
    ALL_REGIONS = "ALL"


@unique
class AzureOfferType(StrEnum):
    """Enums representing the catalog offer types of the Microsoft Marketplace apps.

    Attributes:
        VIRTUAL_MACHINE (str): A virtual machine image.
        SAAS (str): A software as a service.
        OFFICE_365 (str): A Microsoft 365 app.
        POWER_BI_VISUALS (str): A Power BI visual.
        AAD_APPS (str): A Microsoft Entra ID app.
        DYNAMICS_BC (str): A Dynamics 365 Business Central app.
        DYNAMICS_CE (str): A Dynamics 365 Customer Engagement app.
        DYNAMICS_OPS (str): A Dynamics 365 Operations app.
        CONTAINERS (str): A container image.
        CONTAINER_APPS (str): A container app.
        IOT_EDGE_MODULES (str): An IoT Edge module.
        AZURE_APPLICATION (str): An Azure application.
        SOLUTION_TEMPLATE (str): A solution template.
        MANAGED_APPLICATION (str): A managed application.
        CONSULTING_SERVICES (str): A consulting service, not software.
        MANAGED_SERVICES (str): A managed service, not software.
        DYNAMICS (str): The prefix of the Dynamics 365 offer types.
    """

    VIRTUAL_MACHINE = "VirtualMachine"
    SAAS = "SaaS"
    OFFICE_365 = "Office365"
    POWER_BI_VISUALS = "PowerBIVisuals"
    AAD_APPS = "AADApps"
    DYNAMICS_BC = "DynamicsBC"
    DYNAMICS_CE = "DynamicsCE"
    DYNAMICS_OPS = "DynamicsOps"
    CONTAINERS = "Containers"
    CONTAINER_APPS = "ContainerApps"
    IOT_EDGE_MODULES = "IotEdgeModules"
    AZURE_APPLICATION = "AzureApplication"
    SOLUTION_TEMPLATE = "SolutionTemplate"
    MANAGED_APPLICATION = "ManagedApplication"
    CONSULTING_SERVICES = "ConsultingServices"
    MANAGED_SERVICES = "ManagedServices"
    DYNAMICS = "Dynamics"


@unique
class AzureMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Microsoft Marketplace crawler.

    Attributes:
        PAGE (str): The page number within a query, from 1.
        FILTERS (str): The category filters of a query.
        LABELS (str): The category labels of a query.
        OFFER_DATES (str): Marks a catalog API request.
    """

    PAGE = "page"
    FILTERS = "filters"
    LABELS = "labels"
    OFFER_DATES = "offer_dates"


@unique
class AzureCatalogParameter(StrEnum):
    """Enums representing the query parameters of the Azure catalog REST API.

    Attributes:
        API_VERSION (str): The version of the API.
        TOP (str): The most offers given in total.
        SELECT (str): The offer fields given.
    """

    API_VERSION = "api-version"
    TOP = "$top"
    SELECT = "$select"


@unique
class AzureCatalogApiVersion(StrEnum):
    """Enums representing the versions of the Azure catalog REST API.

    Attributes:
        V2018_08_01_BETA (str): The version giving the offer dates.
    """

    V2018_08_01_BETA = "2018-08-01-beta"


@unique
class AzureOfferField(StrEnum):
    """Enums representing the fields of an Azure catalog API page and of its offers.

    Attributes:
        ITEMS (str): The offers of a page.
        NEXT_PAGE_LINK (str): The URL of the next page.
        ID (str): The offer identifier.
        CREATION_DATE (str): The offer creation.
        BIG_CAT_LAST_MODIFIED_DATE (str): The last modification of the catalog entry of the offer.
    """

    ITEMS = "items"
    NEXT_PAGE_LINK = "nextPageLink"
    ID = "id"
    CREATION_DATE = "creationDate"
    BIG_CAT_LAST_MODIFIED_DATE = "bigCatLastModifiedDate"


@unique
class AzureScriptMarker(StrEnum):
    """Enums representing the script statements of the Microsoft Marketplace search page read by the crawler.

    Attributes:
        INITIAL_STATE (str): The statement assigning the initial state of the search page.
    """

    INITIAL_STATE = "window.__INITIAL_STATE__ = "


@unique
class AzureStateField(StrEnum):
    """Enums representing the fields of the initial state of the Microsoft Marketplace search page.

    Attributes:
        APPS (str): The apps state.
        DATA_MAP (str): The data of the apps state.
        CATEGORIES (str): The category taxonomy, by key.
    """

    APPS = "apps"
    DATA_MAP = "dataMap"
    CATEGORIES = "categories"


@unique
class AzureTaxonomyField(StrEnum):
    """Enums representing the fields of a category or subcategory of the Microsoft Marketplace taxonomy.

    Attributes:
        LONG_TITLE (str): The long title.
        TITLE (str): The title.
        URL_KEY (str): The URL key, the filter value.
        SUB_CATEGORY_DATA_MAPPING (str): The subcategories of a category, by key.
    """

    LONG_TITLE = "LongTitle"
    TITLE = "Title"
    URL_KEY = "UrlKey"
    SUB_CATEGORY_DATA_MAPPING = "SubCategoryDataMapping"


@unique
class AzureTilesField(StrEnum):
    """Enums representing the fields of a Microsoft Marketplace tiles API page.

    Attributes:
        APPS (str): The apps of the page.
        GALLERY_TILES (str): The app tiles, in the apps.
        COUNT (str): The app count of the query, in the apps.
    """

    APPS = "apps"
    GALLERY_TILES = "galleryTiles"
    COUNT = "count"


@unique
class AzureTileField(StrEnum):
    """Enums representing the fields of a Microsoft Marketplace app tile.

    Attributes:
        ENTITY_ID_LOWERED_CASED (str): The lower case app identifier.
        ENTITY_ID (str): The app identifier.
        CATEGORIES_DETAILS (str): The categories of the app.
        TITLE (str): The app name.
        CATALOG_OFFER_TYPE (str): The catalog offer type of the app.
        SHORT_DESCRIPTION (str): The app description.
        PUBLISHER (str): The app publisher.
    """

    ENTITY_ID_LOWERED_CASED = "entityIdLoweredCased"
    ENTITY_ID = "entityId"
    CATEGORIES_DETAILS = "categoriesDetails"
    TITLE = "title"
    CATALOG_OFFER_TYPE = "catalogOfferType"
    SHORT_DESCRIPTION = "shortDescription"
    PUBLISHER = "publisher"


@unique
class AzureTileCategoryField(StrEnum):
    """Enums representing the fields of a category of a Microsoft Marketplace app tile.

    Attributes:
        LONG_TITLE (str): The category label.
        URL_KEY (str): The category URL key.
    """

    LONG_TITLE = "longTitle"
    URL_KEY = "urlKey"


@unique
class AzureUpdatesParameter(StrEnum):
    """Enums representing the OData query parameters of the Azure Updates API.

    Attributes:
        FILTER (str): The filter of the updates, e.g. on the products they name.
        ORDER_BY (str): The order of the updates.
        TOP (str): How many updates are returned.
        SELECT (str): The fields returned.
    """

    FILTER = "$filter"
    ORDER_BY = "$orderby"
    TOP = "$top"
    SELECT = "$select"


@unique
class AzureUpdateField(StrEnum):
    """Enums representing the fields of the Azure Updates API responses.

    Attributes:
        VALUE (str): The list of updates of a response.
        PRODUCTS (str): The products an update names.
        GENERAL_AVAILABILITY (str): The month the update makes a feature generally available (`YYYY-MM`), if any.
        PREVIEW (str): The month the update makes a feature available in preview (`YYYY-MM`), if any.
        CREATED (str): When the update was published.
    """

    VALUE = "value"
    PRODUCTS = "products"
    GENERAL_AVAILABILITY = "generalAvailabilityDate"
    PREVIEW = "previewAvailabilityDate"
    CREATED = "created"


@unique
class AzurePriceField(StrEnum):
    """Enums representing the fields of the Azure Retail Prices API, read for the prices.

    Attributes:
        ITEMS (str): The prices of a page.
        NEXT_PAGE_LINK (str): The next page, `null` on the last one.
        CURRENCY_CODE (str): The currency of a price.
        TIER_MINIMUM_UNITS (str): The quantity from which a tier price applies.
        RETAIL_PRICE (str): The public price.
        ARM_REGION_NAME (str): The region, e.g. `westeurope` (empty for a global price).
        LOCATION (str): The region as displayed, e.g. `EU West`.
        EFFECTIVE_START_DATE (str): Since when the price applies.
        METER_ID (str): The meter (the priced dimension).
        METER_NAME (str): Its name, e.g. `D14/DS14 Spot`.
        PRODUCT_NAME (str): The product, e.g. `Virtual Machines D Series Windows`.
        SKU_ID (str): The SKU, e.g. `DZH318Z0BPVW/00QZ`.
        SKU_NAME (str): Its name, e.g. `D14 Spot`.
        SERVICE_NAME (str): The service, e.g. `Virtual Machines`.
        SERVICE_FAMILY (str): Its family, e.g. `Compute`.
        UNIT_OF_MEASURE (str): What the price is per, e.g. `1 Hour`, `10K`, `1 GB/Month`.
        TYPE (str): The kind of price (`Consumption`, `Reservation`, `DevTestConsumption`).
        RESERVATION_TERM (str): The term of a reservation, e.g. `1 Year`.
        IS_PRIMARY_METER_REGION (str): Whether the region is the primary one of the meter.
        ARM_SKU_NAME (str): The resource SKU, e.g. `Standard_D14`.
        SAVINGS_PLAN (str): The savings plan prices of the meter, by term.
        TERM (str): The term of a savings plan price.
    """

    ITEMS = "Items"
    NEXT_PAGE_LINK = "NextPageLink"
    CURRENCY_CODE = "currencyCode"
    TIER_MINIMUM_UNITS = "tierMinimumUnits"
    RETAIL_PRICE = "retailPrice"
    ARM_REGION_NAME = "armRegionName"
    LOCATION = "location"
    EFFECTIVE_START_DATE = "effectiveStartDate"
    METER_ID = "meterId"
    METER_NAME = "meterName"
    PRODUCT_NAME = "productName"
    SKU_ID = "skuId"
    SKU_NAME = "skuName"
    SERVICE_NAME = "serviceName"
    SERVICE_FAMILY = "serviceFamily"
    UNIT_OF_MEASURE = "unitOfMeasure"
    TYPE = "type"
    RESERVATION_TERM = "reservationTerm"
    IS_PRIMARY_METER_REGION = "isPrimaryMeterRegion"
    ARM_SKU_NAME = "armSkuName"
    SAVINGS_PLAN = "savingsPlan"
    TERM = "term"


@unique
class AzurePriceType(StrEnum):
    """Enums representing the kinds of price of the Azure Retail Prices API.

    Attributes:
        CONSUMPTION (str): Pay as you go.
        RESERVATION (str): A reservation, priced for its whole term.
        DEV_TEST (str): Pay as you go with a Dev/Test subscription.
    """

    CONSUMPTION = "Consumption"
    RESERVATION = "Reservation"
    DEV_TEST = "DevTestConsumption"


@unique
class AzureTerm(StrEnum):
    """Enums representing the terms of an Azure reservation or savings plan.

    Attributes:
        ONE_YEAR (str): One year.
        THREE_YEARS (str): Three years.
        FIVE_YEARS (str): Five years.
        TEN_YEARS (str): Ten years.
    """

    ONE_YEAR = "1 Year"
    THREE_YEARS = "3 Years"
    FIVE_YEARS = "5 Years"
    TEN_YEARS = "10 Years"


@unique
class AzureUnitSuffix(StrEnum):
    """Enums representing what an Azure unit of measure counts, its number aside (`10K` counts operations).

    Attributes:
        COUNT (str): A count of operations, or a unit when it is 1.
        HOUR (str): An hour.
        HOURS (str): Hours.
        PER_HOUR (str): A unit for an hour.
        PER_DAY (str): A unit for a day.
        PER_MONTH (str): A unit for a month.
        PER_YEAR (str): A unit for a year.
        PER_SECOND (str): A rate per second (a capacity).
        GB (str): A GB.
        GIB (str): A GiB.
        MB (str): A MB.
        TB (str): A TB.
        GB_MONTH (str): A GB for a month.
        GIB_MONTH (str): A GiB for a month.
        TB_MONTH (str): A TB for a month.
        GB_HOUR (str): A GB for an hour.
        GIB_HOUR (str): A GiB for an hour.
        GB_DAY (str): A GB a day (an ingestion rate).
        SECOND (str): A second.
        SECONDS (str): Seconds.
        MINUTE (str): A minute.
        MINUTES (str): Minutes.
        DAY (str): A day.
        DAYS (str): Days.
    """

    COUNT = ""
    HOUR = "Hour"
    HOURS = "Hours"
    PER_HOUR = "/Hour"
    PER_DAY = "/Day"
    PER_MONTH = "/Month"
    PER_YEAR = "/Year"
    PER_SECOND = "/Second"
    GB = "GB"
    GIB = "GiB"
    MB = "MB"
    TB = "TB"
    GB_MONTH = "GB/Month"
    GIB_MONTH = "GiB/Month"
    TB_MONTH = "TB/Month"
    GB_HOUR = "GB/Hour"
    GIB_HOUR = "GiB/Hour"
    GB_DAY = "GB/Day"
    SECOND = "Second"
    SECONDS = "Seconds"
    MINUTE = "Minute"
    MINUTES = "Minutes"
    DAY = "Day"
    DAYS = "Days"
