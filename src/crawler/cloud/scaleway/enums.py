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
