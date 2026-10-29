from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class InstitutionField(StrEnum):
    """Enums representing the fields of an OpenAlex institutions answer.

    Attributes:
        RESULTS (str): The institutions found.
        ID (str): The identifier of an institution, a URL ending with `I` and digits.
        DISPLAY_NAME (str): Its name.
        ALTERNATIVES (str): Its other names.
        ACRONYMS (str): Its acronyms.
        LINEAGE (str): The institutions it belongs to, itself included.
        COUNTRY (str): The country of its headquarters.
        WORKS (str): The works signed by its members.
    """

    RESULTS = "results"
    ID = "id"
    DISPLAY_NAME = "display_name"
    ALTERNATIVES = "display_name_alternatives"
    ACRONYMS = "display_name_acronyms"
    LINEAGE = "lineage"
    COUNTRY = "country_code"
    WORKS = "works_count"
