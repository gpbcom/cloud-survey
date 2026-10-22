from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GcpHtmlAttribute(StrEnum):
    """Enums representing the tracking attributes of the Google Cloud catalogue pages read by the crawler.

    Attributes:
        CATEGORY_ID (str): The identifier of a category filter.
        EVENT_DETAIL (str): The label of a category filter.
        MODULE_HEADLINE (str): The headline of the menu group of a menu link, if any.
        TRACK_NAME (str): The tracking name of a menu link.
    """

    CATEGORY_ID = "data-category-id"
    EVENT_DETAIL = "track-metadata-eventdetail"
    MODULE_HEADLINE = "track-metadata-module_headline"
    TRACK_NAME = "track-name"


@unique
class GcpCatalogueMeta(StrEnum):
    """Enums representing the request meta keys of the Google Cloud catalogue crawler.

    Attributes:
        CATEGORY (str): The category label of a category page request.
    """

    CATEGORY = "gcp_category"


@unique
class GcpCatalogueParameter(StrEnum):
    """Enums representing the query parameters of the Google Cloud catalogue pages.

    Attributes:
        PDS (str): The code of the category of a category page.
    """

    PDS = "pds"


@unique
class GcpHostPrefix(StrEnum):
    """Enums representing the host prefixes ignored when comparing the Google Cloud product links.

    Attributes:
        DOCS (str): The documentation sub-domain.
    """

    DOCS = "docs."


@unique
class GcpHeader(StrEnum):
    """Enums representing the request headers expected by the Google Cloud console entity service.

    Attributes:
        CONTENT_TYPE (str): The media type of the request body.
        ORIGIN (str): The origin of the request.
        REFERER (str): The page sending the request.
    """

    CONTENT_TYPE = "content-type"
    ORIGIN = "origin"
    REFERER = "referer"


@unique
class GcpMediaType(StrEnum):
    """Enums representing the media types of the Google Cloud console entity service requests.

    Attributes:
        JSON (str): A JSON document.
    """

    JSON = "application/json"


@unique
class GcpFacet(StrEnum):
    """Enums representing the facets of the Google Cloud Marketplace browse results.

    Attributes:
        CATEGORY (str): The product categories.
    """

    CATEGORY = "category"


@unique
class GcpCategoryFacetValue(StrEnum):
    """Enums representing the category facet values of the Google Cloud Marketplace queried for their path only.

    Attributes:
        MANAGED_SERVICES (str): The managed services.
        OTHERS (str): The catch-all category.
    """

    MANAGED_SERVICES = "managed-services"
    OTHERS = "others"


@unique
class GcpProductType(StrEnum):
    """Enums representing the product types of the Google Cloud Marketplace cards.

    Attributes:
        PROFESSIONAL_SERVICES (str): A professional service, not software.
        DATA (str): A dataset, not software.
        DATASETS (str): A dataset, not software.
        GOOGLE_CLOUD_PLATFORM (str): A Google Cloud service, not software.
        PROVISIONED_THROUGHPUT (str): A provisioned model throughput, not software.
        SAAS_AND_APIS (str): A software as a service or an API.
        AI_AGENT_AS_A_SERVICE (str): An AI agent as a service.
        VIRTUAL_MACHINES (str): A virtual machine image.
        KUBERNETES_APPS (str): A Kubernetes app.
        CONTAINER_IMAGES (str): A container image.
        VERTEX_AI (str): A Vertex AI model.
    """

    PROFESSIONAL_SERVICES = "Professional Services"
    DATA = "Data"
    DATASETS = "Datasets"
    GOOGLE_CLOUD_PLATFORM = "Google Cloud Platform"
    PROVISIONED_THROUGHPUT = "Provisioned Throughput"
    SAAS_AND_APIS = "SaaS & APIs"
    AI_AGENT_AS_A_SERVICE = "AI Agent as a Service"
    VIRTUAL_MACHINES = "Virtual machines"
    KUBERNETES_APPS = "Kubernetes apps"
    CONTAINER_IMAGES = "Container images"
    VERTEX_AI = "Vertex AI"


@unique
class GcpProductFamily(StrEnum):
    """Enums representing the product families of the Google Cloud Marketplace cards which are not software.

    Attributes:
        PROFESSIONAL_SERVICES_PRODUCT (str): A professional service.
        DATASET (str): A dataset.
        ANALYTICS_HUB_LISTING (str): An Analytics Hub dataset listing.
        GCP (str): A Google Cloud service.
        PROVISIONED_THROUGHPUT_PRODUCT (str): A provisioned model throughput.
    """

    PROFESSIONAL_SERVICES_PRODUCT = "ProfessionalServicesProduct"
    DATASET = "Dataset"
    ANALYTICS_HUB_LISTING = "AnalyticsHubListing"
    GCP = "GCP"
    PROVISIONED_THROUGHPUT_PRODUCT = "ProvisionedThroughputProduct"


@unique
class GcpMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the Google Cloud Marketplace crawler.

    Attributes:
        PAGE (str): The page number within a query, from 1.
        FACET (str): The facet value of a category query.
        LABEL (str): The category label of a category query.
        PATHS_ONLY (str): Marks the category queries giving their products the category path only.
    """

    PAGE = "page"
    FACET = "facet"
    LABEL = "label"
    PATHS_ONLY = "paths_only"


@unique
class GcpBrowseRequestField(StrEnum):
    """Enums representing the fields of a browse request of the Google Cloud console entity service.

    Attributes:
        ENTITY_REQUEST (str): The entity request.
        ENTITY_NAME (str): The entity requested.
        REQUEST_PAYLOAD (str): The payload of the entity request.
        PARAMETERS (str): The browse parameters.
        LOCALE (str): The language of the results.
        SOLUTION_SCOPE_ID (str): The scope of the browsed solutions.
        SELECTED_FACET_VALUES (str): The facet values filtering the results.
        FACET_ID (str): The facet of a selected facet value.
        FACET_VALUE_ID (str): The value of a selected facet value.
        QUERY (str): The search query.
        PAGE_TOKEN (str): The cursor of the requested page.
        IS_PRIVATE_CATALOG (str): Whether the private catalog is browsed.
        RESPONSE_TYPE (str): The kind of response.
        TYPE (str): The protobuf type of the payload.
        REQUEST_CONTEXT (str): The context of the request.
        PAGE_PATH (str): The console page sending the request.
    """

    ENTITY_REQUEST = "entityRequest"
    ENTITY_NAME = "entityName"
    REQUEST_PAYLOAD = "requestPayload"
    PARAMETERS = "parameters"
    LOCALE = "locale"
    SOLUTION_SCOPE_ID = "solutionScopeId"
    SELECTED_FACET_VALUES = "selectedFacetValues"
    FACET_ID = "facetId"
    FACET_VALUE_ID = "facetValueId"
    QUERY = "query"
    PAGE_TOKEN = "pageToken"
    IS_PRIVATE_CATALOG = "isPrivateCatalog"
    RESPONSE_TYPE = "responseType"
    TYPE = "@type"
    REQUEST_CONTEXT = "requestContext"
    PAGE_PATH = "pagePath"


@unique
class GcpBrowseRequestValue(StrEnum):
    """Enums representing the values of the browse request parameters of the Google Cloud console entity service.

    Attributes:
        BROWSE_PRODUCTS (str): The browse results entity.
        ENGLISH (str): The English (United States) locale.
        LAUNCHER (str): The marketplace solution scope.
        EVERYTHING (str): The query matching every product.
        SEARCH_RESULTS (str): The search results response.
    """

    BROWSE_PRODUCTS = "MARKETPLACE_BROWSE_PRODUCTS"
    ENGLISH = "en_US"
    LAUNCHER = "LAUNCHER"
    EVERYTHING = "*"
    SEARCH_RESULTS = "SEARCH_RESULTS"


@unique
class GcpBrowseResultField(StrEnum):
    """Enums representing the fields of the browse results of the Google Cloud console entity service.

    Attributes:
        SUCCESSFUL_RESULT (str): The result of a successful request.
        RESULT_DATA (str): The data of the result.
        MARKETPLACE_BROWSE_PRODUCTS (str): The browse results.
        SEARCH_RESULT (str): The search result of the browse results.
        CARDS (str): The product cards of the search result.
        FACET_VALUE_LINK_LISTS (str): The facets of the browse results.
        FACET_ID (str): The facet of a facet link list.
        FACET_VALUE_LINKS (str): The values of a facet.
        FACET_BINDING (str): The binding of a facet value.
        FACET_VALUE_ID (str): The identifier of a facet value, in its binding.
        DISPLAY_NAME (str): The label of a facet value.
        NEXT_PAGE_TOKEN (str): The cursor of the next page.
        TOTAL_COUNT (str): The number of products of the query.
    """

    SUCCESSFUL_RESULT = "successfulResult"
    RESULT_DATA = "resultData"
    MARKETPLACE_BROWSE_PRODUCTS = "marketplaceBrowseProducts"
    SEARCH_RESULT = "searchResult"
    CARDS = "cards"
    FACET_VALUE_LINK_LISTS = "facetValueLinkLists"
    FACET_ID = "facetId"
    FACET_VALUE_LINKS = "facetValueLinks"
    FACET_BINDING = "facetBinding"
    FACET_VALUE_ID = "facetValueId"
    DISPLAY_NAME = "displayName"
    NEXT_PAGE_TOKEN = "nextPageToken"
    TOTAL_COUNT = "totalCount"


@unique
class GcpCardField(StrEnum):
    """Enums representing the fields of a Google Cloud Marketplace product card.

    Attributes:
        TITLE (str): The product name.
        PRODUCT_TYPE (str): The product type.
        FAMILY_TYPE (str): The product family.
        PRODUCT_DISPLAY_NAME (str): The product identifier in its page URL.
        DESCRIPTION (str): The short description.
        LONG_DESCRIPTION (str): The long description, an HTML fragment.
        SUBTITLE (str): The publisher.
    """

    TITLE = "title"
    PRODUCT_TYPE = "productType"
    FAMILY_TYPE = "familyType"
    PRODUCT_DISPLAY_NAME = "productDisplayName"
    DESCRIPTION = "description"
    LONG_DESCRIPTION = "longDescription"
    SUBTITLE = "subtitle"
