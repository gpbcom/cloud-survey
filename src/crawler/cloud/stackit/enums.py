from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class StackitProductField(StrEnum):
    """Enums representing the fields of the STACKIT marketplace API responses and products.

    Attributes:
        ITEMS (str): The products of a listing page.
        TOTAL_COUNT (str): The number of products of the listing.
        CURSOR (str): The cursor of the next listing page.
        PRODUCT_ID (str): The product identifier.
        NAME (str): The name of a product or of its vendor.
        DELIVERY_METHOD (str): The delivery method of a product.
        SUMMARY (str): The product description.
        VENDOR (str): The product vendor, the publisher.
        CATEGORIES (str): The category labels of a product detail.
    """

    ITEMS = "items"
    TOTAL_COUNT = "totalCount"
    CURSOR = "cursor"
    PRODUCT_ID = "productId"
    NAME = "name"
    DELIVERY_METHOD = "deliveryMethod"
    SUMMARY = "summary"
    VENDOR = "vendor"
    CATEGORIES = "categories"


@unique
class StackitDeliveryMethod(StrEnum):
    """Enums representing the delivery methods of the STACKIT marketplace products.

    Attributes:
        SAAS (str): A software as a service.
        CONTAINER_IMAGE (str): A container image.
        CLOUD_IMAGE (str): A virtual machine image.
        PROFESSIONAL_SERVICE (str): A professional service, not a software.
    """

    SAAS = "SAAS"
    CONTAINER_IMAGE = "CONTAINER_IMAGE"
    CLOUD_IMAGE = "CLOUD_IMAGE"
    PROFESSIONAL_SERVICE = "PROFESSIONAL_SERVICE"


@unique
class StackitRequestMeta(StrEnum):
    """Enums representing the meta keys of the STACKIT marketplace API requests.

    Attributes:
        PAGE (str): The number of a listing page.
        PRODUCT (str): Marks a product detail request, holding the product identifier.
    """

    PAGE = "page"
    PRODUCT = "product"
