from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CompanyFactsField(StrEnum):
    """Enums representing the fields of an SEC EDGAR XBRL `companyfacts` document.

    Attributes:
        FACTS (str): The facts, by taxonomy then concept.
        UNITS (str): The facts of a concept, by unit (`USD`, `TWD`, `USD/shares`, `shares`).
        START (str): The first day of the period of a fact (absent for a balance).
        END (str): The last day of the period of a fact, or the date of a balance.
        VALUE (str): The value of a fact.
        FORM (str): The filing form of a fact, e.g. `10-Q`.
        FISCAL_YEAR (str): The fiscal year the filing states.
        FISCAL_PERIOD (str): The fiscal period the filing states, e.g. `Q2`, `FY`.
        FILED (str): The day the filing was made.
        ENTITY (str): The name of the filer.
    """

    FACTS = "facts"
    UNITS = "units"
    START = "start"
    END = "end"
    VALUE = "val"
    FORM = "form"
    FISCAL_YEAR = "fy"
    FISCAL_PERIOD = "fp"
    FILED = "filed"
    ENTITY = "entityName"


@unique
class XbrlUnit(StrEnum):
    """Enums representing the units of the XBRL facts that are not a currency.

    Attributes:
        SHARES (str): A number of shares.
        PER_SHARE (str): The suffix of a per-share amount, e.g. `USD/shares`.
    """

    SHARES = "shares"
    PER_SHARE = "/shares"
