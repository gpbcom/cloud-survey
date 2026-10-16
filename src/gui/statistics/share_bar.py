from __future__ import annotations

# Standard Library Imports.
from dataclasses import dataclass
from typing import Optional

# Third Party Imports.
from PyQt6.QtGui import QColor


@dataclass(frozen=True)
class ShareBar:
    """A bar of the market share chart.

    Attributes:
        label (str): The player label.
        share_pct (float): The market share, in percent.
        color (QColor): The bar colour.
        low_pct (Optional[float]): The low bound of a published band, if any.
        high_pct (Optional[float]): The high bound of a published band, if any.
        approximate (bool): Whether the share is an approximation.
        computed (bool): Whether the share is computed rather than published.
    """

    label: str
    share_pct: float
    color: QColor
    low_pct: Optional[float] = None
    high_pct: Optional[float] = None
    approximate: bool = False
    computed: bool = False
