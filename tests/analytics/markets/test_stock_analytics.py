from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List

import pytest

from analytics.markets.stocks.fx_converter import FxConverter
from analytics.markets.stocks.stock_metrics import StockMetrics
from analytics.markets.stocks.stock_table import StockTable
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.history.catalog.company import Company
from models.markets.enums import PriceScale
from models.markets.facts.fx_observation import FxObservation
from models.markets.facts.price_point import PricePoint
from models.markets.listings.hq_region import HqRegion
from models.markets.listings.stock_listing import StockListing
from models.markets.markets_catalog import MarketsCatalog
from models.markets.values.fx_rate import FxRate

DAY = date(2024, 3, 15)


def price(listing: str, day: date, close: float, currency: str = "USD") -> PricePoint:
    return PricePoint(listing=listing, day=day, close=close, currency=currency, source_url="u")


def converter() -> FxConverter:
    return FxConverter(
        [
            FxRate(currency="EUR", day=DAY, usd_per_unit=1.1),
            FxRate(currency="JPY", day=DAY, usd_per_unit=1 / 150),
            FxRate(currency="EUR", day=date(1999, 1, 4), usd_per_unit=1.18),
        ]
    )


class TestFxConverter:
    def test_the_series_are_turned_into_dollars_per_unit(self, markets_catalog: MarketsCatalog) -> None:
        observations = [
            FxObservation(series="DEXUSEU", day=DAY, value=1.1, source_url="u"),
            FxObservation(series="DEXJPUS", day=DAY, value=150.0, source_url="u"),
            FxObservation(series="UNKNOWN", day=DAY, value=1.0, source_url="u"),
        ]

        rates = FxConverter().to_rates(observations, markets_catalog)

        assert [(rate.currency, rate.usd_per_unit) for rate in rates] == [("EUR", 1.1), ("JPY", pytest.approx(1 / 150))]

    def test_amounts_convert_through_the_dollar_with_the_latest_rate(self) -> None:
        fx = converter()

        assert fx.convert(150.0, "JPY", "EUR", DAY + timedelta(days=3)) == pytest.approx(1 / 1.1)
        assert fx.convert(10.0, "USD", "USD", DAY) == 10.0
        assert fx.usd_per_unit("USD", date(1950, 1, 1)) == 1.0

    def test_no_rate_before_the_first_or_long_after_the_last(self) -> None:
        fx = converter()

        assert fx.convert(1.0, "EUR", "USD", date(1998, 12, 31)) is None
        assert fx.convert(1.0, "JPY", "USD", DAY + timedelta(days=60)) is None
        assert fx.first_day("EUR") == date(1999, 1, 4)


class TestStockTable:
    def test_month_ends_keep_the_last_close_of_each_month(self) -> None:
        ends = StockTable(converter()).month_ends(
            [(date(2024, 1, 5), 1.0), (date(2024, 1, 26), 2.0), (date(2024, 2, 2), 3.0)]
        )

        assert ends == {date(2024, 1, 1): 2.0, date(2024, 2, 1): 3.0}

    def test_listing_lines_convert_and_rebase(self) -> None:
        listings = [StockListing(company="sap", symbol="ETR:SAP", currency="EUR")]
        points = [
            price("ETR:SAP", date(1998, 6, 1), 50.0, "EUR"),
            price("ETR:SAP", DAY, 100.0, "EUR"),
            price("ETR:SAP", DAY + timedelta(days=7), 110.0, "EUR"),
        ]
        table = StockTable(converter())

        usd = table.listing_lines(points, listings, {"sap": "SAP"}, "USD")
        indexed = table.listing_lines(points, listings, {"sap": "SAP"}, "listing", PriceScale.INDEXED)

        assert usd[0].points == [(DAY, pytest.approx(110.0)), (DAY + timedelta(days=7), pytest.approx(121.0))]
        assert usd[0].label == "SAP (ETR:SAP)"
        assert "from 1999-01-04" in (usd[0].note or "")
        assert indexed[0].currency == "index"
        assert [value for _, value in indexed[0].points] == pytest.approx([100.0, 200.0, 220.0])

    def test_region_indexes_are_equal_weight_and_chain_linked(self) -> None:
        listings = [
            StockListing(company="a", symbol="NYSE:A", currency="USD"),
            StockListing(company="b", symbol="NYSE:B", currency="USD"),
        ]
        points = [
            price("NYSE:A", date(2024, 1, 31), 10.0),
            price("NYSE:A", date(2024, 2, 29), 20.0),
            price("NYSE:B", date(2024, 1, 31), 50.0),
            price("NYSE:B", date(2024, 2, 29), 50.0),
            price("NYSE:B", date(2024, 3, 29), 100.0),
        ]
        regions = [
            HqRegion(key="us", label="United States", countries=["US"]),
            HqRegion(key="uk", label="UK", countries=["GB"]),
        ]

        lines = StockTable(converter()).region_indexes(points, listings, regions, {"a": "US", "b": "US"})

        assert len(lines) == 1
        assert lines[0].key == "region:us"
        assert [value for _, value in lines[0].points] == [100.0, pytest.approx(150.0), pytest.approx(300.0)]


class TestStockMetrics:
    def test_the_providers_get_their_quarterly_value_and_return(self, markets_catalog: MarketsCatalog) -> None:
        amazon = Company(key="amazon", label="Amazon", color="#ff9900", provider=CloudProvider.AWS, country="US")
        points: List[PricePoint] = [
            price("NASDAQ:AMZN", date(2024, 3, 28), 180.0),
            price("NASDAQ:AMZN", date(2024, 6, 28), 193.0),
            price("NASDAQ:AMZN", date(2024, 6, 21), 189.0),
        ]

        values = StockMetrics(converter()).measure(markets_catalog, [amazon], points)

        by_key = {(value.period, value.metric): value.value for value in values}
        assert by_key[("2024Q2", ProviderMetric.STOCK_VALUE)] == 193.0
        assert by_key[("2024Q2", ProviderMetric.STOCK_RETURN)] == pytest.approx(math.log(193.0 / 180.0))
        assert ("2024Q1", ProviderMetric.STOCK_RETURN) not in by_key
        assert {value.source for value in values} == {MetricSource.GOOGLE_FINANCE}
        assert {value.provider for value in values} == {CloudProvider.AWS}
