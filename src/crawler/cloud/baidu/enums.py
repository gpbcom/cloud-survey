from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class BaiduPageTitle(StrEnum):
    """Enums representing the texts of the Baidu AI Cloud product page titles removed from the product names.

    Attributes:
        BRAND_SUFFIX (str): The brand suffix of the page titles.
    """

    BRAND_SUFFIX = "-百度智能云"


@unique
class BaiduNextDataField(StrEnum):
    """Enums representing the fields of the Next.js data of the Baidu AI Cloud products page, on the catalogue path.

    Attributes:
        PROPS (str): The page properties.
        PAGE_PROPS (str): The properties of the page component, within the page properties.
        NEW_PRODUCTS_LIST (str): The catalogue, a list of top groups, within the page component properties.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"
    NEW_PRODUCTS_LIST = "newProductsList"


@unique
class BaiduCatalogueGroupField(StrEnum):
    """Enums representing the fields of a top group of the Baidu AI Cloud catalogue.

    Attributes:
        NAME (str): The name of the group.
        CATEGORIES (str): The categories of the group.
    """

    NAME = "name"
    CATEGORIES = "categories"


@unique
class BaiduCatalogueCategoryField(StrEnum):
    """Enums representing the fields of a category of the Baidu AI Cloud catalogue.

    Attributes:
        CATEGORY (str): The name of the category.
        LIST (str): The sub-categories of the category.
    """

    CATEGORY = "category"
    LIST = "list"


@unique
class BaiduCatalogueSubCategoryField(StrEnum):
    """Enums representing the fields of a sub-category of the Baidu AI Cloud catalogue.

    Attributes:
        TYPE (str): The name of the sub-category.
        PRODUCTS (str): The products of the sub-category.
        LINK (str): The page of the sub-category, a product when it holds no products.
    """

    TYPE = "type"
    PRODUCTS = "products"
    LINK = "link"


@unique
class BaiduCatalogueProductField(StrEnum):
    """Enums representing the fields of a product of the Baidu AI Cloud catalogue.

    Attributes:
        NAME (str): The name of the product.
        DESC (str): The description of the product.
        LINK (str): The product page link.
    """

    NAME = "name"
    DESC = "desc"
    LINK = "link"


@unique
class BaiduMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Baidu AI Cloud marketplace crawler.

    Attributes:
        KIND (str): The kind of the response (`BaiduMarketplaceKind`).
        PRODUCT (str): The product identifier of a detail or related products response.
        SHARE (str): How many products of a category page are requested, under a page limit.
    """

    KIND = "kind"
    PRODUCT = "product"
    SHARE = "share"


@unique
class BaiduMarketplaceKind(StrEnum):
    """Enums representing the kinds of the responses read by the Baidu AI Cloud marketplace crawler.

    Attributes:
        CATEGORIES (str): The category tree.
        LIST (str): A category products page.
        SITEMAP (str): The sitemap.
        DETAIL (str): A product detail.
        RELATED (str): The related products of a product.
    """

    CATEGORIES = "categories"
    LIST = "list"
    SITEMAP = "sitemap"
    DETAIL = "detail"
    RELATED = "related"


@unique
class BaiduMarketplaceErrorCode(StrEnum):
    """Enums representing the error codes of the Baidu AI Cloud marketplace product detail API.

    Attributes:
        OFFLINE (str): The product is delisted.
    """

    OFFLINE = "OFFLINE"


@unique
class BaiduMarketplaceDelivery(StrEnum):
    """Enums representing the delivery methods of the Baidu AI Cloud marketplace products.

    Attributes:
        SAAS_AUTO (str): A software as a service, provisioned automatically.
        SAAS (str): A software as a service.
        API (str): An API.
        MIRROR (str): A virtual machine image.
        OFFLINE (str): An offline delivery (线下交付), installed by the vendor.
        MAN_MADE (str): A manual delivery (人工交付), set up by the vendor.
    """

    SAAS_AUTO = "SAAS_AUTO"
    SAAS = "SAAS"
    API = "API"
    MIRROR = "MIRROR"
    OFFLINE = "OFFLINE"
    MAN_MADE = "MAN_MADE"


@unique
class BaiduMarketplaceCategory(StrEnum):
    """Enums representing the top categories of the Baidu AI Cloud marketplace compared by the crawler.

    Attributes:
        CLOUD_SERVICES (str): The cloud services (上云服务), no software.
        COMPANY_SERVICES (str): The company services (公司服务), no software.
        ROBOTS (str): The robots (泛机器人), no software.
        ARTIFICIAL_INTELLIGENCE (str): The artificial intelligence offers (人工智能).
        SECURITY_SERVICES (str): The security offers (安全服务), whose manual ones are services.
        BLOCKCHAIN (str): The blockchain offers (区块链).
        WEBSITE_PROMOTION (str): The website building and promotion offers (建站推广).
        INDUSTRIAL_APPLICATIONS (str): The industrial applications (工业应用).
        API_SERVICES (str): The APIs (API服务), data lookups except the AI sub-category.
    """

    CLOUD_SERVICES = "上云服务"
    COMPANY_SERVICES = "公司服务"
    ROBOTS = "泛机器人"
    ARTIFICIAL_INTELLIGENCE = "人工智能"
    SECURITY_SERVICES = "安全服务"
    BLOCKCHAIN = "区块链"
    WEBSITE_PROMOTION = "建站推广"
    INDUSTRIAL_APPLICATIONS = "工业应用"
    API_SERVICES = "API服务"


@unique
class BaiduMarketplaceSubcategory(StrEnum):
    """Enums representing the sub-categories of the Baidu AI Cloud marketplace compared by the crawler.

    Attributes:
        ARTIFICIAL_INTELLIGENCE (str): The AI APIs (人工智能), the only APIs kept.
        HARDWARE (str): The AI hardware (硬件产品).
        SECURITY_CONSULTING (str): The security consulting (安全咨询).
        SECURITY_TESTING (str): The security testing (安全测试).
        INCIDENT_HANDLING (str): The security incident handling (安全处理).
        SECURITY_SERVICES (str): The blockchain security services (安全服务).
        CUSTOM_WEBSITE (str): The custom website building (定制建站).
        CONTENT_MAINTENANCE (str): The website content maintenance (内容维护).
        SHOP_OPERATION (str): The shop operation (店铺运营).
        MARKETING_PROMOTION (str): The marketing and promotion (营销推广).
        WEBSITE_HOSTING (str): The website hosting (建站主机).
        MAINTENANCE_SERVICES (str): The industrial maintenance services (运维服务).
    """

    ARTIFICIAL_INTELLIGENCE = "人工智能"
    HARDWARE = "硬件产品"
    SECURITY_CONSULTING = "安全咨询"
    SECURITY_TESTING = "安全测试"
    INCIDENT_HANDLING = "安全处理"
    SECURITY_SERVICES = "安全服务"
    CUSTOM_WEBSITE = "定制建站"
    CONTENT_MAINTENANCE = "内容维护"
    SHOP_OPERATION = "店铺运营"
    MARKETING_PROMOTION = "营销推广"
    WEBSITE_HOSTING = "建站主机"
    MAINTENANCE_SERVICES = "运维服务"


@unique
class BaiduMarketplaceResponseField(StrEnum):
    """Enums representing the fields of a Baidu AI Cloud marketplace API response.

    Attributes:
        RESULT (str): The result of the response, the category list of the category tree.
    """

    RESULT = "result"


@unique
class BaiduMarketplaceResultField(StrEnum):
    """Enums representing the fields of the result of a Baidu AI Cloud marketplace API response.

    Attributes:
        RESULT (str): The products of a category products page.
        PRODUCT (str): The product of a product detail.
        ERR_CODE (str): The error code of a product detail without product.
    """

    RESULT = "result"
    PRODUCT = "product"
    ERR_CODE = "errCode"


@unique
class BaiduMarketplaceTreeField(StrEnum):
    """Enums representing the fields of a category of the Baidu AI Cloud marketplace category tree.

    Attributes:
        NAME (str): The name of the category.
        CHILDREN (str): The sub-categories of a top category.
        CID (str): The identifier of the category.
    """

    NAME = "name"
    CHILDREN = "children"
    CID = "cid"


@unique
class BaiduMarketplaceListedField(StrEnum):
    """Enums representing the fields of a product of a Baidu AI Cloud marketplace category products page.

    Attributes:
        PID (str): The identifier of the product.
    """

    PID = "pid"


@unique
class BaiduMarketplaceRelatedField(StrEnum):
    """Enums representing the fields of a related product of the Baidu AI Cloud marketplace.

    Attributes:
        PRODUCT_ID (str): The identifier of the product.
    """

    PRODUCT_ID = "productId"


@unique
class BaiduMarketplaceProductField(StrEnum):
    """Enums representing the fields of the product of a Baidu AI Cloud marketplace product detail.

    Attributes:
        PRODUCT_INFO (str): The product information.
        VENDOR_INFO (str): The vendor information.
        CRUMB_INFO (str): The breadcrumb of the categories of the product.
    """

    PRODUCT_INFO = "productInfo"
    VENDOR_INFO = "vendorInfo"
    CRUMB_INFO = "crumbInfo"


@unique
class BaiduMarketplaceInfoField(StrEnum):
    """Enums representing the fields of the information of a Baidu AI Cloud marketplace product.

    Attributes:
        PID (str): The identifier of the product.
        TITLE (str): The title of the product.
        DIGEST (str): The description of the product.
        DELIVERY_METHOD (str): The delivery method (`BaiduMarketplaceDelivery`).
    """

    PID = "pid"
    TITLE = "title"
    DIGEST = "digest"
    DELIVERY_METHOD = "deliveryMethod"


@unique
class BaiduMarketplaceVendorField(StrEnum):
    """Enums representing the fields of the vendor of a Baidu AI Cloud marketplace product.

    Attributes:
        VENDOR_NAME (str): The name of the vendor.
    """

    VENDOR_NAME = "vendorName"


@unique
class BaiduMarketplaceCrumbField(StrEnum):
    """Enums representing the fields of a crumb of the breadcrumb of a Baidu AI Cloud marketplace product.

    Attributes:
        NAME (str): The name of the category.
        CID (str): The identifier of the category.
    """

    NAME = "name"
    CID = "cid"


@unique
class BaiduMarketplaceSitemapPath(StrEnum):
    """Enums representing the first path segments of the Baidu AI Cloud marketplace sitemap pages.

    Attributes:
        DETAIL (str): A product page (`/detail/{pid}`).
    """

    DETAIL = "detail"
