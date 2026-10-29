from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class AwsDirectoryParameter(StrEnum):
    """Enums representing the query parameters of the AWS products directory search API.

    Attributes:
        DIRECTORY_ID (str): The directory searched.
        LOCALE (str): The language of the directory entries.
        SORT_BY (str): The field the entries are sorted by.
        SORT_ORDER (str): The order of the entries.
        SIZE (str): The entries read per page.
        PAGE (str): The page number, from 0.
        TAG_ID (str): A tag the entries carry (a What's New year, as the search reads at most 10,000 entries).
    """

    DIRECTORY_ID = "item.directoryId"
    LOCALE = "item.locale"
    SORT_BY = "sort_by"
    SORT_ORDER = "sort_order"
    SIZE = "size"
    PAGE = "page"
    TAG_ID = "tags.id"


@unique
class AwsDirectoryParameterValue(StrEnum):
    """Enums representing the values of the AWS products directory search parameters.

    Attributes:
        PRODUCTS_DIRECTORY (str): The directory of the product cards.
        ENGLISH (str): The English (United States) locale.
        TITLE_FIELD (str): The card title, the sort field.
        ASCENDING (str): The ascending sort order.
        FIRST_PAGE (str): The first page number.
        WHATS_NEW_DIRECTORY (str): The directory of the What's New announcements (the dated source).
        POST_DATE_FIELD (str): The publication of an announcement, the sort field of the dated source.
    """

    PRODUCTS_DIRECTORY = "products-cards-interactive-aws-products-ams"
    ENGLISH = "en_US"
    TITLE_FIELD = "item.additionalFields.title"
    ASCENDING = "asc"
    FIRST_PAGE = "0"
    WHATS_NEW_DIRECTORY = "whats-new-v2"
    POST_DATE_FIELD = "item.additionalFields.postDateTime"


@unique
class AwsDirectoryField(StrEnum):
    """Enums representing the fields of the AWS products directory pages and of their entries.

    Attributes:
        METADATA (str): The metadata of a page.
        TOTAL_HITS (str): The number of entries of the directory, in the page metadata.
        ITEMS (str): The entries of a page.
        ITEM (str): The item of an entry.
        TAGS (str): The tags of an entry.
        DATE_UPDATED (str): The last update of the card of an item.
        ADDITIONAL_FIELDS (str): The card fields of an item.
    """

    METADATA = "metadata"
    TOTAL_HITS = "totalHits"
    ITEMS = "items"
    ITEM = "item"
    TAGS = "tags"
    DATE_UPDATED = "dateUpdated"
    ADDITIONAL_FIELDS = "additionalFields"


@unique
class AwsCardField(StrEnum):
    """Enums representing the card fields (`additionalFields`) of an AWS products directory item.

    Attributes:
        TITLE (str): The product name.
        BODY (str): The product description, an HTML fragment.
        CTA_LINK (str): The link to the product page.
        PUBLISHED_DATE (str): The publication of the card.
        BADGE (str): The category badge, a JSON text.
    """

    TITLE = "title"
    BODY = "body"
    CTA_LINK = "ctaLink"
    PUBLISHED_DATE = "publishedDate"
    BADGE = "badge"


@unique
class AwsTagField(StrEnum):
    """Enums representing the fields of a tag of an AWS products directory entry.

    Attributes:
        NAME (str): The tag value, e.g. a launch year or a category label.
        TAG_NAMESPACE_ID (str): The tag namespace.
    """

    NAME = "name"
    TAG_NAMESPACE_ID = "tagNamespaceId"


@unique
class AwsTagNamespace(StrEnum):
    """Enums representing the tag namespaces of the AWS products directory entries.

    Attributes:
        YEAR (str): The launch year of a product.
        TECHNOLOGY_CATEGORY (str): The technology categories of a product.
        WHATS_NEW_PRODUCT (str): The products a What's New announcement is about.
    """

    YEAR = "GLOBAL#local-tags-year"
    TECHNOLOGY_CATEGORY = "GLOBAL#aws-technology-categories"
    WHATS_NEW_PRODUCT = "whats-new-v2#general-products"


@unique
class AwsBadgeField(StrEnum):
    """Enums representing the fields of the category badge of an AWS products directory card.

    Attributes:
        VALUE (str): The category labels.
    """

    VALUE = "value"


@unique
class AwsDocsSection(StrEnum):
    """Enums representing the sections of the AWS documentation home page which do not list services.

    Attributes:
        DECISION_GUIDES (str): The decision guides.
        SDK_TOOLKITS (str): The SDKs and toolkits.
        GENERAL_REFERENCE (str): The general reference.
        ADDITIONAL_RESOURCES (str): The additional resources.
        FEATURED_SERVICES (str): The featured services, repeated in their own sections.
        CONSOLE (str): The console documentation.
        CUSTOMER_ENABLEMENT (str): The customer enablement documentation.
    """

    DECISION_GUIDES = "decision_guides"
    SDK_TOOLKITS = "sdktoolkits"
    GENERAL_REFERENCE = "genref"
    ADDITIONAL_RESOURCES = "addtlrcs"
    FEATURED_SERVICES = "featuredsvcs"
    CONSOLE = "console"
    CUSTOMER_ENABLEMENT = "custenable"


@unique
class AwsDocsLink(StrEnum):
    """Enums representing the vocabulary of the links of the AWS documentation home page.

    Attributes:
        CAMPAIGN (str): The query parameter naming the section of a link.
        HOMEPAGE_PREFIX (str): The prefix of the section of a link.
    """

    CAMPAIGN = "icmpid"
    HOMEPAGE_PREFIX = "docs_homepage_"


@unique
class AwsHtmlTag(StrEnum):
    """Enums representing the HTML elements compared by the AWS catalogue crawler.

    Attributes:
        ARTICLE (str): A section of the documentation home page, holding its title.
    """

    ARTICLE = "article"


@unique
class AwsMarketplaceMeta(StrEnum):
    """Enums representing the request meta keys of the AWS Marketplace crawler.

    Attributes:
        FULFILLMENT_OPTION (str): The queried fulfillment option.
        PAGE (str): The page number within a fulfillment option, from 1.
        INTEGRATION_ID (str): The integration identifier of the marketplace pages.
        LISTING_PAGE (str): Marks a listing page request, holding the software identity.
    """

    FULFILLMENT_OPTION = "fulfillment_option"
    PAGE = "page"
    INTEGRATION_ID = "integration_id"
    LISTING_PAGE = "listing_page"


@unique
class AwsPageMeta(StrEnum):
    """Enums representing the `meta` tags read on the AWS Marketplace pages.

    Attributes:
        INTEGRATION_ID (str): The integration identifier of the marketplace pages.
    """

    INTEGRATION_ID = "integrationId"


@unique
class AwsFulfillmentOption(StrEnum):
    """Enums representing the software fulfillment options of the AWS Marketplace listings.

    Attributes:
        SAAS (str): A software as a service subscription.
        AMAZON_MACHINE_IMAGE (str): A machine image.
        CONTAINER (str): A container image.
        HELM (str): A Helm chart.
        EKS_ADD_ON (str): An Amazon EKS add-on.
        CLOUDFORMATION_TEMPLATE (str): A CloudFormation template.
        EC2_IMAGE_BUILDER_COMPONENT (str): An EC2 Image Builder component.
        SAGEMAKER_MODEL (str): A SageMaker model package.
        SAGEMAKER_ALGORITHM (str): A SageMaker algorithm.
        API (str): An API.
    """

    SAAS = "SAAS"
    AMAZON_MACHINE_IMAGE = "AMAZON_MACHINE_IMAGE"
    CONTAINER = "CONTAINER"
    HELM = "HELM"
    EKS_ADD_ON = "EKS_ADD_ON"
    CLOUDFORMATION_TEMPLATE = "CLOUDFORMATION_TEMPLATE"
    EC2_IMAGE_BUILDER_COMPONENT = "EC2_IMAGE_BUILDER_COMPONENT"
    SAGEMAKER_MODEL = "SAGEMAKER_MODEL"
    SAGEMAKER_ALGORITHM = "SAGEMAKER_ALGORITHM"
    API = "API"


@unique
class AwsSearchRequestField(StrEnum):
    """Enums representing the fields of a `SearchListings` request of the AWS Marketplace discovery service.

    Attributes:
        MAX_RESULTS (str): The listings read per page.
        REQUEST_CONTEXT (str): The context of the request.
        INTEGRATION_ID (str): The integration identifier, in the request context.
        FILTERS (str): The search filters.
        TYPE (str): The type of a filter.
        VALUES (str): The values of a filter.
        NEXT_TOKEN (str): The cursor of the requested page.
    """

    MAX_RESULTS = "MaxResults"
    REQUEST_CONTEXT = "RequestContext"
    INTEGRATION_ID = "IntegrationId"
    FILTERS = "Filters"
    TYPE = "Type"
    VALUES = "Values"
    NEXT_TOKEN = "NextToken"


@unique
class AwsSearchFilterType(StrEnum):
    """Enums representing the filter types of a `SearchListings` request.

    Attributes:
        FULFILLMENT_OPTION_TYPE (str): The fulfillment option of the listings.
    """

    FULFILLMENT_OPTION_TYPE = "FULFILLMENT_OPTION_TYPE"


@unique
class AwsProxyEnvelopeField(StrEnum):
    """Enums representing the fields of the envelope sent to the AWS Marketplace discovery API proxy.

    Attributes:
        REGION (str): The region of the discovery service.
        HEADERS (str): The headers of the proxied request.
        CONTENT_STRING (str): The proxied request, a JSON text.
        METHOD (str): The HTTP method of the proxied request.
        OPERATION (str): The operation of the discovery service.
        PATH (str): The path of the proxied request.
    """

    REGION = "region"
    HEADERS = "headers"
    CONTENT_STRING = "contentString"
    METHOD = "method"
    OPERATION = "operation"
    PATH = "path"


@unique
class AwsDiscoveryHeader(StrEnum):
    """Enums representing the headers of the request proxied to the AWS Marketplace discovery service.

    Attributes:
        ACCEPT (str): The accepted media type.
        CONTENT_TYPE (str): The media type of the request content.
        TARGET (str): The operation targeted.
    """

    ACCEPT = "Accept"
    CONTENT_TYPE = "Content-Type"
    TARGET = "X-Amz-Target"


@unique
class AwsProxyHeader(StrEnum):
    """Enums representing the headers of the request sent to the AWS Marketplace discovery API proxy.

    Attributes:
        CONTENT_TYPE (str): The media type of the envelope.
    """

    CONTENT_TYPE = "content-type"


@unique
class AwsMediaType(StrEnum):
    """Enums representing the media types of the AWS Marketplace discovery requests.

    Attributes:
        JSON (str): A JSON document.
        AMZ_JSON (str): An AWS JSON 1.1 protocol document.
    """

    JSON = "application/json"
    AMZ_JSON = "application/x-amz-json-1.1"


@unique
class AwsDiscoveryOperation(StrEnum):
    """Enums representing the operations of the AWS Marketplace discovery service.

    Attributes:
        SEARCH_LISTINGS (str): The search of the listings.
        SEARCH_LISTINGS_TARGET (str): The search of the listings, qualified by its service (`X-Amz-Target`).
    """

    SEARCH_LISTINGS = "SearchListings"
    SEARCH_LISTINGS_TARGET = "AWSMPDiscoveryService.SearchListings"


@unique
class AwsRegion(StrEnum):
    """Enums representing the AWS regions of the AWS Marketplace discovery service.

    Attributes:
        US_EAST_1 (str): The North Virginia region.
    """

    US_EAST_1 = "us-east-1"


@unique
class AwsSearchPageField(StrEnum):
    """Enums representing the fields of a `SearchListings` response page.

    Attributes:
        LISTING_SUMMARIES (str): The listings of the page.
        NEXT_TOKEN (str): The cursor of the next page.
        TOTAL_RESULTS (str): The number of listings of the search.
    """

    LISTING_SUMMARIES = "ListingSummaries"
    NEXT_TOKEN = "NextToken"
    TOTAL_RESULTS = "TotalResults"


@unique
class AwsListingField(StrEnum):
    """Enums representing the fields of an AWS Marketplace listing summary and of its nested objects.

    Attributes:
        ID (str): The listing identifier.
        DISPLAY_ATTRIBUTES (str): The display attributes of the listing.
        TITLE (str): The listing title, in its display attributes.
        SHORT_DESCRIPTION (str): The short description, in its display attributes.
        LONG_DESCRIPTION (str): The long description, in its display attributes.
        FULFILLMENT_OPTION_TYPES (str): The fulfillment options of the listing.
        LISTING_CREATOR (str): The creator of the listing.
        ASSOCIATED_ENTITIES (str): The products associated to the listing.
        MANUFACTURER (str): The manufacturer of an associated product.
        CATEGORIES (str): The categories of the listing.
        DISPLAY_NAME (str): The display name of a creator, a manufacturer or a category.
        VALUE (str): The code of a fulfillment option or of a category.
        PARENT_VALUE (str): The code of the parent of a category.
    """

    ID = "Id"
    DISPLAY_ATTRIBUTES = "DisplayAttributes"
    TITLE = "Title"
    SHORT_DESCRIPTION = "ShortDescription"
    LONG_DESCRIPTION = "LongDescription"
    FULFILLMENT_OPTION_TYPES = "FulfillmentOptionTypes"
    LISTING_CREATOR = "ListingCreator"
    ASSOCIATED_ENTITIES = "AssociatedEntities"
    MANUFACTURER = "Manufacturer"
    CATEGORIES = "Categories"
    DISPLAY_NAME = "DisplayName"
    VALUE = "Value"
    PARENT_VALUE = "ParentValue"


@unique
class AwsIntegrationId(StrEnum):
    """Enums representing the known integration identifiers of the AWS Marketplace pages.

    Attributes:
        MARKETPLACE_PAGES (str): The identifier used when the browse page holds none.
    """

    MARKETPLACE_PAGES = "integ-kzv5xkq73lzjw"


@unique
class AwsWhatsNewField(StrEnum):
    """Enums representing the fields of a What's New announcement.

    Attributes:
        HEADLINE (str): Its title.
        POST_DATE_TIME (str): When it was published, ISO 8601.
    """

    HEADLINE = "headline"
    POST_DATE_TIME = "postDateTime"


@unique
class AwsOfferField(StrEnum):
    """Enums representing the fields of the AWS Price List bulk API indexes.

    Attributes:
        OFFERS (str): The offers (services) of the offer index.
        OFFER_CODE (str): The code of an offer, e.g. `AmazonEC2`.
        CURRENT_REGION_INDEX_URL (str): The region index of the current version of an offer.
        REGIONS (str): The regions of a region index.
        REGION_CODE (str): The code of a region.
        CURRENT_VERSION_URL (str): The price file of an offer in a region (its version in its path).
        CURRENT_SAVINGS_PLAN_INDEX_URL (str): The region index of the savings plan of an offer.
        VERSION_URL (str): The price file of a savings plan in a region.
    """

    OFFERS = "offers"
    OFFER_CODE = "offerCode"
    CURRENT_REGION_INDEX_URL = "currentRegionIndexUrl"
    REGIONS = "regions"
    REGION_CODE = "regionCode"
    CURRENT_VERSION_URL = "currentVersionUrl"
    CURRENT_SAVINGS_PLAN_INDEX_URL = "currentSavingsPlanIndexUrl"
    VERSION_URL = "versionUrl"


@unique
class AwsPriceColumn(StrEnum):
    """Enums representing the columns of an AWS Price List CSV price file read for the prices.

    Attributes:
        SKU (str): The product SKU.
        OFFER_TERM_CODE (str): The term of the price.
        RATE_CODE (str): The price dimension (SKU, term and rate), unique.
        TERM_TYPE (str): `OnDemand` or `Reserved`.
        PRICE_DESCRIPTION (str): The price written out.
        EFFECTIVE_DATE (str): Since when the price applies.
        STARTING_RANGE (str): The quantity from which a tier price applies.
        ENDING_RANGE (str): The quantity up to which it applies (`Inf` without bound).
        UNIT (str): What the price is per, e.g. `Hrs`, `GB-Mo`.
        PRICE_PER_UNIT (str): The price.
        CURRENCY (str): Its currency.
        LEASE_CONTRACT_LENGTH (str): The term of a reservation (`1yr`, `3yr`).
        PURCHASE_OPTION (str): How a reservation is paid (`No Upfront`, `All Upfront`...).
        OFFERING_CLASS (str): The class of a reservation (`standard`, `convertible`).
        PRODUCT_FAMILY (str): The family of the product, e.g. `Compute Instance`.
        SERVICE_NAME (str): The service, e.g. `Amazon Elastic Compute Cloud`.
        LOCATION (str): The location, e.g. `EU (Paris)`.
        INSTANCE_TYPE (str): The instance type.
        VCPU (str): Its virtual CPUs.
        MEMORY (str): Its memory, e.g. `128 GiB`.
        OPERATING_SYSTEM (str): Its operating system.
        DATABASE_ENGINE (str): The database engine (RDS).
        TENANCY (str): Its tenancy.
        LICENSE_MODEL (str): Its license model.
        PRE_INSTALLED_SW (str): Its pre-installed software.
        CAPACITY_STATUS (str): The capacity status of an EC2 line (`Used`, or a reservation accounting line).
        USAGE_TYPE (str): The usage type, e.g. `EUW3-BoxUsage:m5.large`.
        OPERATION (str): The operation, e.g. `RunInstances`.
    """

    SKU = "SKU"
    OFFER_TERM_CODE = "OfferTermCode"
    RATE_CODE = "RateCode"
    TERM_TYPE = "TermType"
    PRICE_DESCRIPTION = "PriceDescription"
    EFFECTIVE_DATE = "EffectiveDate"
    STARTING_RANGE = "StartingRange"
    ENDING_RANGE = "EndingRange"
    UNIT = "Unit"
    PRICE_PER_UNIT = "PricePerUnit"
    CURRENCY = "Currency"
    LEASE_CONTRACT_LENGTH = "LeaseContractLength"
    PURCHASE_OPTION = "PurchaseOption"
    OFFERING_CLASS = "OfferingClass"
    PRODUCT_FAMILY = "Product Family"
    SERVICE_NAME = "serviceName"
    LOCATION = "Location"
    INSTANCE_TYPE = "Instance Type"
    VCPU = "vCPU"
    MEMORY = "Memory"
    OPERATING_SYSTEM = "Operating System"
    DATABASE_ENGINE = "Database Engine"
    TENANCY = "Tenancy"
    LICENSE_MODEL = "License Model"
    PRE_INSTALLED_SW = "Pre Installed S/W"
    CAPACITY_STATUS = "CapacityStatus"
    USAGE_TYPE = "usageType"
    OPERATION = "operation"


@unique
class AwsTermType(StrEnum):
    """Enums representing the term types of an AWS price.

    Attributes:
        ON_DEMAND (str): Pay as you go.
        RESERVED (str): A reservation.
    """

    ON_DEMAND = "OnDemand"
    RESERVED = "Reserved"


@unique
class AwsLeaseLength(StrEnum):
    """Enums representing the terms of an AWS reservation.

    Attributes:
        ONE_YEAR (str): One year.
        THREE_YEARS (str): Three years.
    """

    ONE_YEAR = "1yr"
    THREE_YEARS = "3yr"


@unique
class AwsCapacityStatus(StrEnum):
    """Enums representing the capacity status of an EC2 price line.

    Attributes:
        USED (str): The price of a running instance (the other statuses repeat it for reservation accounting).
    """

    USED = "Used"


@unique
class AwsSavingsColumn(StrEnum):
    """Enums representing the columns of an AWS savings plan CSV price file.

    Attributes:
        RATE_CODE (str): The rate (savings plan and discounted usage), unique.
        UNIT (str): What the rate is per, e.g. `Hrs`.
        EFFECTIVE_DATE (str): Since when the rate applies.
        DISCOUNTED_RATE (str): The rate.
        CURRENCY (str): Its currency.
        DISCOUNTED_SERVICE_CODE (str): The offer of the discounted usage, e.g. `AmazonEC2`.
        DISCOUNTED_USAGE_TYPE (str): The discounted usage, e.g. `EUW3-BoxUsage:m8g.24xlarge`.
        DISCOUNTED_OPERATION (str): The discounted operation, e.g. `RunInstances` (Linux).
        PURCHASE_OPTION (str): How the plan is paid (`No Upfront`, `All Upfront`...).
        LEASE_CONTRACT_LENGTH (str): The term of the plan, e.g. `1`.
        LEASE_CONTRACT_LENGTH_UNIT (str): Its unit, e.g. `year`.
        DESCRIPTION (str): The plan written out.
        PRODUCT_FAMILY (str): The kind of plan, e.g. `ComputeSavingsPlans`.
        DISCOUNTED_REGION_CODE (str): The region of the discounted usage.
        DISCOUNTED_INSTANCE_TYPE (str): The instance type of the discounted usage.
    """

    RATE_CODE = "RateCode"
    UNIT = "Unit"
    EFFECTIVE_DATE = "EffectiveDate"
    DISCOUNTED_RATE = "DiscountedRate"
    CURRENCY = "Currency"
    DISCOUNTED_SERVICE_CODE = "DiscountedServiceCode"
    DISCOUNTED_USAGE_TYPE = "DiscountedUsageType"
    DISCOUNTED_OPERATION = "DiscountedOperation"
    PURCHASE_OPTION = "PurchaseOption"
    LEASE_CONTRACT_LENGTH = "LeaseContractLength"
    LEASE_CONTRACT_LENGTH_UNIT = "LeaseContractLengthUnit"
    DESCRIPTION = "Description"
    PRODUCT_FAMILY = "Product Family"
    DISCOUNTED_REGION_CODE = "DiscountedRegionCode"
    DISCOUNTED_INSTANCE_TYPE = "DiscountedInstanceType"
