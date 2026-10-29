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


@unique
class YandexPriceField(StrEnum):
    """Enums representing the fields of the Yandex Cloud price list API, read for the prices.

    Attributes:
        SKUS (str): The SKUs of a page.
        NEXT_PAGE_TOKEN (str): The token of the next page (a JSON text), empty on the last one.
        PAGE_TOKEN (str): The query parameter of a page token.
        NAME (str): The name of a SKU, e.g. `compute.vm.cpu.c100.v3`, unique.
        TRANSLATED_NAME (str): Its English name.
        SERVICE (str): Its service.
        DESCRIPTION (str): The name of the service, e.g. `API Gateway`.
        GROUP (str): The group of the service, e.g. `Serverless`.
        PRICING_UNIT (str): What the price is per, e.g. `core*hour`, `1m*request`.
        TRANSLATED_PRICING_UNIT (str): That unit in English.
        PRICING_VERSION (str): The current pricing of the SKU.
        EFFECTIVE_TIME (str): Since when it applies, in milliseconds.
        PRICING_EXPRESSION (str): Its rates.
        RATES (str): The rates, one per tier.
        START_PRICING_QUANTITY (str): The quantity from which a rate applies.
        END_PRICING_QUANTITY (str): The quantity up to which it applies, missing without bound.
        UNIT_PRICE (str): The rate, as text.
    """

    SKUS = "skus"
    NEXT_PAGE_TOKEN = "nextPageToken"
    PAGE_TOKEN = "pageToken"
    NAME = "name"
    TRANSLATED_NAME = "translatedName"
    SERVICE = "service"
    DESCRIPTION = "description"
    GROUP = "group"
    PRICING_UNIT = "pricingUnit"
    TRANSLATED_PRICING_UNIT = "translatedPricingUnit"
    PRICING_VERSION = "pricingVersion"
    EFFECTIVE_TIME = "effectiveTime"
    PRICING_EXPRESSION = "pricingExpression"
    RATES = "rates"
    START_PRICING_QUANTITY = "startPricingQuantity"
    END_PRICING_QUANTITY = "endPricingQuantity"
    UNIT_PRICE = "unitPrice"


@unique
class YandexUnitPart(StrEnum):
    """Enums representing the words of a Yandex Cloud pricing unit (`<count>*<thing>*<period>`).

    Attributes:
        CORE (str): A virtual CPU core.
        GBYTE (str): A gigabyte.
        SERVER (str): A dedicated server.
        HOUR (str): An hour.
        DAY (str): A day.
        MONTH (str): A month.
        MINUTE (str): A minute.
        SECOND (str): A second.
        SECONDS (str): Seconds.
        FIFTEEN_SECONDS (str): Fifteen seconds.
        TOKEN (str): A token of a language model.
        SYMBOL (str): A character.
        SYMBOLS (str): Characters.
        IMAGE (str): An image.
        REQUEST (str): A request.
        REQUEST_UNIT (str): A request unit.
        EVENT (str): An event.
        MESSAGE (str): A message.
        INVOCATION (str): A function invocation.
        CALL (str): A call.
        PHONE_CALL (str): A phone call.
        ROW (str): A row.
        SCAN (str): A scan.
        OBJECTS (str): Objects.
        EMAIL (str): An email.
        SMS (str): A text message.
        DIALOG (str): A dialog.
        SESSION (str): A session.
        USER (str): A user.
        UNIT (str): A unit.
        APPLICATION (str): An application.
        RESOURCE (str): A resource.
        POINT (str): A point (a monitored metric point).
        POINTS (str): Points.
    """

    CORE = "core"
    GBYTE = "gbyte"
    SERVER = "server"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    MINUTE = "minute"
    SECOND = "second"
    SECONDS = "seconds"
    FIFTEEN_SECONDS = "15sec"
    TOKEN = "token"
    SYMBOL = "symbol"
    SYMBOLS = "symbols"
    IMAGE = "image"
    REQUEST = "request"
    REQUEST_UNIT = "request_unit"
    EVENT = "event"
    MESSAGE = "message"
    INVOCATION = "invocation"
    CALL = "call"
    PHONE_CALL = "phone_call"
    ROW = "row"
    SCAN = "scan"
    OBJECTS = "objects"
    EMAIL = "email"
    SMS = "sms"
    DIALOG = "dialog"
    SESSION = "session"
    USER = "user"
    UNIT = "unit"
    APPLICATION = "application"
    RESOURCE = "resource"
    POINT = "point"
    POINTS = "points"
