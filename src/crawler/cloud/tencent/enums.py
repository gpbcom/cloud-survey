from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class TencentCrawlerMeta(StrEnum):
    """Enums representing the request meta keys of the Tencent Cloud catalogue crawler.

    Attributes:
        DOC_ID (str): The documentation id of a product page request.
        DOC_CATALOGUE (str): The product URL of a product documentation request.
        DOC_ARTICLE (str): The product URL of an overview article request.
    """

    DOC_ID = "doc_id"
    DOC_CATALOGUE = "doc_catalogue"
    DOC_ARTICLE = "doc_article"


@unique
class TencentCardClass(StrEnum):
    """Enums representing the CSS classes of the elements of the Tencent Cloud products page.

    Attributes:
        CATEGORY_HEADING (str): A category heading.
        SUBCATEGORY_HEADING (str): A subcategory heading.
        LINK_ITEM (str): A link which is not a product card.
    """

    CATEGORY_HEADING = "v3-product-menu-card-tit"
    SUBCATEGORY_HEADING = "v3-product-menu-child-card-tit"
    LINK_ITEM = "v3-link-item"


@unique
class TencentDocsGroup(StrEnum):
    """Enums representing the Tencent Cloud documentation groups which are not products, casefolded.

    Attributes:
        MORE (str): The miscellaneous documentation.
    """

    MORE = "more"


@unique
class TencentDocsSlug(StrEnum):
    """Enums representing the Tencent Cloud documentation entries which are not products, by slug.

    Attributes:
        CLOUDAPP (str): The marketplace.
        SDK (str): The SDK.
        SPLA (str): The announcements.
        PARTNER (str): The partners.
        LIVING_RECORD (str): The records.
        MESSAGE (str): The messages.
    """

    CLOUDAPP = "cloudapp"
    SDK = "sdk"
    SPLA = "spla"
    PARTNER = "partner"
    LIVING_RECORD = "living-record"
    MESSAGE = "message"


@unique
class TencentNextDataField(StrEnum):
    """Enums representing the fields of the Next.js data of the Tencent Cloud pages.

    Attributes:
        PROPS (str): The page properties.
        PAGE_PROPS (str): The properties of the page component, within the page properties.
    """

    PROPS = "props"
    PAGE_PROPS = "pageProps"


@unique
class TencentDocsPagePropsField(StrEnum):
    """Enums representing the fields of the page component properties of the Tencent Cloud documentation pages.

    Attributes:
        CATALOGUE_LIST (str): The documentation groups of the documentation home page.
        DATA (str): The table of contents of a product documentation.
        DETAIL_CONTENT (str): The content of an article.
    """

    CATALOGUE_LIST = "catalogueList"
    DATA = "data"
    DETAIL_CONTENT = "detailContent"


@unique
class TencentDocsEntryField(StrEnum):
    """Enums representing the fields of a group or entry of the Tencent Cloud documentation home page.

    Attributes:
        ID (str): The documentation id of the entry.
        TITLE (str): The title of the group or entry.
        SLUG (str): The product slug of the entry.
        URL (str): The link of the entry.
        CHILDREN (str): The child entries.
    """

    ID = "id"
    TITLE = "title"
    SLUG = "slug"
    URL = "url"
    CHILDREN = "children"


@unique
class TencentDocsDataField(StrEnum):
    """Enums representing the fields of the table of contents of a Tencent Cloud product documentation.

    Attributes:
        LIST (str): The top level sections.
    """

    LIST = "list"


@unique
class TencentDocsSectionField(StrEnum):
    """Enums representing the fields of a section or article of a Tencent Cloud product documentation.

    Attributes:
        TITLE (str): The title of the section or article.
        LINK (str): The path of the article.
        CHILDREN (str): The articles of the section.
    """

    TITLE = "title"
    LINK = "link"
    CHILDREN = "children"


@unique
class TencentArticleField(StrEnum):
    """Enums representing the fields of the content of a Tencent Cloud documentation article.

    Attributes:
        DESCRIPTION (str): The description of the article.
        SLATE (str): The rich text of the article, a JSON document.
    """

    DESCRIPTION = "description"
    SLATE = "slate"


@unique
class TencentSlateField(StrEnum):
    """Enums representing the fields of a rich text node of a Tencent Cloud documentation article.

    Attributes:
        TYPE (str): The type of the node.
        TEXT (str): The text of the node.
        CHILDREN (str): The child nodes.
    """

    TYPE = "type"
    TEXT = "text"
    CHILDREN = "children"


@unique
class TencentSlateType(StrEnum):
    """Enums representing the types of the rich text nodes of a Tencent Cloud documentation article.

    Attributes:
        PARAGRAPH (str): A paragraph.
    """

    PARAGRAPH = "p"


@unique
class TencentMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Tencent Cloud marketplace crawler.

    Attributes:
        SOURCE (str): The source of a page (`TencentMarketplaceSource`).
        PAGE (str): The number of a product list page.
    """

    SOURCE = "source"
    PAGE = "page"


@unique
class TencentMarketplaceSource(StrEnum):
    """Enums representing the sources read by the Tencent Cloud marketplace crawler.

    Attributes:
        CLASSES (str): The product classes.
        PRODUCTS (str): The product list.
        GOODS (str): The SPU goods of the marketplace home page.
    """

    CLASSES = "classes"
    PRODUCTS = "products"
    GOODS = "goods"


@unique
class TencentProductCategory(StrEnum):
    """Enums representing the categories of the Tencent Cloud marketplace listed products.

    Attributes:
        SAAS (str): The SaaS products.
    """

    SAAS = "1"


@unique
class TencentProductFamily(StrEnum):
    """Enums representing the Tencent Cloud marketplace product families which are not software.

    Attributes:
        PROFESSIONAL_SERVICES (str): The professional services.
    """

    PROFESSIONAL_SERVICES = "Professional Services"


@unique
class TencentFamilyPrefix(StrEnum):
    """Enums representing the prefixes of the Tencent Cloud marketplace family names which are not families.

    Attributes:
        PCD (str): The `PCD` coded families, whose classes are ignored.
    """

    PCD = "PCD"


@unique
class TencentVendorAccount(StrEnum):
    """Enums representing the Tencent Cloud marketplace vendor accounts which are not the product publishers.

    Attributes:
        PLACEHOLDER (str): The vendor account of every listed product.
    """

    PLACEHOLDER = "200022263022"


@unique
class TencentGoodsStatus(StrEnum):
    """Enums representing the statuses of the Tencent Cloud marketplace SPU goods.

    Attributes:
        ONLINE (str): Goods on sale.
    """

    ONLINE = "onlined"


@unique
class TencentTimezone(StrEnum):
    """Enums representing the timezones of the Tencent Cloud marketplace data.

    Attributes:
        CHINA_STANDARD_TIME (str): China Standard Time, the time of the product identifiers.
    """

    CHINA_STANDARD_TIME = "Asia/Shanghai"


@unique
class TencentClassesResponseField(StrEnum):
    """Enums representing the fields of the Tencent Cloud marketplace product classes response.

    Attributes:
        DATA (str): The product classes.
    """

    DATA = "data"


@unique
class TencentClassField(StrEnum):
    """Enums representing the fields of a Tencent Cloud marketplace product class.

    Attributes:
        CLASS_NAME (str): The name of the class.
        CLASS_CODE (str): The code of the class.
        FAMILY_NAME (str): The name of the family of the class.
    """

    CLASS_NAME = "className"
    CLASS_CODE = "classCode"
    FAMILY_NAME = "familyName"


@unique
class TencentProductListField(StrEnum):
    """Enums representing the fields of a Tencent Cloud marketplace product list page.

    Attributes:
        PRD_LIST (str): The products of the page.
        PAGE_COUNT (str): The total number of products.
    """

    PRD_LIST = "prdList"
    PAGE_COUNT = "pageCount"


@unique
class TencentProductField(StrEnum):
    """Enums representing the fields of a Tencent Cloud marketplace listed product.

    Attributes:
        PRD_ID (str): The identifier of the product.
        PRD_NAME (str): The name of the product.
        INTRODUCE (str): The description of the product.
        CATEGORY_ID (str): The category of the product (`TencentProductCategory`).
        CLASS_NAMES (str): The comma separated class names of the product.
        VENDOR_ID (str): The vendor account of the product.
        VENDOR_NAME (str): The vendor name of the product.
    """

    PRD_ID = "prdID"
    PRD_NAME = "prdName"
    INTRODUCE = "introduce"
    CATEGORY_ID = "categoryID"
    CLASS_NAMES = "classNames"
    VENDOR_ID = "vendorID"
    VENDOR_NAME = "vendorName"


@unique
class TencentMarketPagePropsField(StrEnum):
    """Enums representing the fields of the page component properties of the Tencent Cloud marketplace home page.

    Attributes:
        GOODS_INFO (str): The SPU goods.
    """

    GOODS_INFO = "goodsInfo"


@unique
class TencentGoodsField(StrEnum):
    """Enums representing the fields of Tencent Cloud marketplace SPU goods.

    Attributes:
        GOODS_BASIC_INFO (str): The basic information of the goods.
        GOODS_DETAIL_INFO (str): The detailed information of the goods.
        GOODS_PROVIDER_INFO (str): The provider of the goods.
    """

    GOODS_BASIC_INFO = "GoodsBasicInfo"
    GOODS_DETAIL_INFO = "GoodsDetailInfo"
    GOODS_PROVIDER_INFO = "GoodsProviderInfo"


@unique
class TencentGoodsBasicField(StrEnum):
    """Enums representing the fields of the basic information of Tencent Cloud marketplace SPU goods.

    Attributes:
        SPU_ID (str): The identifier of the goods.
        STATUS (str): The status of the goods (`TencentGoodsStatus`).
    """

    SPU_ID = "SpuId"
    STATUS = "Status"


@unique
class TencentGoodsDetailField(StrEnum):
    """Enums representing the fields of the detailed information of Tencent Cloud marketplace SPU goods.

    Attributes:
        GOODS_NAME (str): The name of the goods.
        GOODS_DESCRIPTION (str): The description of the goods.
        CATEGORY_LIST (str): The categories of the goods.
    """

    GOODS_NAME = "GoodsName"
    GOODS_DESCRIPTION = "GoodsDescription"
    CATEGORY_LIST = "CategoryList"


@unique
class TencentGoodsCategoryField(StrEnum):
    """Enums representing the fields of a category of Tencent Cloud marketplace SPU goods.

    Attributes:
        CATEGORY_ID (str): The identifier of the category.
        CATEGORY_NAME (str): The name of the category.
    """

    CATEGORY_ID = "CategoryId"
    CATEGORY_NAME = "CategoryName"


@unique
class TencentGoodsProviderField(StrEnum):
    """Enums representing the fields of the provider of Tencent Cloud marketplace SPU goods.

    Attributes:
        PROVIDER_NAME (str): The name of the provider.
    """

    PROVIDER_NAME = "ProviderName"


@unique
class TencentPriceField(StrEnum):
    """Enums representing the fields of the CVM purchase API answers (instance types of a region and their prices).

    Attributes:
        DATA (str): The answer of the proxied call.
        RESPONSE (str): The response of the CVM API.
        ERROR (str): The error of a refused call.
        CODE (str): The code of that error.
        QUOTAS (str): The instance types of the zones of the region, each with its price.
        ZONE (str): The availability zone of an instance type.
        INSTANCE_TYPE (str): The instance type, e.g. `S5.MEDIUM4`.
        INSTANCE_FAMILY (str): Its family, e.g. `S5`.
        TYPE_NAME (str): The name of its family (in Chinese).
        CPU (str): Its vCPUs.
        MEMORY (str): Its memory, in GiB.
        GPU (str): Its GPUs (a fraction for a shared GPU).
        CPU_TYPE (str): Its processor.
        STATUS (str): Whether it is sold in the zone (`SELL`) or sold out (`SOLD_OUT`).
        PRICE (str): Its price.
        UNIT_PRICE (str): The hourly list price (first step).
        UNIT_PRICE_DISCOUNT (str): The hourly price (first step).
        SECOND_STEP_PRICE (str): The hourly price of the second step.
        THIRD_STEP_PRICE (str): The hourly price of the third step.
        CHARGE_UNIT (str): The unit of the hourly prices (`HOUR`).
        ORIGINAL_PRICE (str): The monthly list price.
        DISCOUNT_PRICE (str): The monthly price.
        ONE_YEAR_PRICE (str): The price of one year paid at once.
        THREE_YEARS_PRICE (str): The price of three years paid at once.
        FIVE_YEARS_PRICE (str): The price of five years paid at once.
        SIX_YEARS_PRICE (str): The price of six years paid at once.
    """

    DATA = "data"
    RESPONSE = "Response"
    ERROR = "Error"
    CODE = "Code"
    QUOTAS = "InstanceTypeQuotaSet"
    ZONE = "Zone"
    INSTANCE_TYPE = "InstanceType"
    INSTANCE_FAMILY = "InstanceFamily"
    TYPE_NAME = "TypeName"
    CPU = "Cpu"
    MEMORY = "Memory"
    GPU = "Gpu"
    CPU_TYPE = "CpuType"
    STATUS = "Status"
    PRICE = "Price"
    UNIT_PRICE = "UnitPrice"
    UNIT_PRICE_DISCOUNT = "UnitPriceDiscount"
    SECOND_STEP_PRICE = "UnitPriceDiscountSecondStep"
    THIRD_STEP_PRICE = "UnitPriceDiscountThirdStep"
    CHARGE_UNIT = "ChargeUnit"
    ORIGINAL_PRICE = "OriginalPrice"
    DISCOUNT_PRICE = "DiscountPrice"
    ONE_YEAR_PRICE = "DiscountPriceOneYear"
    THREE_YEARS_PRICE = "DiscountPriceThreeYears"
    FIVE_YEARS_PRICE = "DiscountPriceFiveYears"
    SIX_YEARS_PRICE = "DiscountPriceSixYears"


@unique
class TencentChargeType(StrEnum):
    """Enums representing the CVM charge types, the filter of a purchase API call.

    Attributes:
        POSTPAID (str): Pay as you go, billed by the hour.
        PREPAID (str): Paid in advance, by month or by years.
    """

    POSTPAID = "POSTPAID_BY_HOUR"
    PREPAID = "PREPAID"
