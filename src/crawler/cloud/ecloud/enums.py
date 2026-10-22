from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ChinaMobileMeta(StrEnum):
    """Enums representing the request meta keys of the China Mobile Cloud crawler.

    Attributes:
        TEMPLATE_PRODUCT (str): The product page URL of a page template request.
    """

    TEMPLATE_PRODUCT = "template_product"


@unique
class ChinaMobileSituation(StrEnum):
    """Enums representing the situations (menus) of the China Mobile Cloud menu document.

    Attributes:
        PRODUCT (str): The products menu.
    """

    PRODUCT = "product"


@unique
class ChinaMobileNodeType(StrEnum):
    """Enums representing the types of the China Mobile Cloud menu nodes.

    Attributes:
        CARD (str): A promotion node, not products.
    """

    CARD = "card"


@unique
class ChinaMobileNodeName(StrEnum):
    """Enums representing the names of the China Mobile Cloud menu nodes processed apart.

    Attributes:
        CO_BRANDED (str): The co-branded 和云 node, processed last.
        RECOMMENDED (str): The recommended products (推荐产品), not a category.
        POPULAR (str): The popular products (热门产品), not a category.
        FEATURED_AI (str): The featured AI products (精选AI产品), not a category.
    """

    CO_BRANDED = "和云"
    RECOMMENDED = "推荐产品"
    POPULAR = "热门产品"
    FEATURED_AI = "精选AI产品"


@unique
class ChinaMobileResponseField(StrEnum):
    """Enums representing the fields of a China Mobile Cloud JSON response, the menu or a page template.

    Attributes:
        BODY (str): The situations of the menu, or the page template.
    """

    BODY = "body"


@unique
class ChinaMobileSituationField(StrEnum):
    """Enums representing the fields of a situation of the China Mobile Cloud menu document.

    Attributes:
        SITUATION_CODE (str): The code of the situation.
        BIND_DATA (str): The top menu nodes of the situation.
    """

    SITUATION_CODE = "situationCode"
    BIND_DATA = "bindData"


@unique
class ChinaMobileNodeField(StrEnum):
    """Enums representing the fields of a China Mobile Cloud menu node.

    Attributes:
        TYPE (str): The type of the node.
        NAME (str): The name of the node.
        BIND_METADATAS (str): The product entries of the node.
        CHILDREN (str): The child nodes.
    """

    TYPE = "type"
    NAME = "name"
    BIND_METADATAS = "bindMetadatas"
    CHILDREN = "children"


@unique
class ChinaMobileEntryField(StrEnum):
    """Enums representing the fields of a China Mobile Cloud menu product entry.

    Attributes:
        ID (str): The identifier of the entry.
        NAME (str): The product name.
        TYPE (str): The product type, the page template slug.
        INTRODUCE_URL (str): The product page link.
        S_DESC (str): The short description.
        BRIEF (str): The brief, read when the short description is a placeholder.
    """

    ID = "id"
    NAME = "name"
    TYPE = "type"
    INTRODUCE_URL = "introduceUrl"
    S_DESC = "sDesc"
    BRIEF = "brief"


@unique
class ChinaMobileEntryKey(StrEnum):
    """Enums representing the prefixes of the keys identifying a China Mobile Cloud menu entry.

    Attributes:
        ID (str): A key made of the entry identifier.
        NAME (str): A key made of the entry name.
    """

    ID = "id"
    NAME = "name"


@unique
class ChinaMobileTemplateField(StrEnum):
    """Enums representing the fields of a China Mobile Cloud page template.

    Attributes:
        SEO_DESCRIPTION (str): The SEO description of the page.
        CREATE_DATE (str): The creation date of the page.
        UPDATE_DATE (str): The update date of the page.
    """

    SEO_DESCRIPTION = "seoDescription"
    CREATE_DATE = "createDate"
    UPDATE_DATE = "updateDate"
