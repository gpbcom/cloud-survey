from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from analytics.markets.counterparts.counterpart_series import CounterpartSeries
from models.history.chronology import Chronology
from models.markets.enums import CorrelationCounterpart, Granularity, ShareSource
from models.markets.markets_catalog import MarketsCatalog

S, Q, M = ShareSource.STATCOUNTER, Granularity.QUARTER, Granularity.MONTH


def test_the_choices_are_the_stock_the_nearby_shares_the_currency_and_the_contexts(
    markets_catalog: MarketsCatalog, markets_chronology: Chronology
) -> None:
    storage = MagicMock()
    storage.shares.series_of = AsyncMock(
        return_value=[
            ("device-vendors", "FR", S, M),
            ("device-vendors", "KR", S, M),
            ("device-vendors", "US", S, M),
            ("device-vendors", "ww", S, M),
            ("smartphones", "ww", ShareSource.IDC, Q),
            ("smartphones", "ww", ShareSource.IDC, Granularity.YEAR),
            ("smartphone-os-sales", "ww", ShareSource.MANUAL, Granularity.YEAR),
        ]
    )

    choices = asyncio.run(
        CounterpartSeries(markets_catalog, markets_chronology).options(
            "samsung", "smartphones", "ww", ShareSource.IDC, storage
        )
    )

    assert [(choice.kind, choice.area) for choice in choices[:4]] == [
        (CorrelationCounterpart.STOCK, None),
        (CorrelationCounterpart.SHARE, "KR"),
        (CorrelationCounterpart.SHARE, "ww"),
        (CorrelationCounterpart.CURRENCY, None),
    ], "the home country and worldwide only, never the series correlated nor yearly totals"
    assert choices[0].listing == "KRX:005930"
    assert choices[3].currency == "KRW"
    assert [choice.segment for choice in choices[4:]] == ["foundry", "dram", "nand"]
