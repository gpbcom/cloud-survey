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


@unique
class VolcanoEnginePriceField(StrEnum):
    """Enums representing the fields of the Volcano Engine anonymous price API, read for the prices.

    Attributes:
        RESULT (str): The result of a call.
        NAVIGATION (str): The products of the price navigation (a JSON text).
        CHILDREN (str): The children of a navigation node.
        NAME (str): The name of a navigation category.
        PRODUCT (str): The code of a product.
        PRODUCT_ZH_NAME (str): Its Chinese name.
        TEMPLATE_INFO_LIST (str): Its templates.
        TEMPLATE_CODE (str): The code of a template.
        TYPE (str): The kind of template (1 the price details, 2 the calculator).
        LIST (str): The templates of a template listing.
        TEMPLATE (str): The definition of a template (a JSON text).
        TABLE_LIST (str): The price tables of a template.
        ROWS (str): The rows of a table.
        CONFIGURATION_CODE (str): The configuration of a row, e.g. `ecs.c3il.12xlarge`.
        CHARGE_ITEM_CODE (str): Its charge item, its region as suffix.
        PRICE_INFO_LIST (str): Its prices.
        PERIOD (str): The period of a price (`hourly`, `monthly`).
        TIMES (str): The periods it is for (12 monthly periods: a year).
        PRICE (str): The price, as text.
        PRICING_FUNCTION (str): How it applies (`fixed_price`, `full_progressive`).
        MEASURE_INTERVAL (str): The tier bounds of a progressive price, e.g. `0,8,127`.
        PRICE_INTERVAL (str): The tier prices of a progressive price.
        UNIT (str): The unit of a charge item, e.g. `GiB`, `台`.
        CONFIGURATION_NAME (str): The name of its configuration.
        DISPLAY_NAME (str): The name of the charge item.
        REGION (str): Its region.
        BILLING_BY_USAGE (str): Whether it is billed by its usage (else by its configuration over time).
    """

    RESULT = "Result"
    NAVIGATION = "Navigation"
    CHILDREN = "Children"
    NAME = "Name"
    PRODUCT = "Product"
    PRODUCT_ZH_NAME = "ProductZhName"
    TEMPLATE_INFO_LIST = "TemplateInfoList"
    TEMPLATE_CODE = "TemplateCode"
    TYPE = "Type"
    LIST = "List"
    TEMPLATE = "Template"
    TABLE_LIST = "TableList"
    ROWS = "Rows"
    CONFIGURATION_CODE = "ConfigurationCode"
    CHARGE_ITEM_CODE = "ChargeItemCode"
    PRICE_INFO_LIST = "PriceInfoList"
    PERIOD = "Period"
    TIMES = "Times"
    PRICE = "Price"
    PRICING_FUNCTION = "PricingFunction"
    MEASURE_INTERVAL = "MeasureInterval"
    PRICE_INTERVAL = "PriceInterval"
    UNIT = "Unit"
    CONFIGURATION_NAME = "ConfigurationName"
    DISPLAY_NAME = "DisplayName"
    REGION = "Region"
    BILLING_BY_USAGE = "BillingByUsage"


@unique
class VolcanoEnginePriceAction(StrEnum):
    """Enums representing the actions of the Volcano Engine anonymous price API.

    Attributes:
        NAVIGATION (str): The products and their templates.
        TEMPLATE (str): The definition of a template (its charge items and units).
        TABLE (str): The prices of a template.
    """

    NAVIGATION = "GetNavigationV2"
    TEMPLATE = "ListTemplate"
    TABLE = "GetTable"


@unique
class VolcanoEnginePeriod(StrEnum):
    """Enums representing the periods of a Volcano Engine price.

    Attributes:
        HOURLY (str): Pay as you go, by the hour.
        MONTHLY (str): A subscription, by the month.
    """

    HOURLY = "hourly"
    MONTHLY = "monthly"


@unique
class VolcanoEngineUnit(StrEnum):
    """Enums representing the units of the Volcano Engine charge items.

    Attributes:
        MACHINE (str): A machine (`台`).
        PIECE (str): A piece (`个`).
        VCPU (str): A vCPU.
        GIB (str): A GiB.
        GB (str): A GB.
        TIMES (str): A call (`次`).
        TEN_THOUSAND_TIMES (str): Ten thousand calls (`万次`).
        THOUSAND_TOKENS (str): A thousand tokens.
        MILLION_TOKENS (str): A million tokens.
        TOKENS (str): A token.
        MACHINE_HOURS (str): A machine-hour (`台时`).
        HOURS (str): An hour (`小时`).
        MINUTES (str): A minute (`分钟`).
        ENTRIES (str): An entry (`条`).
        MILLION_SAMPLES (str): A million samples (`百万样本`).
        MILLION_ENTRIES (str): A million entries (`百万·条`).
        CHARACTERS (str): A character (`字符`).
        THOUSAND_TOKENS_SPACED (str): A thousand tokens (`1k tokens`).
        SHEETS (str): An image (`张`).
        NODE (str): A node (`节点`).
        COMPUTE_UNIT (str): A compute unit (`CU`).
        MBPS (str): A Mbps of bandwidth.
    """

    MACHINE = "台"
    PIECE = "个"
    VCPU = "vCPU"
    GIB = "GiB"
    GB = "GB"
    TIMES = "次"
    TEN_THOUSAND_TIMES = "万次"
    THOUSAND_TOKENS = "千tokens"
    MILLION_TOKENS = "百万tokens"
    TOKENS = "tokens"
    MACHINE_HOURS = "台时"
    HOURS = "小时"
    MINUTES = "分钟"
    ENTRIES = "条"
    MILLION_SAMPLES = "百万样本"
    MILLION_ENTRIES = "百万·条"
    CHARACTERS = "字符"
    THOUSAND_TOKENS_SPACED = "1k tokens"
    SHEETS = "张"
    NODE = "节点"
    COMPUTE_UNIT = "CU"
    MBPS = "Mbps"


@unique
class VolcanoEngineDocStage(StrEnum):
    """Enums representing the stages of the Volcano Engine documentation price requests.

    Attributes:
        HOME (str): The documentation home, listing every documentation library.
        LIBRARY (str): A documentation library, listing its documents.
        DOCUMENT (str): A billing document, its Markdown holding price tables.
    """

    HOME = "home"
    LIBRARY = "library"
    DOCUMENT = "document"


@unique
class VolcanoEngineDocField(StrEnum):
    """Enums representing the fields of a Volcano Engine documentation API answer.

    Attributes:
        RESULT (str): The document.
        MD_CONTENT (str): Its Markdown content.
        METADATA (str): The answer metadata.
        ERROR (str): The error of the metadata, when the call failed.
    """

    RESULT = "Result"
    MD_CONTENT = "MDContent"
    METADATA = "ResponseMetadata"
    ERROR = "Error"
