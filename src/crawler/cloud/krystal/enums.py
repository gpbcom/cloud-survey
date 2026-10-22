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
