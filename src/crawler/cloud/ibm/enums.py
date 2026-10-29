from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class IbmScriptVariable(StrEnum):
    """Enums representing the script variables of the IBM Cloud catalogue page read by the crawlers.

    Attributes:
        PRELOADED_STATE (str): The variable holding the catalogue data.
    """

    PRELOADED_STATE = "window.__PRELOADED_STATE__"


@unique
class IbmStateField(StrEnum):
    """Enums representing the fields of the catalogue data embedded in the IBM Cloud catalogue page.

    Attributes:
        MODEL (str): The catalogue model.
        CATEGORIES (str): The categories of the catalogue model.
    """

    MODEL = "model"
    CATEGORIES = "categories"


@unique
class IbmCategoryField(StrEnum):
    """Enums representing the fields of a category of the IBM Cloud catalogue.

    Attributes:
        ID (str): The category identifier.
        NAME (str): The category name.
        ITEMS (str): The offers listed in the category.
    """

    ID = "id"
    NAME = "name"
    ITEMS = "items"


@unique
class IbmOfferField(StrEnum):
    """Enums representing the fields of an offer of the IBM Cloud catalogue.

    Attributes:
        ID (str): The offer identifier.
        NAME (str): The offer name.
        DESCRIPTION (str): The offer description.
        CATALOG_URL (str): The link to the offer page, usually relative to the IBM Cloud console.
        LAST_MODIFIED (str): The last modification of the offer.
        TAG (str): The provenance tag of the offer.
        ALL_TAGS (str): Every tag of the offer.
        TYPE (str): The catalogue type of the offer.
        KIND (str): The kind of the offer, telling its delivery.
        IS_CONSULTING (str): Whether the offer is a consulting offer.
        AUTHOR (str): The publisher of the offer.
    """

    ID = "id"
    NAME = "name"
    DESCRIPTION = "description"
    CATALOG_URL = "catalogUrl"
    LAST_MODIFIED = "lastModified"
    TAG = "tag"
    ALL_TAGS = "allTags"
    TYPE = "type"
    KIND = "kind"
    IS_CONSULTING = "isConsulting"
    AUTHOR = "author"


@unique
class IbmCatalogueTag(StrEnum):
    """Enums representing the tags of the IBM Cloud catalogue offers.

    Attributes:
        CREATED (str): An offer created by IBM.
        THIRD_PARTY (str): An offer of a third party.
        COMMUNITY (str): An offer of the community.
        DEPRECATED (str): A deprecated offer.
        BETA (str): A beta offer.
        PROFESSIONAL_SERVICE (str): A professional service.
    """

    CREATED = "ibm_created"
    THIRD_PARTY = "ibm_third_party"
    COMMUNITY = "ibm_community"
    DEPRECATED = "ibm_deprecated"
    BETA = "ibm_beta"
    PROFESSIONAL_SERVICE = "professional_service"


@unique
class IbmOfferType(StrEnum):
    """Enums representing the catalogue types of the IBM Cloud services.

    Attributes:
        SERVICE (str): A service.
        IAAS (str): An infrastructure offer.
    """

    SERVICE = "service"
    IAAS = "iaas"


@unique
class IbmOfferKind(StrEnum):
    """Enums representing the kinds of the IBM Cloud catalogue offers.

    Attributes:
        CONTENT (str): A content offer, a professional service when tagged so.
        SERVICE (str): A software as a service.
        TERRAFORM (str): A Terraform deployable architecture.
        VSI_IMAGE (str): A virtual server image.
        OVA (str): An open virtual appliance.
        HELM (str): A Helm chart.
        OPERATOR (str): A Kubernetes operator.
    """

    CONTENT = "content"
    SERVICE = "service"
    TERRAFORM = "terraform"
    VSI_IMAGE = "vsi_image"
    OVA = "ova"
    HELM = "helm"
    OPERATOR = "operator"


@unique
class IbmGlobalCatalogField(StrEnum):
    """Enums representing the fields of the IBM Global Catalog API responses, which date the launches.

    Attributes:
        RESOURCES (str): The resources of a search.
        ID (str): The resource identifier, the catalogue offer identifier.
        CREATED (str): The creation of the resource.
        OVERVIEW_UI (str): The display texts of the resource, by language.
        ENGLISH (str): The English display texts of the resource.
        DISPLAY_NAME (str): The display name of the resource.
    """

    RESOURCES = "resources"
    ID = "id"
    CREATED = "created"
    OVERVIEW_UI = "overview_ui"
    ENGLISH = "en"
    DISPLAY_NAME = "display_name"


@unique
class IbmGlobalCatalogParameter(StrEnum):
    """Enums representing the query parameters of the IBM Global Catalog API search.

    Attributes:
        QUERY (str): The free text searched.
        LIMIT (str): How many resources are returned.
    """

    QUERY = "q"
    LIMIT = "_limit"


@unique
class IbmPriceField(StrEnum):
    """Enums representing the fields of the IBM Global Catalog read for the prices.

    Attributes:
        RESOURCES (str): The resources of a listing.
        COUNT (str): The resources of the whole listing.
        ID (str): The identifier of a resource.
        NAME (str): Its name.
        GROUP (str): Whether a service is a group of services.
        CHILDREN (str): The services of a group.
        ACTIVE (str): Whether a service is active.
        METADATA (str): The metadata of a resource.
        PRICING (str): How a plan is priced.
        TYPE (str): Its pricing type (`free`, `lite`, `paid`, `paygo`...).
        METRICS (str): The priced metrics of a pricing.
        METRIC_ID (str): The identifier of a metric.
        CHARGE_UNIT_NAME (str): The charge unit code, e.g. `INSTANCE_HOURS`.
        CHARGE_UNIT (str): The charge unit, e.g. `Instance-Hour`.
        CHARGE_UNIT_QUANTITY (str): The charge units a price is per.
        TIER_MODEL (str): How the tiers apply, e.g. `Linear Tier`.
        RESOURCE_DISPLAY_NAME (str): The name of the priced resource.
        AMOUNTS (str): The prices, by country.
        COUNTRY (str): The country of a price list.
        CURRENCY (str): Its currency.
        PRICES (str): Its prices, one per tier.
        QUANTITY_TIER (str): The upper bound of a tier.
        PRICE (str): The price.
        EFFECTIVE_FROM (str): Since when the pricing applies.
        DEPLOYMENT_LOCATION (str): The region of a deployment pricing.
    """

    RESOURCES = "resources"
    COUNT = "count"
    ID = "id"
    NAME = "name"
    GROUP = "group"
    CHILDREN = "children"
    ACTIVE = "active"
    METADATA = "metadata"
    PRICING = "pricing"
    TYPE = "type"
    METRICS = "metrics"
    METRIC_ID = "metric_id"
    CHARGE_UNIT_NAME = "charge_unit_name"
    CHARGE_UNIT = "charge_unit"
    CHARGE_UNIT_QUANTITY = "charge_unit_quantity"
    TIER_MODEL = "tier_model"
    RESOURCE_DISPLAY_NAME = "resource_display_name"
    AMOUNTS = "amounts"
    COUNTRY = "country"
    CURRENCY = "currency"
    PRICES = "prices"
    QUANTITY_TIER = "quantity_tier"
    PRICE = "price"
    EFFECTIVE_FROM = "effective_from"
    DEPLOYMENT_LOCATION = "deployment_location"


@unique
class IbmPriceStage(StrEnum):
    """Enums representing the Global Catalog requests of the price crawl.

    Attributes:
        SERVICES (str): A page of the services.
        PLANS (str): The plans of a service.
        PRICING (str): The pricing of a plan or of a deployment.
        DEPLOYMENTS (str): The deployments (regions) of a plan priced by region.
    """

    SERVICES = "services"
    PLANS = "plans"
    PRICING = "pricing"
    DEPLOYMENTS = "deployments"


@unique
class IbmPricingType(StrEnum):
    """Enums representing the pricing types of an IBM plan priced without a pricing document (case-folded).

    Attributes:
        FREE (str): A free plan.
        LITE (str): A free plan with limits.
    """

    FREE = "free"
    LITE = "lite"
