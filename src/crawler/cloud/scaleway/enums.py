from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ScalewayNextDataField(StrEnum):
    """Enums representing the fields of the Next.js data of the Scaleway website pages.

    Attributes:
        PROPS (str): The page properties.
        PAGE_PROPS (str): The properties of the page component.
        HEADER (str): The header of the page.
        MAIN_NAVIGATION_ITEMS (str): The groups of the header menu.
        ALL_APPS (str): The applications of the marketplace catalog.
        ALL_FILTERS (str): The filters of the marketplace catalog.
        NAVIGATION (str): The navigation of the marketplace catalog.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"
    HEADER = "header"
    MAIN_NAVIGATION_ITEMS = "mainNavigationItems"
    ALL_APPS = "allApps"
    ALL_FILTERS = "allFilters"
    NAVIGATION = "navigation"


@unique
class ScalewayCmsComponent(StrEnum):
    """Enums representing the CMS components of the Scaleway website pages read by the crawler.

    Attributes:
        GENERIC_COLUMNS (str): The block listing the products of a category.
    """

    GENERIC_COLUMNS = "blocks.generic-columns"


@unique
class ScalewayBlockField(StrEnum):
    """Enums representing the fields of a CMS block of the Scaleway website pages.

    Attributes:
        COMPONENT (str): The CMS component of the block.
        ITEMS (str): The entries of the block.
        TITLE (str): The block title.
    """

    COMPONENT = "__component"
    ITEMS = "items"
    TITLE = "title"


@unique
class ScalewayEntryField(StrEnum):
    """Enums representing the fields of a product entry of the Scaleway page columns and header menu.

    Attributes:
        TITLE (str): The name of a column entry.
        GROUP_NAME (str): The name of a menu entry or group.
        DESCRIPTION (str): The entry description.
        LINK (str): The entry link.
        CHILDREN (str): The entries of a menu group.
    """

    TITLE = "title"
    GROUP_NAME = "groupName"
    DESCRIPTION = "description"
    LINK = "link"
    CHILDREN = "children"


@unique
class ScalewayLinkField(StrEnum):
    """Enums representing the fields of a link of the Scaleway website pages.

    Attributes:
        URL (str): The URL of a link to a URL.
        PAGE (str): The website page of a link to a page.
    """

    URL = "url"
    PAGE = "page"


@unique
class ScalewayPageField(StrEnum):
    """Enums representing the fields of a website page record of a Scaleway link.

    Attributes:
        PATH (str): The page path.
        CREATED_AT (str): The creation of the page record.
        UPDATED_AT (str): The last update of the page record.
    """

    PATH = "path"
    CREATED_AT = "createdAt"
    UPDATED_AT = "updatedAt"


@unique
class ScalewayMenuGroup(StrEnum):
    """Enums representing the groups of the Scaleway header menu listing products.

    Attributes:
        AI (str): The AI products.
        CLOUD (str): The cloud products.
        BARE_METAL (str): The bare metal products.
    """

    AI = "AI"
    CLOUD = "Cloud"
    BARE_METAL = "Bare Metal"


@unique
class ScalewayCatalogFiltersField(StrEnum):
    """Enums representing the fields of the filters of the Scaleway marketplace catalog.

    Attributes:
        VENDORS (str): The vendors.
    """

    VENDORS = "vendors"


@unique
class ScalewayNavigationField(StrEnum):
    """Enums representing the fields of the navigation of the Scaleway marketplace catalog.

    Attributes:
        SIDE_NAV (str): The side navigation.
        CATEGORY_PAGES (str): The category pages, in the side navigation.
    """

    SIDE_NAV = "sideNav"
    CATEGORY_PAGES = "category_pages"


@unique
class ScalewayLabelField(StrEnum):
    """Enums representing the fields of the labelled slugs (vendors, category pages) of the Scaleway marketplace.

    Attributes:
        SLUG (str): The slug.
        NAME (str): The name of a vendor.
        TITLE (str): The title of a category page.
    """

    SLUG = "slug"
    NAME = "name"
    TITLE = "title"


@unique
class ScalewayAppField(StrEnum):
    """Enums representing the fields of a Scaleway marketplace application.

    Attributes:
        TITLE (str): The application name.
        SLUG (str): The slug of the application page.
        DESCRIPTION (str): The description.
        DELIVERY_METHOD (str): The delivery label.
        FILTERS (str): The filters of the application.
    """

    TITLE = "title"
    SLUG = "slug"
    DESCRIPTION = "description"
    DELIVERY_METHOD = "deliveryMethod"
    FILTERS = "filters"


@unique
class ScalewayAppFilterField(StrEnum):
    """Enums representing the filters of a Scaleway marketplace application.

    Attributes:
        CATEGORIES (str): The category slugs.
        VENDOR (str): The vendor slug.
    """

    CATEGORIES = "categories"
    VENDOR = "vendor"


@unique
class ScalewayAppCategory(StrEnum):
    """Enums representing the category slugs of the Scaleway marketplace compared by the crawler.

    Attributes:
        OS (str): The operating system images, not software.
    """

    OS = "os"


@unique
class ScalewayDeliveryLabel(StrEnum):
    """Enums representing the delivery labels of the Scaleway marketplace applications.

    Attributes:
        SAAS_AND_APIS (str): A software as a service or an API.
        VIRTUAL_MACHINES (str): A virtual machine image.
        CONTAINER_IMAGES (str): A container image.
        KUBERNETES_APPS (str): A Kubernetes app.
        OTHER (str): Another delivery.
    """

    SAAS_AND_APIS = "SaaS & APIs"
    VIRTUAL_MACHINES = "Virtual machines"
    CONTAINER_IMAGES = "Container images"
    KUBERNETES_APPS = "Kubernetes apps"
    OTHER = "Other"


@unique
class ScalewayChangelogTag(StrEnum):
    """Enums representing the tags of the Scaleway changelog RSS feed read to date the products.

    Attributes:
        ITEM (str): A changelog entry.
        TITLE (str): The entry title, `<product label> | <change>`.
        PUB_DATE (str): The entry publication date (RFC 822).
    """

    ITEM = "item"
    TITLE = "title"
    PUB_DATE = "pubDate"


@unique
class ScalewayCatalogField(StrEnum):
    """Enums representing the fields of the Scaleway public product catalog API, read for the prices.

    Attributes:
        PRODUCTS (str): The products of a page.
        TOTAL_COUNT (str): The products of the whole catalog.
        SKU (str): The SKU of a product, e.g. `/instance/server/basic3_x2c_4g/fr-par-1`.
        SERVICE_CATEGORY (str): The category of its service, e.g. `Compute`.
        PRODUCT_CATEGORY (str): Its service, e.g. `Instance`.
        PRODUCT (str): Its name, e.g. `BASIC3-X2C-4G`.
        VARIANT (str): Its variant, e.g. `BASIC3-X2C-4G - fr-par-1`.
        DESCRIPTION (str): Its description, the price written out.
        LOCALITY (str): Where it is sold (one zone, region or datacenter, or everywhere).
        PRICE (str): Its price.
        RETAIL_PRICE (str): Its public price.
        CURRENCY_CODE (str): The currency of the price.
        UNITS (str): The whole part of the price.
        NANOS (str): The billionths of the price.
        PROPERTIES (str): Its technical properties, by service.
        UNIT_OF_MEASURE (str): What the price is per.
        UNIT (str): The unit of the price.
        SIZE (str): The units the price is per (1,000 tokens, 100 requests).
        STATUS (str): Its sale status.
    """

    PRODUCTS = "products"
    TOTAL_COUNT = "total_count"
    SKU = "sku"
    SERVICE_CATEGORY = "service_category"
    PRODUCT_CATEGORY = "product_category"
    PRODUCT = "product"
    VARIANT = "variant"
    DESCRIPTION = "description"
    LOCALITY = "locality"
    PRICE = "price"
    RETAIL_PRICE = "retail_price"
    CURRENCY_CODE = "currency_code"
    UNITS = "units"
    NANOS = "nanos"
    PROPERTIES = "properties"
    UNIT_OF_MEASURE = "unit_of_measure"
    UNIT = "unit"
    SIZE = "size"
    STATUS = "status"


@unique
class ScalewayLocality(StrEnum):
    """Enums representing where a product of the Scaleway catalog is sold.

    Attributes:
        ZONE (str): An availability zone, e.g. `fr-par-1`.
        REGION (str): A region, e.g. `fr-par`.
        DATACENTER (str): A Dedibox datacenter, e.g. `DC5`.
        GLOBAL (str): Every region (`true`).
    """

    ZONE = "zone"
    REGION = "region"
    DATACENTER = "datacenter"
    GLOBAL = "global"


@unique
class ScalewayHardwareField(StrEnum):
    """Enums representing the hardware properties of a server of the Scaleway catalog.

    Attributes:
        HARDWARE (str): The hardware of the server.
        CPU (str): Its processor.
        VIRTUAL (str): Its virtual CPUs (an instance).
        COUNT (str): Their number.
        THREADS (str): The threads of a dedicated processor.
        RAM (str): Its memory.
        SIZE (str): The memory, in bytes.
        STORAGE (str): Its storage.
        TOTAL (str): The storage, in bytes.
    """

    HARDWARE = "hardware"
    CPU = "cpu"
    VIRTUAL = "virtual"
    COUNT = "count"
    THREADS = "threads"
    RAM = "ram"
    SIZE = "size"
    STORAGE = "storage"
    TOTAL = "total"


@unique
class ScalewayPriceUnit(StrEnum):
    """Enums representing the units the Scaleway catalog prices are per.

    Attributes:
        HOUR (str): An hour.
        MINUTE (str): A minute.
        SECOND (str): A second (of audio).
        MONTH (str): A month.
        YEAR (str): A year (a domain).
        SETUP (str): A setup fee.
        PLAN (str): A plan (a subscription, or the fee of a server).
        GIGABYTE (str): A gigabyte, stored for an hour or transferred.
        GIGABYTE_DAY (str): A gigabyte kept for a day.
        IOPS_GIGABYTE (str): An IO/s per gigabyte.
        GB_S (str): A gigabyte of memory for a second.
        VCPU_S (str): A virtual CPU for a second.
        MVCPU (str): A thousandth of a virtual CPU.
        TOKEN (str): A token of a language model.
        REQUEST (str): A request.
        CHUNK (str): A message chunk.
        EMAIL (str): An email sent.
        DOMAIN (str): A domain operation.
        IP (str): An IP address, for an hour.
        NODE (str): A node, for an hour.
        CORE (str): A licensed processor core.
        DEVICE (str): A device, for an hour.
        VERSION (str): A secret or key version, for an hour.
        KEY (str): A name key, for an hour.
        SAMPLE_DAY (str): A metric sample kept for a day.
    """

    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    MONTH = "month"
    YEAR = "year"
    SETUP = "setup"
    PLAN = "plan"
    GIGABYTE = "gigabyte"
    GIGABYTE_DAY = "gigabyte_day"
    IOPS_GIGABYTE = "iops_gigabyte"
    GB_S = "gb_s"
    VCPU_S = "vcpu_s"
    MVCPU = "mvcpu"
    TOKEN = "token"
    REQUEST = "request"
    CHUNK = "chunk"
    EMAIL = "email"
    DOMAIN = "domain"
    IP = "ip"
    NODE = "node"
    CORE = "core"
    DEVICE = "device"
    VERSION = "version"
    KEY = "key"
    SAMPLE_DAY = "sample_day"


@unique
class ScalewayStatus(StrEnum):
    """Enums representing the sale status of a product of the Scaleway catalog.

    Attributes:
        GENERAL_AVAILABILITY (str): Sold.
        PUBLIC_BETA (str): In public beta.
        PREVIEW (str): In preview.
        END_OF_GROWTH (str): Sold, no longer developed.
        END_OF_SALE (str): No longer sold to new customers.
        END_OF_LIFE (str): No longer sold.
        RETIRED (str): Withdrawn.
    """

    GENERAL_AVAILABILITY = "general_availability"
    PUBLIC_BETA = "public_beta"
    PREVIEW = "preview"
    END_OF_GROWTH = "end_of_growth"
    END_OF_SALE = "end_of_sale"
    END_OF_LIFE = "end_of_life"
    RETIRED = "retired"
