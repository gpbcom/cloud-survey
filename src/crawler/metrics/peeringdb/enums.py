from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class PeeringdbField(StrEnum):
    """Enums representing the fields of a PeeringDB networks document (`/api/net`, `depth=2`).

    Attributes:
        DATA (str): The networks.
        ASN (str): The autonomous system of a network.
        EXCHANGE_LINKS (str): The links of a network to the internet exchanges.
        EXCHANGE (str): The exchange of a link.
        FACILITY_LINKS (str): The links of a network to the facilities.
        FACILITY (str): The facility of a link.
    """

    DATA = "data"
    ASN = "asn"
    EXCHANGE_LINKS = "netixlan_set"
    EXCHANGE = "ix_id"
    FACILITY_LINKS = "netfac_set"
    FACILITY = "fac_id"
