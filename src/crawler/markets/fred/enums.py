from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class FredField(StrEnum):
    """Enums representing the query parameters and the columns of FRED's CSV export (`fredgraph.csv`).

    Attributes:
        ID (str): The series asked for.
        START (str): The first day asked for, `YYYY-MM-DD`.
        DATE (str): The header of the day column.
        SERIES (str): The meta key holding the series of a request.
    """

    ID = "id"
    START = "cosd"
    DATE = "observation_date"
    SERIES = "fred_series"
