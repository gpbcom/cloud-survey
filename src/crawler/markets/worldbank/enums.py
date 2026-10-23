from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class WorldBankField(StrEnum):
    """Enums representing the fields of a World Bank indicator document (API v2, JSON).

    Attributes:
        COUNTRY (str): The country of an observation.
        ID (str): The ISO alpha-2 code of the country.
        DATE (str): The year of an observation.
        VALUE (str): The value of an observation, `null` when missing.
        INDICATOR (str): The meta key holding the indicator of a request.
    """

    COUNTRY = "country"
    ID = "id"
    DATE = "date"
    VALUE = "value"
    INDICATOR = "worldbank_indicator"
