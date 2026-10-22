from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class EdgarField(StrEnum):
    """Enums representing the fields of an SEC EDGAR XBRL `companyfacts` document.

    Attributes:
        FACTS (str): The facts, by taxonomy.
        US_GAAP (str): The US-GAAP taxonomy.
        UNITS (str): The facts of a concept, by unit.
        USD (str): The unit of the dollar amounts.
        START (str): The first day of the period of a fact.
        END (str): The last day of the period of a fact.
        VALUE (str): The value of a fact.
        FORM (str): The filing form of a fact, e.g. `10-Q`.
    """

    FACTS = "facts"
    US_GAAP = "us-gaap"
    UNITS = "units"
    USD = "USD"
    START = "start"
    END = "end"
    VALUE = "val"
    FORM = "form"
