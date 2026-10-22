from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class VolcanoEngineMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Volcano Engine marketplace crawler.

    Attributes:
        PAGE (str): The page number of a product list request, from 1.
        CATEGORIES (str): The mark of the front category tree request.
    """

    PAGE = "page"
    CATEGORIES = "categories"


@unique
class VolcanoEngineApiAction(StrEnum):
    """Enums representing the actions of the Volcano Engine marketplace portal API.

    Attributes:
        LIST_PRODUCT (str): The product list, by pages.
        QUERY_FRONT_CATEGORY (str): The front category tree.
    """

    LIST_PRODUCT = "ListProduct"
    QUERY_FRONT_CATEGORY = "QueryFrontCategory"


@unique
class VolcanoEngineListParameter(StrEnum):
    """Enums representing the fields of the body of a Volcano Engine product list request.

    Attributes:
        OFFSET (str): The position of the first product of the page.
        LIMIT (str): The products read per page.
    """

    OFFSET = "Offset"
    LIMIT = "Limit"


@unique
class VolcanoEngineResponseField(StrEnum):
    """Enums representing the fields of a Volcano Engine marketplace portal API response.

    Attributes:
        RESULT (str): The result of the action.
    """

    RESULT = "Result"


@unique
class VolcanoEngineResultField(StrEnum):
    """Enums representing the fields of the result of a Volcano Engine marketplace portal API response.

    Attributes:
        LIST (str): The products of the page, or the front category tree.
        TOTAL (str): The total number of products.
    """

    LIST = "List"
    TOTAL = "Total"


@unique
class VolcanoEngineCategoryField(StrEnum):
    """Enums representing the fields of a Volcano Engine front category.

    Attributes:
        ID (str): The identifier of the category.
        CATEGORY_NAME_CN (str): The Chinese name of the category.
    """

    ID = "ID"
    CATEGORY_NAME_CN = "CategoryNameCN"


@unique
class VolcanoEngineProductField(StrEnum):
    """Enums representing the fields of a Volcano Engine marketplace product.

    Attributes:
        PRODUCT_BASIC (str): The basic information of the product.
        PRODUCT_INFO (str): The other information of the product.
    """

    PRODUCT_BASIC = "ProductBasic"
    PRODUCT_INFO = "ProductInfo"


@unique
class VolcanoEngineProductBasicField(StrEnum):
    """Enums representing the fields of the basic information of a Volcano Engine marketplace product.

    Attributes:
        PRODUCT (str): The identifier of the product.
        PRODUCT_TITLE (str): The title of the product.
        ZH_NAME (str): The Chinese name of the product, when it has no title.
        PRODUCT_DESC (str): The description of the product.
        DELIVER_TYPE (str): The delivery type of the product.
        CREATED_TIME (str): The listing date, in epoch seconds.
        FRONTEND_CATEGORY_L1 (str): The identifier of the top front category.
        FRONTEND_CATEGORY_L1_NAME (str): The name of the top front category.
        FRONTEND_CATEGORY_L2 (str): The identifier of the front sub-category.
        FRONTEND_CATEGORY_L2_NAME (str): The name of the front sub-category.
    """

    PRODUCT = "Product"
    PRODUCT_TITLE = "ProductTitle"
    ZH_NAME = "ZhName"
    PRODUCT_DESC = "ProductDesc"
    DELIVER_TYPE = "DeliverType"
    CREATED_TIME = "CreatedTime"
    FRONTEND_CATEGORY_L1 = "FrontendCategoryL1"
    FRONTEND_CATEGORY_L1_NAME = "FrontendCategoryL1Name"
    FRONTEND_CATEGORY_L2 = "FrontendCategoryL2"
    FRONTEND_CATEGORY_L2_NAME = "FrontendCategoryL2Name"


@unique
class VolcanoEngineProductInfoField(StrEnum):
    """Enums representing the fields of the other information of a Volcano Engine marketplace product.

    Attributes:
        PRODUCT (str): The identifier of the product.
        SHOP (str): The shop selling the product.
        CHILD_PRODUCT_NAME (str): The product type.
        CREATED_TIME (str): The listing date, in epoch seconds.
    """

    PRODUCT = "Product"
    SHOP = "Shop"
    CHILD_PRODUCT_NAME = "ChildProductName"
    CREATED_TIME = "CreatedTime"


@unique
class VolcanoEngineShopField(StrEnum):
    """Enums representing the fields of the shop of a Volcano Engine marketplace product.

    Attributes:
        SRV_ACCOUNT_VERIFY_NAME (str): The verified company name of the shop.
        SHOP (str): The shop name.
    """

    SRV_ACCOUNT_VERIFY_NAME = "SrvAccountVerifyName"
    SHOP = "Shop"


@unique
class VolcanoEngineProductTypeKeyword(StrEnum):
    """Enums representing the keywords of the Volcano Engine product types giving a delivery method, casefolded.

    Attributes:
        IMAGE (str): An image (镜像), a virtual machine.
        MCP (str): An MCP server, an API.
        SAAS (str): A software as a service.
    """

    IMAGE = "镜像"
    MCP = "mcp"
    SAAS = "saas"
