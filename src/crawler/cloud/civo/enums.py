from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CivoFooterColumn(StrEnum):
    """Enums representing the footer columns of the Civo website listing products, also naming the hub pages.

    Attributes:
        PUBLIC_CLOUD (str): The public cloud column.
        PRIVATE_CLOUD (str): The private cloud column.
        CIVO_AI (str): The Civo AI column.
    """

    PUBLIC_CLOUD = "Public Cloud"
    PRIVATE_CLOUD = "Private Cloud"
    CIVO_AI = "Civo AI"


@unique
class CivoPricingAnchor(StrEnum):
    """Enums representing the anchors of the Civo pricing navigation entries.

    Attributes:
        KUBERNETES (str): The Kubernetes clusters.
        COMPUTE_INSTANCES (str): The compute instances.
        DATABASES (str): The managed databases.
        LOAD_BALANCERS (str): The load balancers.
        VOLUMES (str): The block storage volumes.
        NVIDIA_GPUS (str): The NVIDIA GPU instances.
        DATA_TRANSFER (str): The data transfer, not a product.
    """

    KUBERNETES = "#kubernetes"
    COMPUTE_INSTANCES = "#compute-instances"
    DATABASES = "#databases"
    LOAD_BALANCERS = "#load-balancers"
    VOLUMES = "#volumes"
    NVIDIA_GPUS = "#nvidia-gpus"
    DATA_TRANSFER = "#data-transfer"


@unique
class CivoJsonLdField(StrEnum):
    """Enums representing the keys of the JSON-LD objects of the Civo hub pages.

    Attributes:
        HAS_OFFER_CATALOG (str): The offer catalogue of a service.
        ITEM_LIST_ELEMENT (str): The entries of an offer catalogue.
        NAME (str): The name of a node or an offer.
        DESCRIPTION (str): The description of an offer.
        URL (str): The link of an offer.
    """

    HAS_OFFER_CATALOG = "hasOfferCatalog"
    ITEM_LIST_ELEMENT = "itemListElement"
    NAME = "name"
    DESCRIPTION = "description"
    URL = "url"


@unique
class CivoPriceOption(StrEnum):
    """Enums representing the price options of a cell of the Civo pricing page (`data-option`).

    Attributes:
        HOURLY (str): The hourly price.
        MONTHLY (str): The monthly price.
    """

    HOURLY = "hourly"
    MONTHLY = "monthly"


@unique
class CivoPriceColumn(StrEnum):
    """Enums representing the hardware columns of the Civo pricing tables.

    Attributes:
        RAM (str): The memory.
        CPU (str): The cores.
        VCPU (str): The vCPUs.
        STORAGE (str): The storage.
    """

    RAM = "RAM"
    CPU = "CPU"
    VCPU = "vCPU"
    STORAGE = "Storage"
