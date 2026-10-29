from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from analytics.companies.financials.reported_lines import ReportedLines
from analytics.companies.indicators.financial_book import FinancialBook
from crawler.companies.catalog_loader import CompaniesCatalogLoader
from models.companies.enums import FinancialGranularity, FinancialMetric, FinancialSource
from models.companies.figures.reported_company import ReportedCompany
from models.companies.values.financial_value import FinancialValue

SOURCE = "https://www.sec.gov/Archives/edgar/data/28887/0000950135-97-003873.txt"
DEC = ReportedCompany.model_validate(
    {
        "company": "dec",
        "currency": "USD",
        "fiscal_year_end": "06-30",
        "scale": "millions",
        "years": [
            {
                "fiscal_year": 1985,
                "basis": "annual-report",
                "source": SOURCE,
                "published": "1985-09-15",
                "note": "Annual report 1985.",
                "figures": {"revenue": 6686.3, "total-assets": 6369.0, "employees": 89000},
            },
            {
                "fiscal_year": 1997,
                "period_end": "1997-06-28",
                "basis": "estimate",
                "source": SOURCE,
                "figures": {"revenue": 13000.0},
            },
        ],
        "events": [
            {"date": "2023-01", "metric": "funding-raised", "value": 300, "basis": "press", "source": SOURCE},
            {"date": "2023-01", "metric": "funding-raised", "value": 100, "basis": "press", "source": SOURCE},
            {"date": 2024, "metric": "revenue-run-rate", "value": 2000, "basis": "run-rate", "source": SOURCE},
        ],
    }
)


def converted() -> Dict[Tuple[FinancialMetric, FinancialGranularity, date], FinancialValue]:
    lines = ReportedLines(CompaniesCatalogLoader().concepts()).lines(DEC)
    return {(line.metric, line.granularity, line.period_end): line for line in lines}


def filed(metric: FinancialMetric, end: date, amount: float, granularity: FinancialGranularity) -> FinancialValue:
    return FinancialValue(
        company="dec",
        metric=metric,
        period_end=end,
        granularity=granularity,
        source=FinancialSource.EDGAR_FDS,
        value=amount,
        currency="USD",
        concept="fds:TOTAL-REVENUES",
    )


class TestReportedLines:
    def test_a_fiscal_year_gives_yearly_flows_and_dated_balances(self) -> None:
        lines = converted()

        revenue = lines[(FinancialMetric.REVENUE, FinancialGranularity.YEAR, date(1985, 6, 30))]
        assert (revenue.value, revenue.currency, revenue.source) == (6686.3e6, "USD", FinancialSource.REPORTED)
        assert (revenue.concept, revenue.fiscal_year, revenue.note) == ("annual-report", 1985, "Annual report 1985.")
        assert lines[(FinancialMetric.TOTAL_ASSETS, FinancialGranularity.INSTANT, date(1985, 6, 30))].value == 6369e6

    def test_employees_are_a_count_never_scaled(self) -> None:
        employees = converted()[(FinancialMetric.EMPLOYEES, FinancialGranularity.INSTANT, date(1985, 6, 30))]

        assert (employees.value, employees.currency) == (89000, None)

    def test_a_stated_period_end_and_the_basis_are_kept(self) -> None:
        revenue = converted()[(FinancialMetric.REVENUE, FinancialGranularity.YEAR, date(1997, 6, 28))]

        assert revenue.concept == "estimate"

    def test_rounds_of_a_same_day_add_up_and_events_are_dated_by_their_first_day(self) -> None:
        lines = converted()

        rounds = lines[(FinancialMetric.FUNDING_RAISED, FinancialGranularity.INSTANT, date(2023, 1, 1))]
        assert rounds.value == 400e6
        assert (FinancialMetric.REVENUE_RUN_RATE, FinancialGranularity.INSTANT, date(2024, 1, 1)) in lines


class TestFiledBeatsReported:
    def test_a_filed_year_a_few_days_off_drops_the_researched_one(self) -> None:
        values: List[FinancialValue] = [
            *ReportedLines(CompaniesCatalogLoader().concepts()).lines(DEC),
            filed(FinancialMetric.REVENUE, date(1997, 6, 28), 13046.8e6, FinancialGranularity.YEAR),
        ]

        book = FinancialBook(values, CompaniesCatalogLoader().concepts())
        figure = book.flow(FinancialMetric.REVENUE, FinancialGranularity.YEAR, date(1997, 6, 28))

        assert figure is not None
        assert figure[0] == 13046.8e6
        assert book.flow(FinancialMetric.REVENUE, FinancialGranularity.YEAR, date(1985, 6, 30)) is not None

    def test_a_researched_figure_names_its_basis(self) -> None:
        book = FinancialBook(
            ReportedLines(CompaniesCatalogLoader().concepts()).lines(DEC), CompaniesCatalogLoader().concepts()
        )

        figure = book.flow(FinancialMetric.REVENUE, FinancialGranularity.YEAR, date(1997, 6, 28))

        assert figure is not None
        assert figure[2] == "reported:estimate"
