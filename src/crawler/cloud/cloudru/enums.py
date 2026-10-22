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
