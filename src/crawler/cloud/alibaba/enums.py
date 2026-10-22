from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class AlibabaCrawlerMeta(StrEnum):
    """Enums representing the request meta keys of the Alibaba Cloud catalogue crawler.

    Attributes:
        HELP_SLUG (str): The documentation slug of a product page request.
        HELP_LANDING (str): The slug of a documentation landing page request.
        HELP_ARTICLE (str): The product URL of an overview article request.
    """

    HELP_SLUG = "help_slug"
    HELP_LANDING = "help_landing"
    HELP_ARTICLE = "help_article"


@unique
class AlibabaPageSource(StrEnum):
    """Enums representing the sources of the pages read by the Alibaba Cloud catalogue crawler.

    Attributes:
        NAV (str): The navigation product tree.
        HELP (str): The documentation website.
        SITEMAP (str): The sitemap of the product pages.
        CARDS (str): The "All products" page and the product pages.
    """

    NAV = "nav"
    HELP = "help"
    SITEMAP = "sitemap"
    CARDS = "cards"


@unique
class AlibabaCardsSection(StrEnum):
    """Enums representing the "All products" sections of Alibaba Cloud which are not products, casefolded.

    Attributes:
        ALIBABA_CLOUD_ACADEMY (str): The certifications.
    """

    ALIBABA_CLOUD_ACADEMY = "alibaba cloud academy"


@unique
class AlibabaHelpBlock(StrEnum):
    """Enums representing the Alibaba Cloud documentation blocks which are not products, casefolded.

    Attributes:
        GETTING_STARTED (str): The getting started guides.
        SOLUTIONS (str): The solutions.
        MEMBERSHIP_SERVICE (str): The membership service.
        MORE (str): The miscellaneous documentation.
    """

    GETTING_STARTED = "getting started"
    SOLUTIONS = "solutions"
    MEMBERSHIP_SERVICE = "membership service"
    MORE = "more"


@unique
class AlibabaHelpArticleSlug(StrEnum):
    """Enums representing the slugs of the Alibaba Cloud documentation overview articles.

    Attributes:
        WHAT_IS (str): The prefix of the "What is" articles, preferred.
        PRODUCT_INTRODUCTION (str): The product introduction section, which opens its first article.
    """

    WHAT_IS = "what-is"
    PRODUCT_INTRODUCTION = "product-introduction"


@unique
class AlibabaPageNotice(StrEnum):
    """Enums representing the notices of the Alibaba Cloud product pages, casefolded.

    Attributes:
        NOT_FOR_SALE (str): The notice of the retired product pages.
    """

    NOT_FOR_SALE = "no longer available for sale"


@unique
class AlibabaNavTreeField(StrEnum):
    """Enums representing the fields of the Alibaba Cloud navigation product tree.

    Attributes:
        DETAILED_CATEGORIES (str): The top navigation categories.
    """

    DETAILED_CATEGORIES = "detailedCategories"


@unique
class AlibabaNavCategoryField(StrEnum):
    """Enums representing the fields of a category of the Alibaba Cloud navigation product tree.

    Attributes:
        NAME (str): The name of the category.
        URL (str): The page of the category.
        PRODUCTS (str): The products of the category.
        SUB_CATEGORIES (str): The subcategories of the category.
    """

    NAME = "name"
    URL = "url"
    PRODUCTS = "products"
    SUB_CATEGORIES = "subCategories"


@unique
class AlibabaNavProductField(StrEnum):
    """Enums representing the fields of a product of the Alibaba Cloud navigation product tree.

    Attributes:
        NAME (str): The name of the product.
        URL (str): The product page.
        SHORT_DESC (str): The description of the product.
    """

    NAME = "name"
    URL = "url"
    SHORT_DESC = "shortDesc"


@unique
class AlibabaCardsDataField(StrEnum):
    """Enums representing the fields of the product cards data of the Alibaba Cloud "All products" page.

    Attributes:
        CONTENT (str): The sections of the cards.
    """

    CONTENT = "content"


@unique
class AlibabaCardsSectionField(StrEnum):
    """Enums representing the fields of a section of the Alibaba Cloud "All products" cards.

    Attributes:
        FIRST_LEVEL_HEAD (str): The title of the section.
        PRODUCT_CARD (str): The card groups of the section.
    """

    FIRST_LEVEL_HEAD = "FirstLevelHead"
    PRODUCT_CARD = "productCard"


@unique
class AlibabaCardsGroupField(StrEnum):
    """Enums representing the fields of a card group of the Alibaba Cloud "All products" cards.

    Attributes:
        CARD_TITLE (str): The title of the group.
        CARD_LIST (str): The cards of the group.
    """

    CARD_TITLE = "cardTitle"
    CARD_LIST = "cardList"


@unique
class AlibabaCardField(StrEnum):
    """Enums representing the fields of a card of the Alibaba Cloud "All products" page.

    Attributes:
        TITLE (str): The name of the product.
        URL (str): The product page link, relative to the website.
        DESC (str): The description of the product.
    """

    TITLE = "title"
    URL = "url"
    DESC = "desc"


@unique
class AlibabaMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Alibaba Cloud marketplace crawler.

    Attributes:
        TOP (str): The identifier of the top category of a result page.
        PAGE (str): The number of a result page.
    """

    TOP = "top"
    PAGE = "page"


@unique
class AlibabaMarketplaceTop(StrEnum):
    """Enums representing the Alibaba Cloud marketplace top categories which are not software.

    Attributes:
        PROFESSIONAL_SERVICE (str): The professional services.
    """

    PROFESSIONAL_SERVICE = "Professional Service"


@unique
class AlibabaMarketplaceQuery(StrEnum):
    """Enums representing the query parameters of the Alibaba Cloud marketplace links.

    Attributes:
        CATEGORY_ID (str): The category identifier of a category link.
    """

    CATEGORY_ID = "categoryId"


@unique
class AlibabaMenuClass(StrEnum):
    """Enums representing the CSS classes of the items of the Alibaba Cloud marketplace category menu.

    Attributes:
        TITLE (str): A top category, followed by its sub-categories.
    """

    TITLE = "title"


@unique
class AlibabaCardInfo(StrEnum):
    """Enums representing the labels of the details of an Alibaba Cloud marketplace product card.

    Attributes:
        DELIVERY_METHOD (str): The delivery method of the product.
    """

    DELIVERY_METHOD = "Delivery Method:"


@unique
class AlibabaCardDelivery(StrEnum):
    """Enums representing the delivery methods of the Alibaba Cloud marketplace product cards, casefolded.

    Attributes:
        IMAGE (str): A virtual machine image.
        SAAS (str): A software as a service.
        API (str): An API.
        SERVICE (str): A service, not a software.
    """

    IMAGE = "image"
    SAAS = "saas"
    API = "api"
    SERVICE = "service"


@unique
class AlibabaProductCodePrefix(StrEnum):
    """Enums representing the prefixes of the Alibaba Cloud marketplace product codes giving a delivery.

    Attributes:
        SERVICE (str): A service, not a software.
        IMAGE (str): A virtual machine image.
        SAAS (str): A software as a service.
        API (str): An API.
    """

    SERVICE = "cmfw"
    IMAGE = "cmjj"
    SAAS = "cmgj"
    API = "cmapi"
