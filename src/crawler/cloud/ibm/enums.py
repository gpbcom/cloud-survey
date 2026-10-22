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
