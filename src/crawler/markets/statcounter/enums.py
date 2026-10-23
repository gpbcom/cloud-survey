from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class StatCounterParameter(StrEnum):
    """Enums representing the query parameters of StatCounter's CSV export (`chart.php`).

    Attributes:
        DEVICE (str): The devices measured.
        STAT (str): The statistic, e.g. `search_engine`.
        REGION (str): The region: `ww`, a continent or a country code.
        GRANULARITY (str): The period of the rows.
        FROM (str): The first month, `YYYYMM`.
        TO (str): The last month, `YYYYMM`.
        CSV (str): Asks for the CSV export rather than the chart.
    """

    DEVICE = "device_hidden"
    STAT = "statType_hidden"
    REGION = "region_hidden"
    GRANULARITY = "granularity"
    FROM = "fromInt"
    TO = "toInt"
    CSV = "csv"


@unique
class StatCounterDevice(StrEnum):
    """Enums representing the device values of StatCounter's CSV export.

    Attributes:
        ALL (str): Every device.
        DESKTOP (str): Desktop and laptop computers.
        MOBILE (str): Phones.
        TABLET (str): Tablets.
    """

    ALL = "desktop+mobile+tablet+console"
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"


@unique
class StatCounterMeta(StrEnum):
    """Enums representing the meta keys of a StatCounter request, read back with the CSV.

    Attributes:
        STAT (str): The statistic asked for.
        AREA (str): The region asked for.
        DEVICE (str): The devices asked for (a `Device` value).
        FROM (str): The first month asked for, `YYYY-MM`.
    """

    STAT = "statcounter_stat"
    AREA = "statcounter_area"
    DEVICE = "statcounter_device"
    FROM = "statcounter_from"
