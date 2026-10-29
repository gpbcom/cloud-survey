from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class KrystalSitemapSection(StrEnum):
    """Enums representing the sections of the Krystal HTML sitemap listing products.

    Attributes:
        WEBSITE_HOSTING (str): The website hosting section.
        SERVERS (str): The servers section.
        DOMAIN_NAMES (str): The domain names section.
    """

    WEBSITE_HOSTING = "Website Hosting"
    SERVERS = "Servers"
    DOMAIN_NAMES = "Domain Names"


@unique
class KrystalFooterColumn(StrEnum):
    """Enums representing the footer columns of the Krystal website listing products.

    Attributes:
        SERVICES (str): The services column.
        CLOUD (str): The cloud column.
    """

    SERVICES = "Services"
    CLOUD = "Cloud"


@unique
class KrystalRequestMeta(StrEnum):
    """Enums representing the request meta keys of the Krystal marketplace crawler.

    Attributes:
        LISTING (str): The listing of an application page request (requested URL, name and categories).
    """

    LISTING = "krystal_listing"


@unique
class KrystalListingField(StrEnum):
    """Enums representing the keys of the listing held by an application page request of the Krystal marketplace.

    Attributes:
        URL (str): The requested application page URL.
        NAME (str): The application name given by the category page.
        CATEGORIES (str): The application categories given by the category page.
    """

    URL = "url"
    NAME = "name"
    CATEGORIES = "categories"


@unique
class KrystalNextDataField(StrEnum):
    """Enums representing the keys of the `__NEXT_DATA__` objects of the Krystal hosting pages.

    Attributes:
        PROPS (str): The properties of the page.
        PAGE_PROPS (str): The page properties object.
        FRAMEWORKS (str): The applications listed by a category page.
        CATEGORIES (str): The categories of an application.
        SLUG (str): The slug of an application or a category.
        ID (str): The identifier of a category.
        NAME (str): The name of an application or a category.
        META (str): The meta data of an application page.
        DESCRIPTION (str): The meta description of an application page.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"
    FRAMEWORKS = "frameworks"
    CATEGORIES = "categories"
    SLUG = "slug"
    ID = "id"
    NAME = "name"
    META = "meta"
    DESCRIPTION = "description"


@unique
class KrystalPriceField(StrEnum):
    """Enums representing the fields of the Next.js data of the Krystal pricing pages, read for the prices.

    Attributes:
        PROPS (str): The page properties.
        PAGE_PROPS (str): The properties of the page component.
        PACKAGES (str): The virtual machine packages of the cloud pricing page, by group.
        GPUS (str): Its GPUs.
        PRICE (str): Its unit prices of the cloud resources.
        PLANS (str): The plans of the hosting page.
        NAME (str): The name of a package, a GPU or a plan.
        IDENTIFIER (str): The identifier of a plan.
        CPU_CORES (str): The cores of a package.
        MEMORY_IN_GB (str): Its memory.
        STORAGE_IN_GB (str): Its storage.
        PRICING (str): Its prices.
        PRICES (str): The prices of a package, a GPU or a plan.
        CURRENCY (str): The currency of a price.
        ISO_CODE (str): Its code.
        PERFORMANCE (str): The performance of a plan.
        CPU (str): Its cores.
        RAM (str): Its memory, e.g. `2GB`.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"
    PACKAGES = "packages"
    GPUS = "gpus"
    PRICE = "price"
    PLANS = "plans"
    NAME = "name"
    IDENTIFIER = "identifier"
    CPU_CORES = "cpu_cores"
    MEMORY_IN_GB = "memory_in_gb"
    STORAGE_IN_GB = "storage_in_gb"
    PRICING = "pricing"
    PRICES = "prices"
    CURRENCY = "currency"
    ISO_CODE = "iso_code"
    PERFORMANCE = "performance"
    CPU = "cpu"
    RAM = "ram"


@unique
class KrystalHostingPeriod(StrEnum):
    """Enums representing the billing periods of a Krystal hosting plan.

    Attributes:
        MONTHLY (str): A month.
        ANNUALLY (str): A year, paid at once.
        BIENNIALLY (str): Two years, paid at once.
    """

    MONTHLY = "monthly"
    ANNUALLY = "annually"
    BIENNIALLY = "biennially"
