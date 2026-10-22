from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.trends.enums import ChartNote


class MetricMatrix(BaseModel):
    """The cells of a matrix chart: a value per row and column.

    Attributes:
        rows (List[str]): The row keys (grouping enum values), the largest first.
        columns (List[str]): The column keys (grouping enum values), the largest first.
        cells (Dict[str, Dict[str, float]]): The value of each row (outer key) and column (inner key), a missing cell
            being zero.
        total_rows (int): The number of rows before the largest ones were kept.
        total_columns (int): The number of columns before the largest ones were kept.
        notes (List[ChartNote]): The caveats of the figures, for the footnote.
    """

    rows: List[str] = Field(default_factory=list, description="The row keys, the largest first.")
    columns: List[str] = Field(default_factory=list, description="The column keys, the largest first.")
    cells: Dict[str, Dict[str, float]] = Field(default_factory=dict, description="The value of each row and column.")
    total_rows: int = Field(default=0, ge=0, description="The number of rows before the largest were kept.")
    total_columns: int = Field(default=0, ge=0, description="The number of columns before the largest were kept.")
    notes: List[ChartNote] = Field(default_factory=list, description="The caveats of the figures.")
