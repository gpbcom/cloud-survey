from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class OvhNextDataField(StrEnum):
    """Enums representing the fields of the Next.js data of the OVHcloud website pages, down to the products menu.

    Attributes:
        PROPS (str): The page properties.
        PAGE_PROPS (str): The properties of the page component.
        ITEMS_DESKTOP (str): The products menu, by universe.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"
    ITEMS_DESKTOP = "itemsDesktop"


@unique
class OvhMenuKey(StrEnum):
    """Enums representing the fields of an entry of the OVHcloud products menu.

    Attributes:
        LEVEL (str): The depth of the entry, 1 for a top level entry.
        CHILDREN (str): The entries under the entry.
        LABEL (str): The entry label.
        LINK (str): The entry link.
        DESCRIPTION (str): The entry description.
        COMING_SOON (str): Whether the entry is not available yet.
    """

    LEVEL = "level"
    CHILDREN = "children"
    LABEL = "label"
    LINK = "link"
    DESCRIPTION = "description"
    COMING_SOON = "comingSoon"


@unique
class OvhMenuUniverse(StrEnum):
    """Enums representing the universes of the OVHcloud products menu compared by the crawler.

    Attributes:
        HOME (str): The home universe, whose top level entries are categories.
    """

    HOME = "home"


@unique
class OvhHostPrefix(StrEnum):
    """Enums representing the host prefixes ignored when comparing the OVHcloud links.

    Attributes:
        WWW (str): The `www` sub-domain.
    """

    WWW = "www."


@unique
class OvhScriptId(StrEnum):
    """Enums representing the identifiers of the scripts of the OVHcloud marketplace products page.

    Attributes:
        PRODUCTS (str): The script holding the marketplace products.
        ASSET_TYPES (str): The script holding the top categories (asset types).
    """

    PRODUCTS = "preloadedProductsData"
    ASSET_TYPES = "preloadedAssetTypesData"


@unique
class OvhPreloadedField(StrEnum):
    """Enums representing the fields of the preloaded data of the OVHcloud marketplace scripts.

    Attributes:
        RESPONSE (str): The data of a script.
        ASSETS (str): The products, in the data of the products script.
    """

    RESPONSE = "response"
    ASSETS = "assets"


@unique
class OvhAssetTypeField(StrEnum):
    """Enums representing the fields of an asset type (top category) of the OVHcloud marketplace.

    Attributes:
        LOCALIZED_NAME (str): The English name.
        NAME (str): The name, the fallback.
        FIELD_SET_ID (str): The field set identifier, the asset type of its products.
    """

    LOCALIZED_NAME = "localizedName"
    NAME = "name"
    FIELD_SET_ID = "fieldSetID"


@unique
class OvhProductField(StrEnum):
    """Enums representing the fields of an OVHcloud marketplace product.

    Attributes:
        NAME (str): The product name.
        DESCRIPTION (str): The HTML description.
        SEO_ELEMENTS (str): The search engine elements, holding a description.
        CATEGORIES (str): The filter groups.
        CUSTOM_FIELDS (str): The custom fields.
        SLUG_NAME (str): The slug of the product page.
        ASSET_ENCRYPT_KEY (str): The key of the product page.
        ASSET_TYPE_ID (str): The asset type (field set of the top category).
        ORGANIZATION_NAME (str): The publisher.
        CREATED_ON (str): The listing date.
        UPDATED_ON (str): The last update.
    """

    NAME = "name"
    DESCRIPTION = "description"
    SEO_ELEMENTS = "seoElements"
    CATEGORIES = "categories"
    CUSTOM_FIELDS = "customFields"
    SLUG_NAME = "slugName"
    ASSET_ENCRYPT_KEY = "assetEncryptKey"
    ASSET_TYPE_ID = "assetTypeID"
    ORGANIZATION_NAME = "organizationName"
    CREATED_ON = "createdOn"
    UPDATED_ON = "updatedOn"


@unique
class OvhFilterGroupField(StrEnum):
    """Enums representing the fields of a filter group of an OVHcloud marketplace product.

    Attributes:
        CATEGORY_NAME (str): The filter group name.
        FILTERS (str): The filter values.
    """

    CATEGORY_NAME = "categoryName"
    FILTERS = "filters"


@unique
class OvhCustomField(StrEnum):
    """Enums representing the custom fields of an OVHcloud marketplace product.

    Attributes:
        SUBCATEGORY (str): The free text sub-category.
    """

    SUBCATEGORY = "Subcategory"


@unique
class OvhSeoField(StrEnum):
    """Enums representing the search engine elements of an OVHcloud marketplace product.

    Attributes:
        DESCRIPTION (str): The search engine description.
    """

    DESCRIPTION = "description"


@unique
class OvhFilterGroup(StrEnum):
    """Enums representing the filter groups of the OVHcloud marketplace products.

    Attributes:
        SUBCATEGORIES (str): The sub-categories.
        SERVICE_TYPE (str): The service types.
    """

    SUBCATEGORIES = "Subcategories"
    SERVICE_TYPE = "Service type"


@unique
class OvhServiceType(StrEnum):
    """Enums representing the service types of the OVHcloud marketplace products (case folded).

    Attributes:
        SUPPORT (str): A support offer, not software.
        MANAGED_SERVICES (str): A managed service, not software.
        SAAS (str): A software as a service.
        PAAS (str): A platform as a service.
        SOFTWARE_ON_PREM (str): A software installed on premises.
    """

    SUPPORT = "support"
    MANAGED_SERVICES = "managed services"
    SAAS = "saas"
    PAAS = "paas"
    SOFTWARE_ON_PREM = "software on-prem"


@unique
class OvhSubcategory(StrEnum):
    """Enums representing the sub-categories of the OVHcloud marketplace technical support offers (case folded).

    Attributes:
        TECHNICAL_SUPPORT (str): The technical support.
        ONE_OFF_TECHNICAL_ASSISTANCE (str): The one-off technical assistance (French label).
    """

    TECHNICAL_SUPPORT = "technical support"
    ONE_OFF_TECHNICAL_ASSISTANCE = "assistance technique ponctuelle"


@unique
class OvhPriceCatalog(StrEnum):
    """Enums representing the public order catalogs of OVHcloud read for the prices.

    Attributes:
        CLOUD (str): The Public Cloud.
        VPS (str): The virtual private servers.
        BAREMETAL (str): The dedicated servers.
        ECO (str): The Eco dedicated servers (Kimsufi, So you Start, Rise).
        WEB_HOSTING (str): The web hosting plans.
        PRIVATE_CLOUD (str): The Hosted Private Cloud.
        EMAIL_DOMAIN (str): The email plans of a domain.
        DOMAIN (str): The domain names.
        OKMS (str): The key management service.
        LOGS (str): The Logs Data Platform.
    """

    CLOUD = "cloud"
    VPS = "vps"
    BAREMETAL = "baremetalServers"
    ECO = "eco"
    WEB_HOSTING = "webHosting"
    PRIVATE_CLOUD = "privateCloud"
    EMAIL_DOMAIN = "emailDomain"
    DOMAIN = "domain"
    OKMS = "okms"
    LOGS = "logs"


@unique
class OvhCatalogField(StrEnum):
    """Enums representing the fields of an OVHcloud public order catalog.

    Attributes:
        CATALOG_ID (str): The catalog version.
        LOCALE (str): The locale of the catalog.
        CURRENCY_CODE (str): Its currency.
        PLANS (str): The plans (what is ordered).
        ADDONS (str): The addons (what is added to a plan, or consumed).
        PRODUCTS (str): The products the plans and addons belong to.
        PLAN_CODE (str): The code of a plan or an addon.
        INVOICE_NAME (str): Its name on the invoice.
        PRODUCT (str): Its product.
        PRICINGS (str): Its prices.
        BLOBS (str): Its commercial and technical descriptions.
        NAME (str): The name of a product.
        DESCRIPTION (str): The description of a product.
    """

    CATALOG_ID = "catalogId"
    LOCALE = "locale"
    CURRENCY_CODE = "currencyCode"
    PLANS = "plans"
    ADDONS = "addons"
    PRODUCTS = "products"
    PLAN_CODE = "planCode"
    INVOICE_NAME = "invoiceName"
    PRODUCT = "product"
    PRICINGS = "pricings"
    BLOBS = "blobs"
    NAME = "name"
    DESCRIPTION = "description"


@unique
class OvhPricingField(StrEnum):
    """Enums representing the fields of a price of an OVHcloud order catalog.

    Attributes:
        CAPACITIES (str): What it is charged for (installation, renewal, consumption...).
        COMMITMENT (str): The commitment, in months.
        DESCRIPTION (str): Its description, e.g. `hourly prices`.
        INTERVAL (str): The intervals it is charged per.
        INTERVAL_UNIT (str): Their unit (`none`, `hour`, `month`).
        PRICE (str): The price, in hundred millionths of the currency.
        MODE (str): The payment mode, e.g. `upfront12`.
        TYPE (str): The kind of price (`rental`, `consumption`, `purchase`).
        PHASE (str): The phase of the price (0 at order, 1 at renewal).
        QUANTITY (str): The quantities it applies to (a consumption tier).
        MIN (str): The least quantity.
        MAX (str): The most quantity, `null` without bound.
    """

    CAPACITIES = "capacities"
    COMMITMENT = "commitment"
    DESCRIPTION = "description"
    INTERVAL = "interval"
    INTERVAL_UNIT = "intervalUnit"
    PRICE = "price"
    MODE = "mode"
    TYPE = "type"
    PHASE = "phase"
    QUANTITY = "quantity"
    MIN = "min"
    MAX = "max"


@unique
class OvhBlobField(StrEnum):
    """Enums representing the fields of the descriptions (blobs) of an OVHcloud plan or addon.

    Attributes:
        COMMERCIAL (str): The commercial description.
        TECHNICAL (str): The technical description.
        PRICE (str): How the commercial description writes the price.
        UNIT (str): The unit of the price, e.g. `GiB*h`.
        BRICK (str): The commercial family, e.g. `storage`.
        BRICK_SUBTYPE (str): The commercial sub-family, e.g. `Standard object storage - S3 API`.
        SERVER (str): The server of a dedicated server.
        CPU (str): The processor.
        CORES (str): Its cores.
        THREADS (str): Its threads.
        NUMBER (str): The number of processors, disks or GPUs.
        MEMORY (str): The memory.
        SIZE (str): Its size, in GiB.
        STORAGE (str): The storage.
        DISKS (str): Its disks.
        CAPACITY (str): The capacity of a disk, in GB.
        OS (str): The operating system.
        FAMILY (str): Its family, e.g. `linux`.
        GPU (str): The GPUs.
        MODEL (str): The GPU model.
    """

    COMMERCIAL = "commercial"
    TECHNICAL = "technical"
    PRICE = "price"
    UNIT = "unit"
    BRICK = "brick"
    BRICK_SUBTYPE = "brickSubtype"
    SERVER = "server"
    CPU = "cpu"
    CORES = "cores"
    THREADS = "threads"
    NUMBER = "number"
    MEMORY = "memory"
    SIZE = "size"
    STORAGE = "storage"
    DISKS = "disks"
    CAPACITY = "capacity"
    OS = "os"
    FAMILY = "family"
    GPU = "gpu"
    MODEL = "model"


@unique
class OvhCapacity(StrEnum):
    """Enums representing what a price of an OVHcloud order catalog is charged for.

    Attributes:
        INSTALLATION (str): The installation (once).
        RENEW (str): The renewal (every interval).
        UPGRADE (str): An upgrade (once).
        CONSUMPTION (str): The consumption.
        DYNAMIC (str): A price set at order (a premium domain).
        DETACH (str): A detachment (once).
    """

    INSTALLATION = "installation"
    RENEW = "renew"
    UPGRADE = "upgrade"
    CONSUMPTION = "consumption"
    DYNAMIC = "dynamic"
    DETACH = "detach"


@unique
class OvhIntervalUnit(StrEnum):
    """Enums representing the interval units of an OVHcloud price.

    Attributes:
        NONE (str): No interval (once, or per consumed unit).
        HOUR (str): An hour.
        MONTH (str): A month.
    """

    NONE = "none"
    HOUR = "hour"
    MONTH = "month"


@unique
class OvhCommercialUnit(StrEnum):
    """Enums representing the units the commercial description of an OVHcloud price writes.

    Attributes:
        HOUR (str): An hour.
        NODE_HOUR (str): A node for an hour.
        GIB_HOUR (str): A GiB for an hour.
        GIB (str): A GiB transferred.
        TOKENS_INPUT (str): A million input tokens.
        TOKENS_OUTPUT (str): A million output tokens.
        VM_MONTH (str): A virtual machine for a month.
        MONTH_PER_GIB (str): A GiB for a month.
        GIB_MONTH (str): A GiB for a month.
        KEY_MONTH (str): A key for a month.
        HOUR_PER_VCORE (str): A vCore for an hour.
        DPU_HOUR (str): A data processing unit for an hour.
        CLUSTER_HOUR (str): A cluster for an hour.
        VCPU_HOUR (str): A vCPU for an hour.
        VCPU_MONTH (str): A vCPU for a month.
        INSTANCE_MONTH (str): An instance for a month.
        MONTH_PER_VCORE (str): A vCore for a month.
        TIB (str): A TiB.
        VCORE_HOUR (str): A vCore for an hour.
        HOUR_PER_GIB (str): A GiB for an hour.
        HOST_MONTH (str): A host for a month.
        SECRET_VERSION_MONTH (str): A secret version for a month.
        UNIT_MONTH (str): A unit for a month.
    """

    HOUR = "h"
    NODE_HOUR = "h/node"
    GIB_HOUR = "GiB*h"
    GIB = "GiB"
    TOKENS_INPUT = "million_token_input"
    TOKENS_OUTPUT = "million_token_output"
    VM_MONTH = "vm*M"
    MONTH_PER_GIB = "M/GiB"
    GIB_MONTH = "GiB*M"
    KEY_MONTH = "key*M"
    HOUR_PER_VCORE = "h/vCore"
    DPU_HOUR = "dpu*h"
    CLUSTER_HOUR = "cluster*h"
    VCPU_HOUR = "vCPU*h"
    VCPU_MONTH = "vCPU*M"
    INSTANCE_MONTH = "instance*M"
    MONTH_PER_VCORE = "M/vCore"
    TIB = "TiB"
    VCORE_HOUR = "vCore*h"
    HOUR_PER_GIB = "h/GiB"
    HOST_MONTH = "host*M"
    SECRET_VERSION_MONTH = "secret*version*M"
    UNIT_MONTH = "unit*M"
