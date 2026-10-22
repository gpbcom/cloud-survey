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
