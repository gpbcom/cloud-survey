from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class WikidataField(StrEnum):
    """Enums representing the fields of a Wikidata entity document (`Special:EntityData/<item>.json`).

    Attributes:
        ENTITIES (str): The entities of the document, by item.
        CLAIMS (str): The statements of an entity, by property.
        MAIN_SNAK (str): The main value of a statement.
        QUALIFIERS (str): The qualifiers of a statement, by property.
        DATA_VALUE (str): The value of a snak.
        VALUE (str): The content of a value.
        TIME (str): The time of a time value, e.g. `+2006-03-01T00:00:00Z`.
        AMOUNT (str): The amount of a quantity value, e.g. `+3074`.
    """

    ENTITIES = "entities"
    CLAIMS = "claims"
    MAIN_SNAK = "mainsnak"
    QUALIFIERS = "qualifiers"
    DATA_VALUE = "datavalue"
    VALUE = "value"
    TIME = "time"
    AMOUNT = "amount"


@unique
class WikidataProperty(StrEnum):
    """Enums representing the Wikidata properties read by the crawler.

    Attributes:
        INCEPTION (str): The founding date of an organization.
        EMPLOYEES (str): The number of employees.
        POINT_IN_TIME (str): When a statement holds (the date of an employee count).
    """

    INCEPTION = "P571"
    EMPLOYEES = "P1128"
    POINT_IN_TIME = "P585"
