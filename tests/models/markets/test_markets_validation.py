from __future__ import annotations

import math
from datetime import date, datetime
from typing import Dict, List, Tuple, Type

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from models.markets.catalog.currency_series import CurrencySeries
from models.markets.catalog.google_finance_settings import GoogleFinanceSettings
from models.markets.catalog.market_area import MarketArea
from models.markets.catalog.series_label import SeriesLabel
from models.markets.catalog.share_segment import ShareSegment
from models.markets.charts.chart_dot import ChartDot
from models.markets.charts.chart_line import ChartLine
from models.markets.correlation.counterpart import Counterpart
from models.markets.crawl_scope import CrawlScope
from models.markets.exception import (
    InvalidMarketChoiceError,
    InvalidMarketDateError,
    InvalidMarketFlagError,
    InvalidMarketListError,
    InvalidMarketNumberError,
    InvalidMarketTextError,
    InvalidMarketValueError,
    MarketsModelError,
)
from models.markets.facts.fx_observation import FxObservation
from models.markets.facts.price_point import PricePoint
from models.markets.facts.release_share import ReleaseShare
from models.markets.facts.share_observation import ShareObservation
from models.markets.facts.weight_observation import WeightObservation
from models.markets.field_check import MarketFieldCheck
from models.markets.help.control_help import ControlHelp
from models.markets.help.markets_help import MarketsHelp
from models.markets.help.option_help import OptionHelp
from models.markets.listings.hq_region import HqRegion
from models.markets.listings.manual_share import ManualShare
from models.markets.listings.stock_listing import StockListing
from models.markets.listings.valuation_point import ValuationPoint
from models.markets.markets_catalog import MarketsCatalog
from models.markets.press.press_family import PressFamily
from models.markets.series.coverage_entry import CoverageEntry
from models.markets.series.lag_correlation import LagCorrelation
from models.markets.series.share_series import ShareSeries
from models.markets.series.share_stock_result import ShareStockResult
from models.markets.series.stock_series import StockSeries
from models.markets.values.fx_rate import FxRate
from models.markets.values.market_share_value import MarketShareValue

CHECK = MarketFieldCheck()

VALID: Dict[Type[BaseModel], Dict[str, JsonValue]] = {
    CurrencySeries: {"currency": "EUR", "series": "DEXUSEU", "quote": "usd-per-unit"},
    GoogleFinanceSettings: {"rpc_id": "c2u4wc", "period": 8, "consent_cookies": {"SOCS": "x"}},
    MarketArea: {"key": "eu27", "label": "EU-27", "kind": "country", "members": []},
    SeriesLabel: {"source": "statcounter", "label": "Chrome", "company": "google"},
    ShareSegment: {
        "key": "search",
        "label": "Search",
        "chronology": "search",
        "source": "statcounter",
        "stat": "search_engine",
        "metric": "usage",
        "devices": ["all"],
        "first_month": "2009-01",
        "description": "Search.",
    },
    ChartDot: {"day": "1998-01-26", "value": 9.6, "color": "#7e57c2", "label": "DEC", "tooltip": "8-K"},
    ChartLine: {
        "key": "google",
        "label": "Google",
        "color": "#34a853",
        "dashed": False,
        "dots": False,
        "points": [["2020-01-01", 1.0]],
        "note": "Chrome",
    },
    CrawlScope: {"areas": "ww,US", "listings": ["NYSE:IBM"], "since": "2026-07", "companies": "nvidia,tsmc"},
    FxObservation: {"series": "DEXUSEU", "day": "2026-10-16", "value": 1.12, "source_url": "u"},
    PricePoint: {
        "listing": "NYSE:IBM",
        "day": "1986-10-24",
        "close": 28.98,
        "volume": 7700300,
        "currency": "USD",
        "source_url": "u",
    },
    ReleaseShare: {
        "source": "idc",
        "segment": "pcs",
        "area": "ww",
        "period": "2026-04-01",
        "granularity": "quarter",
        "label": "Lenovo",
        "value": "24.4%",
        "title": "PC Market",
        "published": "2026-07-08",
        "source_url": "u",
    },
    ShareObservation: {
        "stat": "browser",
        "area": "US",
        "device": "all",
        "month": "2026-09",
        "label": "Chrome",
        "value": 50.0,
        "source_url": "u",
    },
    WeightObservation: {"indicator": "SP.POP.TOTL", "country": "de", "year": "2024", "value": 83.0, "source_url": "u"},
    HqRegion: {"key": "us", "label": "United States", "countries": ["us"]},
    StockListing: {"company": "ibm", "symbol": "NYSE:IBM", "currency": "USD", "primary": True, "note": "Big Blue"},
    ValuationPoint: {
        "company": "dec",
        "date": "1998",
        "kind": "deal",
        "value_bn": 9.6,
        "high_bn": 9.8,
        "label": "To Compaq",
        "source": "8-K",
        "tag": "P",
    },
    MarketsCatalog: {
        "statcounter_from": "2009-01",
        "google_finance": {},
        "segments": [],
        "areas": [],
        "labels": [],
        "currencies": [],
        "regions": [],
        "listings": [],
        "valuations": [],
        "press": [],
        "manual_shares": [],
        "press_names": ["Elpida"],
        "country_currencies": {"us": "usd"},
    },
    ManualShare: {
        "segment": "mainframes",
        "area": "US",
        "period": 1961,
        "label": "IBM",
        "company": "ibm",
        "value": 52,
        "source": "Cato 1985",
        "tag": "A",
    },
    PressFamily: {
        "source": "idc",
        "segment": "pcs",
        "area": "ww",
        "pattern": "PC",
        "exclude": "monitor",
        "search": "PC",
    },
    CoverageEntry: {
        "key": "s",
        "granularity": "month",
        "first": "2009-01-01",
        "last": "2026-10-01",
        "points": 214,
        "longest_gap": 0,
        "enough": True,
    },
    LagCorrelation: {"lag": 3, "rho": 0.5, "low": 0.3, "high": 0.7, "p_value": 0.01, "q_value": 0.02, "months": 80},
    ShareSeries: {"company": "google", "label": "Google", "labels": ["Chrome"], "points": [], "estimate": False},
    ControlHelp: {"control": "against", "title": "Against", "summary": "What the share is correlated with."},
    OptionHelp: {"control": "against", "option": "stock", "summary": "The returns of the primary listing."},
    MarketsHelp: {
        "controls": [{"control": "top", "title": "Top", "summary": "The companies drawn."}],
        "options": [],
        "method": "Spearman, lags -{lags} to +{lags} {unit}.",
    },
    Counterpart: {
        "kind": "share",
        "label": "Smartphones · Worldwide · IDC",
        "segment": "smartphones",
        "area": "ww",
        "source": "idc",
        "listing": None,
        "currency": None,
    },
    ShareStockResult: {
        "company": "google",
        "segment": "search",
        "area": "ww",
        "device": "all",
        "listing": "NASDAQ:GOOGL",
        "counterpart": "stock",
        "counterpart_label": "NASDAQ:GOOGL",
        "granularity": "month",
        "share_coverage": None,
        "stock_coverage": None,
        "lags": [],
        "share_leads_p": 0.01,
        "stock_leads_p": 0.5,
        "granger_lags": 3,
        "refusal": None,
    },
    StockSeries: {
        "key": "NYSE:IBM",
        "company": "ibm",
        "label": "IBM",
        "currency": "USD",
        "primary": True,
        "points": [],
        "note": None,
    },
    FxRate: {"currency": "EUR", "day": "2026-10-16", "usd_per_unit": 1.12, "source": "fred"},
    MarketShareValue: {
        "segment": "search",
        "area": "ww",
        "period": "2026-09-01",
        "granularity": "month",
        "metric": "usage",
        "device": "all",
        "source": "statcounter",
        "label": "Google",
        "company": "google",
        "value": 90.0,
        "estimate": False,
        "source_url": "u",
    },
}

TEXT, NUMBER, CHOICE, DAY, FLAG, LIST, FORMAT = (
    InvalidMarketTextError,
    InvalidMarketNumberError,
    InvalidMarketChoiceError,
    InvalidMarketDateError,
    InvalidMarketFlagError,
    InvalidMarketListError,
    InvalidMarketValueError,
)

# One rejected value per field of every model, with the markets error it must raise.
INVALID: List[Tuple[Type[BaseModel], str, JsonValue, Type[MarketsModelError]]] = [
    (CurrencySeries, "currency", 978, TEXT),
    (CurrencySeries, "series", "DEX US", FORMAT),
    (CurrencySeries, "quote", "per-euro", CHOICE),
    (GoogleFinanceSettings, "rpc_id", "", TEXT),
    (GoogleFinanceSettings, "period", 8.5, NUMBER),
    (GoogleFinanceSettings, "consent_cookies", ["SOCS"], LIST),
    (MarketArea, "key", "x", FORMAT),
    (MarketArea, "label", None, TEXT),
    (MarketArea, "kind", "planet", CHOICE),
    (MarketArea, "members", "DE", LIST),
    (SeriesLabel, "source", "gartner", CHOICE),
    (SeriesLabel, "label", "x" * 81, TEXT),
    (SeriesLabel, "company", "Google", FORMAT),
    (ShareSegment, "key", "Web Search", FORMAT),
    (ShareSegment, "label", 3, TEXT),
    (ShareSegment, "chronology", "Mobile OS", FORMAT),
    (ShareSegment, "source", "gartner", CHOICE),
    (ShareSegment, "stat", "social", CHOICE),
    (ShareSegment, "metric", "users", CHOICE),
    (ShareSegment, "devices", [], LIST),
    (ShareSegment, "first_month", "2025-13", FORMAT),
    (ShareSegment, "description", "x" * 601, TEXT),
    (ChartDot, "day", "yesterday", DAY),
    (ChartDot, "value", 0, NUMBER),
    (ChartDot, "color", "purple", FORMAT),
    (ChartDot, "label", "", TEXT),
    (ChartDot, "tooltip", 1, TEXT),
    (ChartLine, "key", None, TEXT),
    (ChartLine, "label", "", TEXT),
    (ChartLine, "color", "#12345", FORMAT),
    (ChartLine, "dashed", "yes", FLAG),
    (ChartLine, "dots", 1, FLAG),
    (ChartLine, "points", [["2020-01-01"]], LIST),
    (ChartLine, "note", "x" * 601, TEXT),
    (CrawlScope, "areas", 3, LIST),
    (CrawlScope, "listings", ["x" * 31], TEXT),
    (CrawlScope, "companies", ["x" * 31], TEXT),
    (CrawlScope, "since", "2026", FORMAT),
    (FxObservation, "series", "DEX", TEXT),
    (FxObservation, "day", "16/10/2026", DAY),
    (FxObservation, "value", -1.0, NUMBER),
    (FxObservation, "source_url", "", TEXT),
    (PricePoint, "listing", "IB", TEXT),
    (PricePoint, "day", 19861024, DAY),
    (PricePoint, "close", "n/a", NUMBER),
    (PricePoint, "volume", -5, NUMBER),
    (PricePoint, "currency", "US$", FORMAT),
    (PricePoint, "source_url", None, TEXT),
    (ReleaseShare, "source", "gartner", CHOICE),
    (ReleaseShare, "segment", "", TEXT),
    (ReleaseShare, "area", "w", TEXT),
    (ReleaseShare, "period", "2Q26", DAY),
    (ReleaseShare, "granularity", "week", CHOICE),
    (ReleaseShare, "label", "", TEXT),
    (ReleaseShare, "value", "101%", NUMBER),
    (ReleaseShare, "title", "", TEXT),
    (ReleaseShare, "published", None, DAY),
    (ReleaseShare, "source_url", 2, TEXT),
    (ShareObservation, "stat", "social", CHOICE),
    (ShareObservation, "area", "U", TEXT),
    (ShareObservation, "device", "console", CHOICE),
    (ShareObservation, "month", "2026-9", DAY),
    (ShareObservation, "label", "", TEXT),
    (ShareObservation, "value", math.nan, NUMBER),
    (ShareObservation, "source_url", "", TEXT),
    (WeightObservation, "indicator", "NY.GDP", CHOICE),
    (WeightObservation, "country", "DEU", TEXT),
    (WeightObservation, "year", 1950, NUMBER),
    (WeightObservation, "value", -1, NUMBER),
    (WeightObservation, "source_url", [], TEXT),
    (HqRegion, "key", "US", FORMAT),
    (HqRegion, "label", "", TEXT),
    (HqRegion, "countries", ["USA"], FORMAT),
    (StockListing, "company", "IBM", FORMAT),
    (StockListing, "symbol", "IBM", FORMAT),
    (StockListing, "currency", "DOLLAR", TEXT),
    (StockListing, "primary", "true", FLAG),
    (StockListing, "note", "x" * 201, TEXT),
    (ValuationPoint, "company", "Dec", FORMAT),
    (ValuationPoint, "date", "Jan 1998", FORMAT),
    (ValuationPoint, "kind", "rumour", CHOICE),
    (ValuationPoint, "value_bn", 0, NUMBER),
    (ValuationPoint, "high_bn", True, NUMBER),
    (ValuationPoint, "label", "", TEXT),
    (ValuationPoint, "source", None, TEXT),
    (ValuationPoint, "tag", "Primary filing", TEXT),
    (MarketsCatalog, "statcounter_from", "2009", FORMAT),
    (MarketsCatalog, "google_finance", "c2u4wc", LIST),
    (MarketsCatalog, "segments", {}, LIST),
    (MarketsCatalog, "areas", "ww", LIST),
    (MarketsCatalog, "labels", ["Chrome"], LIST),
    (MarketsCatalog, "currencies", None, LIST),
    (MarketsCatalog, "regions", 1, LIST),
    (MarketsCatalog, "listings", "NYSE:IBM", LIST),
    (MarketsCatalog, "valuations", [3], LIST),
    (MarketsCatalog, "press", {"source": "idc"}, LIST),
    (MarketsCatalog, "manual_shares", ["IBM 52%"], LIST),
    (MarketsCatalog, "press_names", [""], TEXT),
    (MarketsCatalog, "country_currencies", {"USA": "USD"}, FORMAT),
    (ManualShare, "segment", "Mainframes", FORMAT),
    (ManualShare, "area", "U", TEXT),
    (ManualShare, "period", "1961-Q1", FORMAT),
    (ManualShare, "label", "", TEXT),
    (ManualShare, "company", "IBM", FORMAT),
    (ManualShare, "value", 120, NUMBER),
    (ManualShare, "source", None, TEXT),
    (ManualShare, "tag", "Academic history", TEXT),
    (PressFamily, "source", "gartner", CHOICE),
    (PressFamily, "segment", "PCs", FORMAT),
    (PressFamily, "area", "w", TEXT),
    (PressFamily, "pattern", "(unclosed", FORMAT),
    (PressFamily, "exclude", 5, TEXT),
    (PressFamily, "search", "x" * 81, TEXT),
    (CoverageEntry, "key", "", TEXT),
    (CoverageEntry, "granularity", "week", CHOICE),
    (CoverageEntry, "first", "January", DAY),
    (CoverageEntry, "last", 2026, DAY),
    (CoverageEntry, "points", -1, NUMBER),
    (CoverageEntry, "longest_gap", 1.5, NUMBER),
    (CoverageEntry, "enough", "no", FLAG),
    (LagCorrelation, "lag", 25, NUMBER),
    (LagCorrelation, "rho", 1.5, NUMBER),
    (LagCorrelation, "low", -2, NUMBER),
    (LagCorrelation, "high", "high", NUMBER),
    (LagCorrelation, "p_value", 1.2, NUMBER),
    (LagCorrelation, "q_value", -0.1, NUMBER),
    (LagCorrelation, "months", 2.5, NUMBER),
    (ShareSeries, "company", 7, TEXT),
    (ShareSeries, "label", "", TEXT),
    (ShareSeries, "labels", [""], TEXT),
    (ShareSeries, "points", [["2020-01-01", "x"]], LIST),
    (ShareSeries, "estimate", None, FLAG),
    (ShareStockResult, "company", "", TEXT),
    (ShareStockResult, "segment", None, TEXT),
    (ShareStockResult, "area", "x" * 13, TEXT),
    (ShareStockResult, "device", "x" * 9, TEXT),
    (ShareStockResult, "listing", "x" * 31, TEXT),
    (ShareStockResult, "granularity", "week", CHOICE),
    (ShareStockResult, "share_coverage", "36 months", LIST),
    (ShareStockResult, "stock_coverage", [1], LIST),
    (ShareStockResult, "counterpart", "bond", CHOICE),
    (ShareStockResult, "counterpart_label", "x" * 121, TEXT),
    (ControlHelp, "control", "zoom", CHOICE),
    (ControlHelp, "title", "x" * 61, TEXT),
    (ControlHelp, "summary", "", TEXT),
    (OptionHelp, "control", "zoom", CHOICE),
    (OptionHelp, "option", "", TEXT),
    (OptionHelp, "summary", None, TEXT),
    (MarketsHelp, "controls", "top", LIST),
    (MarketsHelp, "options", ["top"], LIST),
    (MarketsHelp, "method", "x" * 1201, TEXT),
    (Counterpart, "kind", "bond", CHOICE),
    (Counterpart, "label", "", TEXT),
    (Counterpart, "segment", "x" * 41, TEXT),
    (Counterpart, "area", "x" * 13, TEXT),
    (Counterpart, "source", "gartner", CHOICE),
    (Counterpart, "listing", "x" * 31, TEXT),
    (Counterpart, "currency", "EURO", TEXT),
    (ShareStockResult, "lags", [0.5], LIST),
    (ShareStockResult, "share_leads_p", 2, NUMBER),
    (ShareStockResult, "stock_leads_p", "p", NUMBER),
    (ShareStockResult, "granger_lags", 0, NUMBER),
    (ShareStockResult, "refusal", "x" * 601, TEXT),
    (StockSeries, "key", "", TEXT),
    (StockSeries, "company", 1, TEXT),
    (StockSeries, "label", None, TEXT),
    (StockSeries, "currency", "", TEXT),
    (StockSeries, "primary", 0, FLAG),
    (StockSeries, "points", [["2020-01-01", 0]], LIST),
    (StockSeries, "note", 3.0, TEXT),
    (FxRate, "currency", "eu", FORMAT),
    (FxRate, "day", None, DAY),
    (FxRate, "usd_per_unit", 0, NUMBER),
    (FxRate, "source", "ecb", CHOICE),
    (MarketShareValue, "segment", "", TEXT),
    (MarketShareValue, "area", "w", TEXT),
    (MarketShareValue, "period", "2026-09", DAY),
    (MarketShareValue, "granularity", "week", CHOICE),
    (MarketShareValue, "metric", "users", CHOICE),
    (MarketShareValue, "device", "console", CHOICE),
    (MarketShareValue, "source", "gartner", CHOICE),
    (MarketShareValue, "label", None, TEXT),
    (MarketShareValue, "company", 1, TEXT),
    (MarketShareValue, "value", 100.5, NUMBER),
    (MarketShareValue, "estimate", "false", FLAG),
    (MarketShareValue, "source_url", ["u"], TEXT),
]


def errors_of(model: Type[BaseModel], payload: Dict[str, JsonValue]) -> List[BaseException]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)
    return [item["ctx"]["error"] for item in caught.value.errors() if "error" in item.get("ctx", {})]


@pytest.mark.parametrize("model", list(VALID), ids=lambda model: model.__name__)
def test_the_valid_payload_of_every_model_is_accepted(model: Type[BaseModel]) -> None:
    assert model.model_validate(VALID[model]) is not None


def test_every_field_of_every_model_has_a_rejected_case() -> None:
    covered = {(model, field) for model, field, _, _ in INVALID}

    assert covered == {(model, field) for model in VALID for field in model.model_fields}


@pytest.mark.parametrize(
    ("model", "field", "value", "error"),
    INVALID,
    ids=[f"{model.__name__}.{field}" for model, field, _, _ in INVALID],
)
def test_a_bad_value_raises_its_markets_error(
    model: Type[BaseModel], field: str, value: JsonValue, error: Type[MarketsModelError]
) -> None:
    raised = errors_of(model, {**VALID[model], field: value})

    assert raised
    assert isinstance(raised[0], error)
    assert isinstance(raised[0], MarketsModelError)


class TestMarketFieldCheck:
    def test_texts_are_cleaned_or_refused(self) -> None:
        assert CHECK.text("  two   words ", "t", 20) == "two words"
        assert CHECK.text("  keep   spaces ", "t", 20, collapse=False) == "keep   spaces"
        assert CHECK.text("   ", "t", 20, optional=True) is None
        with pytest.raises(InvalidMarketTextError, match="1 to 3 characters"):
            CHECK.text("four", "t", 3)

    def test_numbers_are_converted_or_refused(self) -> None:
        assert CHECK.number("24.4%", "n", low=0, high=100) == pytest.approx(24.4)
        assert CHECK.number(2024.0, "n", integer=True) == 2024
        assert CHECK.number(None, "n", optional=True) is None
        with pytest.raises(InvalidMarketNumberError, match="above 0"):
            CHECK.number(0, "n", low=0, strict_low=True)
        with pytest.raises(InvalidMarketNumberError):
            CHECK.number(True, "n")
        with pytest.raises(InvalidMarketNumberError):
            CHECK.number(math.inf, "n")

    def test_choices_dates_flags_and_lists(self) -> None:
        assert CHECK.choice(" all ", "c", ["all"]) == "all"
        assert CHECK.day(datetime(2026, 10, 23, 12, 0), "d") == date(2026, 10, 23)
        assert CHECK.day("2026-10-23T12:00:00+00:00", "d") == date(2026, 10, 23)
        assert CHECK.iso_day(date(2026, 1, 2), "d") == "2026-01-02"
        assert CHECK.flag(False, "f") is False
        assert CHECK.items(["a", "b"], "l", "texts") == ["a", "b"]
        with pytest.raises(InvalidMarketChoiceError, match="one of all"):
            CHECK.choice("mobile", "c", ["all"])

    def test_points_are_sorted_and_checked(self) -> None:
        points = CHECK.points([["2020-02-01", 2], ["2020-01-01", "1"]], "p")

        assert points == [(date(2020, 1, 1), 1.0), (date(2020, 2, 1), 2.0)]
        with pytest.raises(InvalidMarketListError, match="above zero"):
            CHECK.points([["2020-01-01", 0]], "p", positive=True)
