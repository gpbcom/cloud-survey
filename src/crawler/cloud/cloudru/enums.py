from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CloudRuProductField(StrEnum):
    """Enums representing the fields of the Cloud.ru catalogue (flight data) and of its products.

    Attributes:
        PRODUCTS (str): The products of the catalogue.
        CATEGORIES (str): The catalogue tabs, and the tabs a product is filed under.
        SLUG (str): The slug of a product or of a tab.
        TITLE (str): The name of a product or the label of a tab.
        DESCRIPTION (str): The product description.
        CUSTOM_LINK (str): The custom page of a product.
        AVAILABLE (str): Whether the product is available.
    """

    PRODUCTS = "products"
    CATEGORIES = "categories"
    SLUG = "slug"
    TITLE = "title"
    DESCRIPTION = "description"
    CUSTOM_LINK = "customLink"
    AVAILABLE = "available"


@unique
class CloudRuCatalogueTab(StrEnum):
    """Enums representing the slugs of the Cloud.ru catalogue tabs handled by the crawler.

    Attributes:
        POPULAR (str): The `Популярное` tab, a selection of products, not a category.
    """

    POPULAR = "popular"


@unique
class CloudRuCardField(StrEnum):
    """Enums representing the fields of the Cloud.ru marketplace listing (flight data), cards and records.

    Attributes:
        CARDS (str): The cards of the listing.
        CATEGORIES (str): The taxonomy of the listing, and the category slugs of a card.
        SLUG (str): The slug of a category, a card or a software record.
        DISPLAY_NAME (str): The label of a category, the software name of a card.
        NAME (str): The name of a selection of a card.
        ID (str): The identifier of a product type of a card.
        SELECTION (str): The selections of a card, sub-categories of its category.
        PRODUCT_TYPES (str): The product types of a card.
        PREVIEW_TEXT (str): The software description of a card.
        REDIRECT_URL (str): The console page of the software of a card.
        LICENSE (str): The licence of a software record.
        OWNER (str): The licence owner, the publisher.
        CREATED_AT (str): The creation date of a software record.
        UPDATED_AT (str): The last edit date of a software record.
    """

    CARDS = "cards"
    CATEGORIES = "categories"
    SLUG = "slug"
    DISPLAY_NAME = "displayName"
    NAME = "name"
    ID = "id"
    SELECTION = "selection"
    PRODUCT_TYPES = "productTypes"
    PREVIEW_TEXT = "previewText"
    REDIRECT_URL = "redirectUrl"
    LICENSE = "license"
    OWNER = "owner"
    CREATED_AT = "createdAt"
    UPDATED_AT = "updatedAt"


@unique
class CloudRuProductType(StrEnum):
    """Enums representing the product types of the Cloud.ru marketplace cards.

    Attributes:
        VM_IMAGE (str): A virtual machine image.
        DOCKER_IMAGE (str): A container image.
        ADDONS (str): A Kubernetes add-on.
    """

    VM_IMAGE = "vm-image"
    DOCKER_IMAGE = "docker-image"
    ADDONS = "addons"


@unique
class CloudRuMarketplaceCategory(StrEnum):
    """Enums representing the slugs of the Cloud.ru marketplace categories telling the delivery of their software.

    Attributes:
        MCP_SERVERS (str): The MCP servers.
        AI_AGENTS (str): The AI agents.
    """

    MCP_SERVERS = "mcp-servers"
    AI_AGENTS = "ai-agents"


@unique
class CloudRuRequestMeta(StrEnum):
    """Enums representing the meta keys of the Cloud.ru marketplace page requests.

    Attributes:
        CARD (str): The listing card of the software of the page.
        TAXONOMY (str): The labels of the categories of the card, by slug.
    """

    CARD = "card"
    TAXONOMY = "taxonomy"


@unique
class CloudRuTariffField(StrEnum):
    """Enums representing the fields of the tariff documents flight data (navigation and price tables).

    Attributes:
        HREF (str): The path of a navigation entry.
        TITLE (str): Its title, e.g. `Тарифы «Evolution Compute». Приложение №7.EVO.1.`.
        COLUMN_DEFINITIONS (str): The columns of a price table.
        DATA (str): Its rows, by column key.
        HEADER (str): The header of a column.
        ACCESSOR_KEY (str): The key of a column in the rows.
    """

    HREF = "href"
    TITLE = "title"
    COLUMN_DEFINITIONS = "columnDefinitions"
    DATA = "data"
    HEADER = "header"
    ACCESSOR_KEY = "accessorKey"


@unique
class CloudRuTariffColumn(StrEnum):
    """Enums representing the column headers of the tariff tables (their start).

    Attributes:
        NAME (str): The service or resource priced.
        UNIT (str): Its unit, e.g. `шт.` or `ГБ`.
        PERIOD (str): Its billing period, e.g. `час`.
        PRICE_WITHOUT_VAT (str): The price without VAT.
        PRICE_WITH_VAT (str): The price with VAT (its one-letter Cyrillic preposition escaped).
    """

    NAME = "Наименование"
    UNIT = "Единица тарификации"
    PERIOD = "Период тарификации"
    PRICE_WITHOUT_VAT = "Цена, без НДС"
    PRICE_WITH_VAT = "Цена \u0441 НДС"


@unique
class CloudRuTariffUnit(StrEnum):
    """Enums representing the units of the tariff tables.

    Attributes:
        PIECE (str): An item (an instance, a vCPU, an address, a license).
        GB (str): A gigabyte.
        TB (str): A terabyte.
    """

    PIECE = "шт."
    GB = "ГБ"
    TB = "ТБ"


@unique
class CloudRuTariffPeriod(StrEnum):
    """Enums representing the billing periods of the tariff tables.

    Attributes:
        HOUR (str): An hour.
        DAY (str): A day.
        MONTH (str): A month.
        YEAR (str): A year.
        ONCE (str): Billed once.
    """

    HOUR = "час"
    DAY = "сутки"
    MONTH = "месяц"
    YEAR = "год"
    ONCE = "разово"
