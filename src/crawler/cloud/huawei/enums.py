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
