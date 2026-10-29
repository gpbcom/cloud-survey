from __future__ import annotations

from typing import Dict, List, Tuple, Type

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from crawler.companies.catalog_loader import CompaniesCatalogLoader
from curated.bundle.bundle_catalogs import BundleCatalogs
from models.companies.concepts.schedules.schedule_layout import ScheduleLayout
from models.companies.concepts.schedules.schedule_tag import ScheduleTag
from models.companies.enums import CompanyIndicator, FinancialMetric, IndicatorFamily
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.companies.figures.reported_company import ReportedCompany
from models.companies.figures.reported_event import ReportedEvent
from models.companies.figures.reported_figures import ReportedFigures
from models.companies.figures.reported_year import ReportedYear
from models.companies.help.financial_control_help import FinancialControlHelp
from models.companies.help.financials_help import FinancialsHelp
from models.companies.help.indicator_family_help import IndicatorFamilyHelp
from models.companies.help.indicator_help import IndicatorHelp
from models.markets.exception import (
    InvalidMarketChoiceError,
    InvalidMarketDateError,
    InvalidMarketFlagError,
    InvalidMarketListError,
    InvalidMarketNumberError,
    InvalidMarketTextError,
)

TEXT, NUMBER, CHOICE, DAY, FLAG, LIST = (
    InvalidMarketTextError,
    InvalidMarketNumberError,
    InvalidMarketChoiceError,
    InvalidMarketDateError,
    InvalidMarketFlagError,
    InvalidMarketListError,
)
FORMAT, DUPLICATE = InvalidCompanyValueError, DuplicateCompanyKeyError
SOURCE = "https://www.sec.gov/Archives/edgar/data/28887/0000950135-97-003950.txt"
YEAR: Dict[str, JsonValue] = {
    "fiscal_year": 1997,
    "period_end": "1997-06-28",
    "basis": "filing",
    "source": SOURCE,
    "published": "1997-09-15",
    "note": "10-K fiscal 1997, selected financial data.",
    "figures": {"revenue": 13046.8, "net-income": 141.0, "rd-expense": 1080.6, "employees": 54900},
}
EVENT: Dict[str, JsonValue] = {
    "date": "2023-01-23",
    "metric": "funding-raised",
    "value": 10000,
    "currency": "usd",
    "basis": "press",
    "source": "https://blogs.microsoft.com/blog/2023/01/23/microsoftandopenaiextendpartnership/",
    "note": "Microsoft's investment.",
}
HELP_INDICATORS: List[JsonValue] = [
    {"indicator": item.value, "family": "size", "title": item.value, "formula": "x", "summary": "x"}
    for item in CompanyIndicator
]

# A valid payload of every model.
VALID: Dict[Type[BaseModel], Dict[str, JsonValue]] = {
    ReportedYear: YEAR,
    ReportedEvent: EVENT,
    ReportedCompany: {
        "company": "dec",
        "currency": "USD",
        "fiscal_year_end": "06-30",
        "scale": "millions",
        "years": [YEAR, {**YEAR, "fiscal_year": 1996, "period_end": None}],
        "events": [],
    },
    ReportedFigures: {"companies": [{"company": "dec", "currency": "USD", "years": [YEAR]}]},
    ScheduleTag: {"tag": "TOTAL-REVENUES", "metric": "revenue", "rank": 0, "sum": False, "per_share": False},
    ScheduleLayout: {"articles": [5], "tags": [{"tag": "COMMON", "metric": "total-equity", "sum": True}]},
    FinancialControlHelp: {"control": "currency", "title": "Currency", "summary": "The currency of the amounts."},
    IndicatorFamilyHelp: {"family": "scores", "title": "Health scores", "summary": "Composite scores."},
    IndicatorHelp: {
        "indicator": "altman-z",
        "family": "scores",
        "title": "Altman Z-score",
        "formula": "1.2 × working capital ÷ assets + …",
        "summary": "The 1968 bankruptcy predictor.",
        "caveat": "Listed companies only.",
    },
    FinancialsHelp: {
        "controls": [{"control": "period", "title": "Period", "summary": "Years or quarters."}],
        "families": [{"family": "size", "title": "Size", "summary": "How big."}],
        "indicators": HELP_INDICATORS,
    },
}

# A rejected value of every field, and the error it raises.
INVALID: List[Tuple[Type[BaseModel], str, JsonValue, Type[ValueError]]] = [
    (ReportedYear, "fiscal_year", 1949, NUMBER),
    (ReportedYear, "period_end", "1998-03-31", FORMAT),
    (ReportedYear, "basis", "run-rate", CHOICE),
    (ReportedYear, "source", "http://example.com/report.pdf", FORMAT),
    (ReportedYear, "published", "soon", DAY),
    (ReportedYear, "note", "x" * 501, TEXT),
    (ReportedYear, "figures", {"rd-expense": -1}, NUMBER),
    (ReportedEvent, "date", "2023-13", FORMAT),
    (ReportedEvent, "metric", "revenue", CHOICE),
    (ReportedEvent, "value", -5, NUMBER),
    (ReportedEvent, "currency", "dollars", TEXT),
    (ReportedEvent, "basis", "rumour", CHOICE),
    (ReportedEvent, "source", "ftp://example.com", FORMAT),
    (ReportedEvent, "note", 3, TEXT),
    (ReportedCompany, "company", "Digital Equipment", FORMAT),
    (ReportedCompany, "currency", "us", FORMAT),
    (ReportedCompany, "fiscal_year_end", "02-30", FORMAT),
    (ReportedCompany, "scale", "lakhs", CHOICE),
    (ReportedCompany, "years", [YEAR, YEAR], DUPLICATE),
    (ReportedCompany, "events", "round", LIST),
    (ReportedFigures, "companies", [{"company": "dec"}, {"company": "dec"}], DUPLICATE),
    (ScheduleTag, "tag", "total revenues", FORMAT),
    (ScheduleTag, "metric", "sales", CHOICE),
    (ScheduleTag, "rank", 21, NUMBER),
    (ScheduleTag, "sum", "yes", FLAG),
    (ScheduleTag, "per_share", 1, FLAG),
    (ScheduleLayout, "articles", [13], NUMBER),
    (ScheduleLayout, "tags", [{"tag": "CASH", "metric": "cash"}, {"tag": "CASH", "metric": "cash"}], DUPLICATE),
    (FinancialControlHelp, "control", "zoom", CHOICE),
    (FinancialControlHelp, "title", "", TEXT),
    (FinancialControlHelp, "summary", "x" * 901, TEXT),
    (IndicatorFamilyHelp, "family", "luck", CHOICE),
    (IndicatorFamilyHelp, "title", "x" * 61, TEXT),
    (IndicatorFamilyHelp, "summary", "", TEXT),
    (IndicatorHelp, "indicator", "beta", CHOICE),
    (IndicatorHelp, "family", "luck", CHOICE),
    (IndicatorHelp, "title", "", TEXT),
    (IndicatorHelp, "formula", "x" * 301, TEXT),
    (IndicatorHelp, "summary", 3, TEXT),
    (IndicatorHelp, "caveat", "x" * 601, TEXT),
    (FinancialsHelp, "controls", [{"control": "period"}, {"control": "period"}], DUPLICATE),
    (FinancialsHelp, "families", "size", LIST),
    (FinancialsHelp, "indicators", HELP_INDICATORS[1:], FORMAT),
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
def test_a_bad_value_raises_its_error(
    model: Type[BaseModel], field: str, value: JsonValue, error: Type[ValueError]
) -> None:
    raised = errors_of(model, {**VALID[model], field: value})

    assert raised
    assert isinstance(raised[0], error)


class TestReportedFigures:
    def test_a_year_reads_its_lines_and_counts_its_employees(self) -> None:
        year = ReportedYear.model_validate(YEAR)

        assert year.figures[FinancialMetric.RD_EXPENSE] == 1080.6
        assert year.figures[FinancialMetric.EMPLOYEES] == 54900

    def test_a_53_week_year_ending_early_january_belongs_to_the_year_before(self) -> None:
        year = ReportedYear.model_validate({**YEAR, "fiscal_year": 1999, "period_end": "2000-01-02"})

        assert year.period_end is not None
        assert year.period_end.year == 2000

    def test_a_loss_is_a_negative_net_income(self) -> None:
        year = ReportedYear.model_validate({**YEAR, "figures": {"net-income": -2088.0}})

        assert year.figures[FinancialMetric.NET_INCOME] == -2088.0

    def test_employees_must_be_whole(self) -> None:
        assert isinstance(errors_of(ReportedYear, {**YEAR, "figures": {"employees": 10.5}})[0], NUMBER)

    def test_the_catalogue_finds_a_company(self) -> None:
        figures = ReportedFigures.model_validate(VALID[ReportedFigures])

        assert figures.of("dec") is not None
        assert figures.of("ibm") is None


class TestShippedFiles:
    def test_the_figures_name_companies_of_the_chronology(self) -> None:
        figures = BundleCatalogs().figures()

        assert all(entry.years or entry.events for entry in figures.companies)

    def test_the_help_explains_every_indicator_under_a_listed_family(self) -> None:
        helps = CompaniesCatalogLoader().help()
        families = [item.family for item in helps.families]

        assert set(families) == set(IndicatorFamily)
        assert {item.family for item in helps.indicators} <= set(families)
        assert sum(len(helps.family_of(family)) for family in families) == len(CompanyIndicator)

    def test_the_schedule_tags_leave_the_accumulated_depreciation_out(self) -> None:
        tags = CompaniesCatalogLoader().concepts().fds.by_tag()

        assert "DEPRECIATION" not in tags
        assert "PP&E" not in tags
        assert tags["EPS-DILUTED"].per_share
        assert {tag for tag, item in tags.items() if item.sum} == {"COMMON", "OTHER-SE", "PREFERRED"}
