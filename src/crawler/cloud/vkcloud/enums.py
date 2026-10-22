from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class VkCloudCmsComponent(StrEnum):
    """Enums representing the CMS components of the VK Cloud pages read by the catalogue crawler.

    Attributes:
        HEADER_MENU (str): The products menu of the page header.
    """

    HEADER_MENU = "header.header-menu"


@unique
class VkCloudCmsField(StrEnum):
    """Enums representing the fields of the CMS objects of the VK Cloud catalogue page (flight data).

    Attributes:
        COMPONENT (str): The CMS component of an object, e.g. the header menu.
        CATALOG (str): The services catalogue.
        ITEMS (str): The items of a CMS object, e.g. the groups of the catalogue.
        TITLE (str): The title of a group, a card, a service or a link.
        SERVICES (str): The service cards of a catalogue group.
        SERVICE (str): The service of a catalogue card.
        TEXT (str): The description of a service or a link.
        URL (str): The link object of a service or a link, and the page URL of a link object.
        DROPDOWN (str): The products of a menu group.
        DROPDOWN_ITEMS (str): The other products of a menu group.
    """

    COMPONENT = "__component"
    CATALOG = "catalog"
    ITEMS = "items"
    TITLE = "title"
    SERVICES = "services"
    SERVICE = "service"
    TEXT = "text"
    URL = "url"
    DROPDOWN = "dropdown"
    DROPDOWN_ITEMS = "dropdown_items"


@unique
class VkCloudCatalogueField(StrEnum):
    """Enums representing the fields of the response of the VK Cloud marketplace catalogue API.

    Attributes:
        DATA (str): The listed software.
    """

    DATA = "data"


@unique
class VkCloudSoftwareField(StrEnum):
    """Enums representing the fields of the VK Cloud marketplace catalogue entries.

    Attributes:
        TITLE (str): The software name.
        TEXT (str): The software description.
        HREF (str): The software page, relative to the website.
        COMPANY (str): The company selling the software.
        DEVELOPER (str): Its developer.
        PROVIDER (str): Its provider.
        TAGS (str): The typed tags of the software.
        LABELS (str): The typed tags of the software, when it has no `tags`.
        RELEASE_DATE (str): When the marketplace entry was released or last updated.
    """

    TITLE = "title"
    TEXT = "text"
    HREF = "href"
    COMPANY = "company"
    DEVELOPER = "developer"
    PROVIDER = "provider"
    TAGS = "tags"
    LABELS = "labels"
    RELEASE_DATE = "releaseDate"


@unique
class VkCloudTagField(StrEnum):
    """Enums representing the fields of the tags of the VK Cloud marketplace catalogue entries.

    Attributes:
        TYPE (str): The tag type, e.g. `category`.
        TITLE (str): The tag label, e.g. a category name.
        TAG (str): The tag identifier, e.g. a category slug or a product type.
    """

    TYPE = "type"
    TITLE = "title"
    TAG = "tag"


@unique
class VkCloudTagType(StrEnum):
    """Enums representing the types of the tags of the VK Cloud marketplace catalogue entries.

    Attributes:
        CATEGORY (str): The tags naming a marketplace category.
        PRODUCT_TYPE (str): The tags naming how a software is delivered.
    """

    CATEGORY = "category"
    PRODUCT_TYPE = "product_type"


@unique
class VkCloudProductType(StrEnum):
    """Enums representing the product type tags of the VK Cloud marketplace catalogue entries.

    Attributes:
        IMAGE_BASED (str): A virtual machine image.
        SAAS (str): A software as a service.
        APPLICATION (str): An offer sold on request (`Заявка`).
    """

    IMAGE_BASED = "image_based"
    SAAS = "saas"
    APPLICATION = "application"


@unique
class VkCloudHost(StrEnum):
    """Enums representing the hosts of the VK Cloud website.

    Attributes:
        CURRENT (str): The current host of the website.
        LEGACY (str): The former host of the website, redirected to the current one.
        LEGACY_WWW (str): The `www.` alias of the former host.
    """

    CURRENT = "cloud.vk.ru"
    LEGACY = "cloud.vk.com"
    LEGACY_WWW = "www.cloud.vk.com"
