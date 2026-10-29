from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class SelectelMenu(StrEnum):
    """Enums representing the titles of the top entries of the Selectel header menu listing offers.

    Attributes:
        PRODUCTS (str): The products entry (`Продукты`).
        SERVICES (str): The services entry (`Услуги`).
    """

    PRODUCTS = "Продукты"
    SERVICES = "Услуги"


@unique
class SelectelMenuGroup(StrEnum):
    """Enums representing the titles of the Selectel header menu groups which are not catalogue categories.

    Attributes:
        POPULAR (str): The popular products (`Популярные`), a selection of the other groups.
        BUSINESS_TASKS (str): The business tasks (`Бизнес-задачи`), use-case pages.
        INDUSTRIES (str): The industries (`Отрасли`).
    """

    POPULAR = "Популярные"
    BUSINESS_TASKS = "Бизнес-задачи"
    INDUSTRIES = "Отрасли"


@unique
class SelectelPriceField(StrEnum):
    """Enums representing the fields of the Selectel price APIs, read for the prices.

    Attributes:
        RESOURCE (str): The priced resource of a cloud price, e.g. `compute_vds_1_1_10`.
        GROUP (str): Its region or pool, e.g. `ru-1`.
        VALUE (str): Its price, in kopecks per hour per unit.
        UNIT (str): Its unit, e.g. `item`, `GB`, `MB*H`.
        RESULT (str): The dedicated servers of the server API.
        UUID (str): The identifier of a server.
        NAME (str): The name of a server, e.g. `AEL10-SSD`.
        CONFIG_NAME (str): Its configuration written out.
        TARIFF_LINE (str): Its line, e.g. `Entry Line`.
        CPU (str): Its processors.
        COUNT (str): A count of processors, memory modules or disks.
        CORES_PER_CPU (str): The cores of a processor.
        RAM (str): Its memory modules.
        SIZE (str): The size of a memory module or a disk, in GB.
        DISK (str): Its disks.
        LOCATION_PRICE_COLLECTION (str): Its prices, by location then currency.
        RUB (str): The prices in rubles of a server.
        MONTH (str): The monthly price.
        DAY (str): The daily price.
        ID (str): The identifier of a billing item.
        NAME_EN (str): The English name of a billing item.
        GROUP_ID (str): Its group.
        PRICES (str): Its prices, by currency, in kopecks.
        RUB_PRICE (str): Its price in rubles, in kopecks.
        REPEAT (str): Whether it is charged every month (1) or once (0).
    """

    RESOURCE = "resource"
    GROUP = "group"
    VALUE = "value"
    UNIT = "unit"
    RESULT = "result"
    UUID = "uuid"
    NAME = "name"
    CONFIG_NAME = "config_name"
    TARIFF_LINE = "tariff_line"
    CPU = "cpu"
    COUNT = "count"
    CORES_PER_CPU = "cores_per_cpu"
    RAM = "ram"
    SIZE = "size"
    DISK = "disk"
    LOCATION_PRICE_COLLECTION = "location_price_collection"
    RUB = "RUB"
    MONTH = "month"
    DAY = "day"
    ID = "id"
    NAME_EN = "name_en"
    GROUP_ID = "group_id"
    PRICES = "prices"
    RUB_PRICE = "rub"
    REPEAT = "repeat"


@unique
class SelectelPriceFamily(StrEnum):
    """Enums representing the families of the Selectel cloud price API (`/prices/<family>`).

    Attributes:
        VPC (str): The cloud servers.
        DBAAS (str): The managed databases.
        MKS (str): The managed Kubernetes.
        NETDISK (str): The network disks.
        ONES (str): The 1C cloud.
        STORAGE (str): The object storage.
        VMWARE (str): The VMware cloud.
        CRAAS (str): The container registry.
    """

    VPC = "vpc"
    DBAAS = "dbaas"
    MKS = "mks"
    NETDISK = "netdisk"
    ONES = "ones"
    STORAGE = "storage"
    VMWARE = "vmware"
    CRAAS = "craas"


@unique
class SelectelPriceUnit(StrEnum):
    """Enums representing the units of the Selectel cloud prices (per hour, unless transferred).

    Attributes:
        ITEM (str): An item for an hour.
        GB (str): A GB for an hour, or transferred.
        MB (str): A MB for an hour, or transferred.
        GB_HOUR (str): A GB for an hour.
        MB_HOUR (str): A MB for an hour.
    """

    ITEM = "item"
    GB = "GB"
    MB = "MB"
    GB_HOUR = "GB*H"
    MB_HOUR = "MB*H"
