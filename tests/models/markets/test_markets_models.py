from __future__ import annotations

from datetime import date
from typing import Dict, List

import pytest
from pydantic import JsonValue, ValidationError

from models.markets.catalog.market_area import MarketArea
from models.markets.catalog.share_segment import ShareSegment
from models.markets.charts.chart_line import ChartLine
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import AreaKind, Device, ShareSource, StatCounterStat
from models.markets.exception import DuplicateMarketKeyError, InvalidMarketValueError, UnknownMarketReferenceError
from models.markets.facts.price_point import PricePoint
from models.markets.facts.share_observation import ShareObservation
from models.markets.listings.stock_listing import StockListing
from models.markets.listings.valuation_point import ValuationPoint
from models.markets.markets_catalog import MarketsCatalog
from models.markets.series.share_series import ShareSeries


def catalog(**changes: JsonValue) -> Dict[str, JsonValue]:
    raw: Dict[str, JsonValue] = {
        "areas": [
            {"key": "ww", "label": "Worldwide", "kind": "world"},
            {"key": "DE", "label": "Germany", "kind": "country"},
            {"key": "FR", "label": "France", "kind": "country"},
            {"key": "eu27", "label": "EU-27", "kind": "union", "members": ["de", "FR"]},
        ],
        "currencies": [{"currency": "eur", "series": "dexuseu", "quote": "usd-per-unit"}],
        "listings": [
            {"company": "sap", "symbol": " etr:sap ", "currency": "EUR"},
            {"company": "sap", "symbol": "NYSE:SAP", "currency": "USD", "primary": False},
        ],
        "labels": [{"label": " Chrome ", "company": "google"}],
        "segments": [
            {"key": "browsers", "label": "Browsers", "source": "statcounter", "stat": "browser", "metric": "usage"}
        ],
    }
    raw.update(changes)
    return raw


class TestMarketsCatalog:
    def test_the_shipped_catalogue_is_valid(self, markets_catalog: MarketsCatalog) -> None:
        assert {segment.key for segment in markets_catalog.segments} >= {"search", "browsers", "operating-systems"}
        assert markets_catalog.area("eu27") is not None
        assert len(markets_catalog.area("eu27").members) == 27  # type: ignore[union-attr]
        assert markets_catalog.company_of(ShareSource.STATCOUNTER, "bing") == "microsoft"
        assert markets_catalog.company_of(ShareSource.SYNERGY, "amazon") == "amazon"
        assert [listing.symbol for listing in markets_catalog.listings_of("tsmc")] == ["TPE:2330", "NYSE:TSM"]

    def test_entries_are_normalised(self) -> None:
        parsed = MarketsCatalog.model_validate(catalog())

        assert parsed.area("eu27").members == ["DE", "FR"]  # type: ignore[union-attr]
        assert parsed.listings[0].symbol == "ETR:SAP"
        assert parsed.currencies[0].currency == "EUR"
        assert parsed.currencies[0].series == "DEXUSEU"
        assert parsed.labels[0].label == "Chrome"
        assert parsed.statcounter_segments([StatCounterStat.BROWSER])[0].key == "browsers"
        assert parsed.region_of("DE") is None

    @pytest.mark.parametrize(
        ("changes", "error"),
        [
            ({"listings": [{"company": "sap", "symbol": "ETR:SAP", "currency": "EUR"}] * 2}, DuplicateMarketKeyError),
            (
                {"areas": [{"key": "eu27", "label": "EU", "kind": "union", "members": ["IT"]}]},
                UnknownMarketReferenceError,
            ),
            ({"listings": [{"company": "tsmc", "symbol": "TPE:2330", "currency": "TWD"}]}, UnknownMarketReferenceError),
            ({"listings": [{"company": "sap", "symbol": "SAP", "currency": "EUR"}]}, InvalidMarketValueError),
            ({"statcounter_from": "2009"}, InvalidMarketValueError),
        ],
    )
    def test_invalid_catalogues_are_refused(self, changes: Dict[str, JsonValue], error: type[Exception]) -> None:
        with pytest.raises(ValidationError) as caught:
            MarketsCatalog.model_validate(catalog(**changes))

        assert any(isinstance(item.get("ctx", {}).get("error"), error) for item in caught.value.errors())


class TestCatalogEntries:
    def test_a_listing_knows_its_google_codes(self) -> None:
        listing = StockListing(company="sap", symbol="FWB:SAP", currency="EUR")

        assert (listing.exchange(), listing.ticker()) == ("FWB", "SAP")
        assert listing.google_candidates() == [("SAP", "ETR"), ("SAP", "FRA")]
        assert StockListing(company="ibm", symbol="NYSE:IBM", currency="usd").google_candidates() == [("IBM", "NYSE")]

    @pytest.mark.parametrize("value", ["1998", "1998-01", "1998-01-26", 1998])
    def test_valuation_dates_are_partial(self, value: JsonValue) -> None:
        point = ValuationPoint(
            company="dec", date=value, kind="deal", value_bn=9.6, label="To Compaq", source="8-K", tag="P"
        )

        assert point.date.startswith("1998")

    def test_a_malformed_valuation_date_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ValuationPoint(company="dec", date="Jan 1998", kind="deal", value_bn=9.6, label="x", source="y", tag="P")

    def test_a_segment_lists_each_device_once(self) -> None:
        segment = ShareSegment(
            key="search", label="Search", source="statcounter", metric="usage", devices=["mobile", "all", "mobile"]
        )

        assert segment.devices == [Device.MOBILE, Device.ALL]

    @pytest.mark.parametrize("members", [["DEU"], [""], [3]])
    def test_union_members_are_country_codes(self, members: List[JsonValue]) -> None:
        with pytest.raises(ValidationError):
            MarketArea(key="eu27", label="EU", kind=AreaKind.UNION, members=members)


class TestFactsAndSeries:
    def test_a_statcounter_month_is_its_first_day(self) -> None:
        share = ShareObservation(
            stat="search_engine", area="US", device="all", month="2026-09", label="Google", value=85.2, source_url="u"
        )

        assert share.month == date(2026, 9, 1)

    def test_a_price_volume_is_whole(self) -> None:
        point = PricePoint(
            listing="NYSE:IBM", day="1986-10-24", close=28.98, volume=7700300.0, currency="usd", source_url="u"
        )

        assert point.volume == 7700300
        assert point.currency == "USD"

    def test_series_points_are_sorted(self) -> None:
        series = ShareSeries(label="Google", points=[(date(2020, 2, 1), 2.0), (date(2020, 1, 1), 1.0)])

        assert [day for day, _ in series.points] == [date(2020, 1, 1), date(2020, 2, 1)]

    def test_a_chart_line_colour_is_rgb(self) -> None:
        assert ChartLine(key="g", label="G", color="#34A853").color == "#34a853"
        with pytest.raises(ValidationError):
            ChartLine(key="g", label="G", color="green")

    def test_a_crawl_scope_reads_comma_separated_keys(self) -> None:
        scope = CrawlScope(areas=" ww, US,,US ", listings="", since=" ")

        assert scope.areas == ["ww", "US"]
        assert scope.listings == []
        assert scope.since is None
        with pytest.raises(ValidationError):
            CrawlScope(since="2026")
