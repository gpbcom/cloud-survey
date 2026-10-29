from __future__ import annotations

from typing import Dict

from analytics.companies.checks.figure_checker import FigureChecker
from models.companies.enums import FigureBasis, FigureScale, FinancialMetric
from models.companies.figures.reported_year import ReportedYear
from models.curated.enums import FigureCheck


def year(figures: Dict[FinancialMetric, float]) -> ReportedYear:
    return ReportedYear(fiscal_year=1994, basis=FigureBasis.FILING, source="https://www.sec.gov/x.txt", figures=figures)


def test_figures_written_in_the_document_scale_match() -> None:
    checked = year(
        {
            FinancialMetric.REVENUE: 5584.0,
            FinancialMetric.NET_INCOME: 329.121,
            FinancialMetric.EMPLOYEES: 79800.0,
        }
    )

    status, note = FigureChecker().check(checked, FigureScale.MILLIONS, sorted([5583912.0, 329121.0, 79800.0]))

    assert status is FigureCheck.MATCH
    assert note is None


def test_the_figures_a_document_does_not_state_are_named() -> None:
    checked = year({FinancialMetric.REVENUE: 26213.0, FinancialMetric.NET_INCOME: 3562.0})

    status, note = FigureChecker().check(checked, FigureScale.MILLIONS, [99.0, 26213.0])

    assert status is FigureCheck.MISMATCH
    assert note == "not found: net-income"


def test_a_document_without_number_or_figure_is_unparsed() -> None:
    checked = year({FinancialMetric.REVENUE: 26213.0})

    assert FigureChecker().check(checked, FigureScale.MILLIONS, [])[0] is FigureCheck.UNPARSED
    assert FigureChecker().check(checked, FigureScale.MILLIONS, [1.0, 2.0])[0] is FigureCheck.UNPARSED


def test_a_negative_figure_matches_the_amount_in_parentheses() -> None:
    checked = year({FinancialMetric.NET_INCOME: -172.5, FinancialMetric.REVENUE: 5322.0})

    status, _ = FigureChecker().check(checked, FigureScale.MILLIONS, [172500.0, 5322000.0])

    assert status is FigureCheck.MATCH
