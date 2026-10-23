from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

import pytest

from models.markets.enums import Granularity
from models.markets.press.period_label import PeriodLabel

Q, Y = Granularity.QUARTER, Granularity.YEAR


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2Q26 Market Share", (date(2026, 4, 1), Q)),
        ("3Q 2025 Shipments", (date(2025, 7, 1), Q)),
        ("Q4 2024 Share", (date(2024, 10, 1), Q)),
        ("Q1'26", (date(2026, 1, 1), Q)),
        ("in the third quarter of 2026", (date(2026, 7, 1), Q)),
        ("2022 Market Share (%)", (date(2022, 1, 1), Y)),
        ("1H26 revenue", None),
        ("Company", None),
    ],
)
def test_the_periods_analysts_write_are_read(text: str, expected: Optional[Tuple[date, Granularity]]) -> None:
    assert PeriodLabel().parse(text) == expected


@pytest.mark.parametrize(
    ("title", "published", "expected"),
    [
        ("Q2 NAND Flash Revenue Up 7.4%", date(2023, 8, 20), (date(2023, 4, 1), Q)),
        ("Q4 NAND Flash Revenue", date(2024, 2, 1), (date(2023, 10, 1), Q)),
        (
            "Top 10 Foundries Q4 Revenue Up 7.9%, Annual Total Hits US$111.54 Billion in 2023",
            date(2024, 3, 12),
            (date(2023, 10, 1), Q),
        ),
        ("NAND Flash Supplier Revenue Grows 12.2% in Third Quarter", date(2014, 11, 20), (date(2014, 7, 1), Q)),
        ("Top 10 Ranking of Global Semiconductor Foundries of 2017", date(2017, 11, 29), (date(2017, 1, 1), Y)),
        ("Revenue Rises", date(2026, 1, 1), None),
    ],
)
def test_a_bare_quarter_takes_its_year_from_the_title_or_the_publication(
    title: str, published: date, expected: Optional[Tuple[date, Granularity]]
) -> None:
    assert PeriodLabel().release(title, published) == expected
