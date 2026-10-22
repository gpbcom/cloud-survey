from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class YandexPageStateField(StrEnum):
    """Enums representing the fields of the state the Yandex Cloud pages embed (`__DATA__ = {...}`).

    Attributes:
        PROPS (str): The page properties.
        CONTEXT (str): The page context.
        PAGE_PROPS (str): The properties of the marketplace pages (`props.pageProps`).
        DATA (str): The data of a marketplace page (`props.pageProps.data`).
        SERVICES_DATA (str): The services data of a services page (`context.servicesData`).
    """

    PROPS = "props"
    CONTEXT = "context"
    PAGE_PROPS = "pageProps"
    DATA = "data"
    SERVICES_DATA = "servicesData"


@unique
class YandexServiceField(StrEnum):
    """Enums representing the fields of the services data of the Yandex Cloud services pages.

    Attributes:
        CATEGORIES (str): The service groups.
        DATA_BY_CATEGORY (str): The services of each group, by group slug.
        SLUG (str): The slug of a group or of a service.
        NAME (str): The name of a group or of a service.
        DESCRIPTION (str): The description of a service.
        EXTERNAL_URL (str): The external website of a service.
    """

    CATEGORIES = "categories"
    DATA_BY_CATEGORY = "dataByCategory"
    SLUG = "slug"
    NAME = "name"
    DESCRIPTION = "description"
    EXTERNAL_URL = "externalUrl"


@unique
class YandexServiceGroup(StrEnum):
    """Enums representing the slugs of the Yandex Cloud service groups handled by the catalogue crawler.

    Attributes:
        FEATURED (str): The featured services, a selection of the other groups, not a category.
        AVAILABLE_IN_REGION (str): Every service available in the region.
    """

    FEATURED = "featured"
    AVAILABLE_IN_REGION = "available-in-region"


@unique
class YandexLocale(StrEnum):
    """Enums representing the locales of the Yandex Cloud website.

    Attributes:
        ENGLISH (str): The international (English) website, the default locale of the service pages.
    """

    ENGLISH = "en"


@unique
class YandexHttpHeader(StrEnum):
    """Enums representing the HTTP headers set by the Yandex Cloud crawlers.

    Attributes:
        USER_AGENT (str): The user agent, naming the crawler.
    """

    USER_AGENT = "User-Agent"


@unique
class YandexProductField(StrEnum):
    """Enums representing the fields of the Yandex Cloud Marketplace selections, products and categories.

    Attributes:
        CATEGORIES (str): The selections of the home page, and the categories of a product.
        PRODUCTS (str): The products of a selection.
        TITLE (str): The title of a selection or of a category.
        NAME (str): The name of a product, of a publisher or of a category (its slug).
        ID (str): The identifier of a product.
        TYPE (str): The product type, the delivery method.
        MARKETING_INFO (str): The marketing information of a product or of a publisher.
        SHORT_DESCRIPTION (str): The short description of a product.
        DESCRIPTION (str): The HTML description of a product.
        PUBLISHER (str): The publisher of a product.
        CREATED_AT (str): The creation date of a product.
        UPDATED_AT (str): The update date of a product.
    """

    CATEGORIES = "categories"
    PRODUCTS = "products"
    TITLE = "title"
    NAME = "name"
    ID = "id"
    TYPE = "type"
    MARKETING_INFO = "marketingInfo"
    SHORT_DESCRIPTION = "shortDescription"
    DESCRIPTION = "description"
    PUBLISHER = "publisher"
    CREATED_AT = "createdAt"
    UPDATED_AT = "updatedAt"


@unique
class YandexMarketplaceCategory(StrEnum):
    """Enums representing the slugs of the Yandex Cloud Marketplace selections which are not categories.

    Attributes:
        RECOMMENDED (str): The recommended products.
        LATEST_PRODUCTS (str): The new arrivals.
    """

    RECOMMENDED = "recommended"
    LATEST_PRODUCTS = "latest-products"


@unique
class YandexProductType(StrEnum):
    """Enums representing the types of the Yandex Cloud Marketplace products.

    Attributes:
        COMPUTE_IMAGE (str): A virtual machine image.
        BAREMETAL (str): A bare metal server image.
        BAREMETAL_EXTEND (str): An extended bare metal server image.
        COS (str): A Container Optimized Solution image.
        K8S (str): A Kubernetes application.
        SAAS (str): A software as a service.
        CLOUD_APP (str): A cloud application.
        DATALENS_DATASET (str): A DataLens dataset, data and not software.
        DATALENS_GEOLAYER (str): A DataLens geolayer, data and not software.
    """

    COMPUTE_IMAGE = "COMPUTE_IMAGE"
    BAREMETAL = "BAREMETAL"
    BAREMETAL_EXTEND = "BAREMETAL_EXTEND"
    COS = "COS"
    K8S = "K8S"
    SAAS = "SAAS"
    CLOUD_APP = "CLOUD_APP"
    DATALENS_DATASET = "DATALENS_DATASET"
    DATALENS_GEOLAYER = "DATALENS_GEOLAYER"


@unique
class YandexMarketplaceRequestMeta(StrEnum):
    """Enums representing the meta keys of the Yandex Cloud Marketplace requests.

    Attributes:
        PRODUCT (str): Marks a product page request, holding the requested URL.
        SITEMAP (str): Marks the sitemap request.
    """

    PRODUCT = "product"
    SITEMAP = "sitemap"
