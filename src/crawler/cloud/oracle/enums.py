from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class OracleDocsSection(StrEnum):
    """Enums representing the sections of the Oracle Cloud Infrastructure documentation table of contents.

    Attributes:
        INFRASTRUCTURE_SERVICES (str): The section listing the services.
    """

    INFRASTRUCTURE_SERVICES = "Infrastructure Services"


@unique
class OraclePanelClass(StrEnum):
    """Enums representing the CSS classes of the services panel blocks of the Oracle cloud home page.

    Attributes:
        DRAWER (str): A drawer, naming a category (e.g. `AI and Machine Learning`).
        GROUP (str): A group of a drawer, naming a sub-category (e.g. `Generative AI`).
    """

    DRAWER = "rc105w3"
    GROUP = "rc105w5"


@unique
class OracleHtmlTag(StrEnum):
    """Enums representing the HTML elements read by the Oracle catalogue crawler.

    Attributes:
        H3 (str): The heading of a services panel drawer.
        H4 (str): The heading of a services panel group.
    """

    H3 = "h3"
    H4 = "h4"


@unique
class OracleTocField(StrEnum):
    """Enums representing the fields of the Oracle Cloud Infrastructure documentation table of contents.

    Attributes:
        PAGES (str): The pages, by identifier.
        SOURCE_BASEPATHS (str): The base paths of the pages, by identifier.
        TREE (str): The tree of the entries.
        PAGE_ID (str): The page identifier of an entry.
        CHILDREN (str): The children of an entry.
        TITLE (str): The title of a page.
        PATH (str): The path of a page, relative to its base path.
        SOURCE (str): The base path identifier of a page.
    """

    PAGES = "pages"
    SOURCE_BASEPATHS = "sourceBasepaths"
    TREE = "tree"
    PAGE_ID = "i"
    CHILDREN = "c"
    TITLE = "t"
    PATH = "p"
    SOURCE = "s"


@unique
class OracleMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Oracle Cloud Marketplace crawler.

    Attributes:
        PAGE (str): The number of a listings page.
        DETAIL (str): Marks a listing detail, holding the listing identifier.
    """

    PAGE = "page"
    DETAIL = "detail"


@unique
class OracleHeader(StrEnum):
    """Enums representing the request headers of the Oracle Cloud Marketplace API.

    Attributes:
        REFERER (str): The page sending the request.
    """

    REFERER = "Referer"


@unique
class OracleListingType(StrEnum):
    """Enums representing the listing types of the Oracle Cloud Marketplace.

    Attributes:
        SERVICE (str): A service, not software.
        OCI_APPLICATION (str): An OCI application (image or stack).
        LEAD_GENERATION (str): A lead generation listing, a SaaS application.
        AI_AGENT (str): An AI agent.
    """

    SERVICE = "SERVICE"
    OCI_APPLICATION = "OCI_APPLICATION"
    LEAD_GENERATION = "LEAD_GENERATION"
    AI_AGENT = "AI_AGENT"


@unique
class OracleProductGroup(StrEnum):
    """Enums representing the product groups of the Oracle Cloud Marketplace listings.

    Attributes:
        SERVICES (str): The services.
    """

    SERVICES = "SERVICES"


@unique
class OraclePartnerProduct(StrEnum):
    """Enums representing the products of the Oracle partners which are not software publishers.

    Attributes:
        SYSTEM_INTEGRATORS (str): The system integrators.
        RESELLERS (str): The resellers.
        INFLUENCERS_AND_ADVISORS (str): The influencers and advisors.
    """

    SYSTEM_INTEGRATORS = "System Integrators"
    RESELLERS = "Resellers"
    INFLUENCERS_AND_ADVISORS = "Influencers and Advisors"


@unique
class OracleListingsPageField(StrEnum):
    """Enums representing the fields of an Oracle Cloud Marketplace listings page.

    Attributes:
        ITEMS (str): The listings of the page.
        PAGINATION (str): The pagination of the listings.
        TOTAL_PAGES (str): The number of pages, in the pagination.
        TOTAL_ITEMS (str): The number of listings, in the pagination.
    """

    ITEMS = "items"
    PAGINATION = "pagination"
    TOTAL_PAGES = "totalPages"
    TOTAL_ITEMS = "totalItems"


@unique
class OracleListingField(StrEnum):
    """Enums representing the fields of an Oracle Cloud Marketplace listing and of its partner.

    Attributes:
        ID (str): The listing identifier.
        NAME (str): The name of the listing, or of its partner.
        LISTING_TYPE (str): The listing type.
        PRODUCTS (str): The products of the listing.
        SHORT_DESCRIPTION (str): The short description.
        TAGLINE (str): The tagline, the fallback description.
        PARTNER (str): The publisher of the listing.
        TIME_CREATED (str): The listing creation.
        TIME_UPDATED (str): The last update of the listing.
    """

    ID = "id"
    NAME = "name"
    LISTING_TYPE = "listingType"
    PRODUCTS = "products"
    SHORT_DESCRIPTION = "shortDescription"
    TAGLINE = "tagline"
    PARTNER = "partner"
    TIME_CREATED = "timeCreated"
    TIME_UPDATED = "timeUpdated"


@unique
class OracleProductField(StrEnum):
    """Enums representing the fields of a product of an Oracle Cloud Marketplace listing.

    Attributes:
        PRODUCT_GROUP (str): The product group.
        PRODUCT_NAME (str): The product name.
        CATEGORIES (str): The categories of the product.
    """

    PRODUCT_GROUP = "productGroup"
    PRODUCT_NAME = "productName"
    CATEGORIES = "categories"


@unique
class OracleCategoryField(StrEnum):
    """Enums representing the fields of a category of an Oracle Cloud Marketplace product.

    Attributes:
        NAME (str): The category name.
        CODE (str): The category code.
    """

    NAME = "name"
    CODE = "code"


@unique
class OracleReleaseNotesField(StrEnum):
    """Enums representing the fields of a service of the Oracle Cloud Infrastructure release notes services list.

    Attributes:
        SLUG (str): The service slug, naming its release notes page (e.g. `audit`).
        TITLE (str): The service title (e.g. `Audit`).
    """

    SLUG = "s"
    TITLE = "t"


@unique
class OracleProductsField(StrEnum):
    """Enums representing the fields of the Oracle Cloud price list API (cetools products), read for the prices.

    Attributes:
        ITEMS (str): The parts of the price list.
        LAST_UPDATED (str): When the price list last changed (its version).
        PART_NUMBER (str): The part number, e.g. `B88327`.
        DISPLAY_NAME (str): The name of the part.
        METRIC_NAME (str): What its price is per, e.g. `OCPU Per Hour`.
        SERVICE_CATEGORY (str): Its service, e.g. `Compute - Virtual Machine`.
        DESCRIPTION (str): Its description, if any.
        CURRENCY_LOCALIZATIONS (str): Its prices, by currency.
        CURRENCY_CODE (str): The currency of a price list.
        PRICES (str): The prices in a currency (one per volume tier).
        MODEL (str): How a price is charged (`PAY_AS_YOU_GO`).
        VALUE (str): The price.
        RANGE_MIN (str): The quantity from which a tier price applies.
        RANGE_MAX (str): The quantity up to which it applies.
    """

    ITEMS = "items"
    LAST_UPDATED = "lastUpdated"
    PART_NUMBER = "partNumber"
    DISPLAY_NAME = "displayName"
    METRIC_NAME = "metricName"
    SERVICE_CATEGORY = "serviceCategory"
    DESCRIPTION = "description"
    CURRENCY_LOCALIZATIONS = "currencyCodeLocalizations"
    CURRENCY_CODE = "currencyCode"
    PRICES = "prices"
    MODEL = "model"
    VALUE = "value"
    RANGE_MIN = "rangeMin"
    RANGE_MAX = "rangeMax"
