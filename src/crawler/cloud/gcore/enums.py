from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GcoreMenuTab(StrEnum):
    """Enums representing the Gcore products menu tabs listing use cases, not products (case-folded labels).

    Attributes:
        BY_INDUSTRY (str): The use cases by industry tab.
        BY_NEED (str): The use cases by need tab.
    """

    BY_INDUSTRY = "by industry"
    BY_NEED = "by need"


@unique
class GcorePriceField(StrEnum):
    """Enums representing the fields of the Gcore cloud pricing API, read for the prices.

    Attributes:
        BODY (str): The price tables of the response.
        LOCATION (str): The location of a price, e.g. `Frankfurt-2`.
        TABLE_TYPE (str): The table of a price, e.g. `standard_g3a`, `bm2`, `lb1`, `egress`.
        NAME (str): The name of the priced flavor (padded with spaces).
        PRICE_PER_HOUR (str): The hourly price, as text.
        PRICE_PER_MONTH (str): The monthly price, as text with thousands separators.
        PRICE_PER_TRAFFIC (str): The price of a GB of traffic.
        VCPUS (str): The vCPUs, e.g. `4vCPU`.
        RAM (str): The memory, e.g. `16GB RAM`.
        GPU (str): The GPUs, e.g. `1 GPU`.
        CPU (str): The processors of a bare metal server.
        DISKS (str): Its disks.
        NETWORK (str): Its network cards.
    """

    BODY = "body"
    LOCATION = "location"
    TABLE_TYPE = "tableType"
    NAME = "name"
    PRICE_PER_HOUR = "pricePerHour"
    PRICE_PER_MONTH = "pricePerMonth"
    PRICE_PER_TRAFFIC = "pricePerTraffic"
    VCPUS = "vcpus"
    RAM = "ram"
    GPU = "gpu"
    CPU = "cpu"
    DISKS = "disks"
    NETWORK = "network"


@unique
class GcoreMachineKind(StrEnum):
    """Enums representing the kinds of machine of the Gcore cloud pricing API (its `vmType`).

    Attributes:
        VIRTUAL (str): The virtual machines (and their load balancers).
        BARE_METAL (str): The bare metal servers (and their load balancers and traffic).
    """

    VIRTUAL = "vm"
    BARE_METAL = "bm"
