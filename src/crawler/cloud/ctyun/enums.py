from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class ChinaTelecomHomeTab(StrEnum):
    """Enums representing the China Telecom Cloud home page tabs which are not categories.

    Attributes:
        POPULAR_PRODUCTS (str): The popular products (热门产品), also listed under their categories.
    """

    POPULAR_PRODUCTS = "热门产品"


@unique
class ChinaTelecomMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the China Telecom Cloud marketplace crawler.

    Attributes:
        PAGE (str): The page number of an offer catalog request, from 1.
        CLASSES (str): The mark of the class tree request.
    """

    PAGE = "page"
    CLASSES = "classes"


@unique
class ChinaTelecomClass(StrEnum):
    """Enums representing the classes of the China Telecom Cloud marketplace menu.

    Attributes:
        APPLICATION (str): The enterprise applications.
        INDUSTRY (str): The industry applications.
        BASIC (str): The basic software.
        SITE_BUILD (str): The website building tools.
        DEVOPS (str): The development and operations tools.
        COURSE (str): The courses, which hold no software.
    """

    APPLICATION = "application"
    INDUSTRY = "industry"
    BASIC = "basic"
    SITE_BUILD = "site_build"
    DEVOPS = "devops"
    COURSE = "course"


@unique
class ChinaTelecomSubclass(StrEnum):
    """Enums representing the China Telecom Cloud marketplace sub-classes which hold no software.

    Attributes:
        PROFESSIONAL_SERVICES (str): The professional services.
        HARDWARE (str): The hardware.
    """

    PROFESSIONAL_SERVICES = "10060"
    HARDWARE = "3030"


@unique
class ChinaTelecomDeliverMode(StrEnum):
    """Enums representing the delivery modes of the China Telecom Cloud marketplace offers, casefolded.

    Attributes:
        SERVICE (str): An offline delivered service, not a software.
        SAAS (str): A software as a service.
        IMAGE (str): A virtual machine image.
        MIRROR (str): A virtual machine image (mirror).
        API (str): An API.
        LICENSE (str): A license to download.
        SOFTWARE (str): A software to download.
    """

    SERVICE = "service"
    SAAS = "saas"
    IMAGE = "image"
    MIRROR = "mirror"
    API = "api"
    LICENSE = "license"
    SOFTWARE = "software"


@unique
class ChinaTelecomOfferState(StrEnum):
    """Enums representing the states of the China Telecom Cloud marketplace offers.

    Attributes:
        ONLINE (str): An offer on sale.
    """

    ONLINE = "online"


@unique
class ChinaTelecomOfferDisplay(StrEnum):
    """Enums representing the display flags of the China Telecom Cloud marketplace offers.

    Attributes:
        HIDDEN (str): An offer not displayed.
    """

    HIDDEN = "false"


@unique
class ChinaTelecomResponseField(StrEnum):
    """Enums representing the fields of a China Telecom Cloud marketplace API response.

    Attributes:
        DATA (str): The data of the response.
    """

    DATA = "data"


@unique
class ChinaTelecomDataField(StrEnum):
    """Enums representing the fields of the data of a China Telecom Cloud marketplace API response.

    Attributes:
        ITEM (str): The offers of a catalog page.
        LIST (str): The classes of the class tree.
        TOTAL (str): The total number of offers.
    """

    ITEM = "item"
    LIST = "list"
    TOTAL = "total"


@unique
class ChinaTelecomClassField(StrEnum):
    """Enums representing the fields of a class or sub-class of the China Telecom Cloud class tree.

    Attributes:
        CLASS_ID (str): The identifier of a class.
        SUBCLASS_ID (str): The identifier of a sub-class.
        NAME (str): The name of the class or sub-class.
    """

    CLASS_ID = "classId"
    SUBCLASS_ID = "subclassId"
    NAME = "name"


@unique
class ChinaTelecomOfferField(StrEnum):
    """Enums representing the fields of a China Telecom Cloud marketplace offer.

    Attributes:
        NAME (str): The name of the offer.
        NOTE (str): The description of the offer.
        CLASS (str): The class identifier.
        SUBCLASS (str): The sub-class identifier.
        DELIVER_MODE (str): The delivery mode.
        DELIVER_NAME (str): The name of the delivery mode.
        STATE (str): The state of the offer.
        DISPLAY (str): Whether the offer is displayed.
        DETAIL_URL (str): The page link.
        OWNER (str): The store selling the offer.
    """

    NAME = "name"
    NOTE = "note"
    CLASS = "class"
    SUBCLASS = "subclass"
    DELIVER_MODE = "deliverMode"
    DELIVER_NAME = "deliverName"
    STATE = "state"
    DISPLAY = "display"
    DETAIL_URL = "detailUrl"
    OWNER = "owner"


@unique
class ChinaTelecomOwnerField(StrEnum):
    """Enums representing the fields of the store selling a China Telecom Cloud marketplace offer.

    Attributes:
        NAME (str): The name of the store.
    """

    NAME = "name"
