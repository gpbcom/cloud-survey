from __future__ import annotations

from datetime import date
from typing import Dict, List, Mapping, Sequence, Tuple

import pytest

from analytics.companies.health.altman_score import AltmanScore
from analytics.companies.health.growth_indicators import GrowthIndicators
from analytics.companies.health.indicator_points import IndicatorPoints
from analytics.companies.health.piotroski_score import PiotroskiScore
from analytics.companies.health.private_proxies import PrivateProxies
from analytics.companies.indicators.currency_rates import CurrencyRates
from analytics.companies.indicators.financial_book import FinancialBook
from analytics.companies.indicators.financial_indicators import FinancialIndicators
from crawler.companies.catalog_loader import CompaniesCatalogLoader
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorUnit,
    StatementKind,
)
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
from models.markets.listings.valuation_point import ValuationPoint

YEAR, INSTANT = FinancialGranularity.YEAR, FinancialGranularity.INSTANT
ENDS = [date(2021, 12, 31), date(2022, 12, 31), date(2023, 12, 31)]
Key = Tuple[CompanyIndicator, FinancialGranularity, date]


def line(metric: FinancialMetric, end: date, amount: float, granularity: FinancialGranularity) -> FinancialValue:
    return FinancialValue(
        company="acme",
        metric=metric,
        period_end=end,
        granularity=granularity,
        source=FinancialSource.EDGAR,
        value=amount,
        currency="USD",
        concept="test",
    )


def book_of(figures: Mapping[FinancialMetric, Sequence[float]]) -> FinancialBook:
    """A book of three fiscal years: each line's figures for 2021, 2022 and 2023."""
    concepts = CompaniesCatalogLoader().concepts()
    values: List[FinancialValue] = []
    for metric, amounts in figures.items():
        nature = concepts.nature(metric)
        granularity = INSTANT if nature is not None and nature.value == "balance" else YEAR
        values += [line(metric, end, amount, granularity) for end, amount in zip(ENDS, amounts, strict=True)]
    return FinancialBook(values, concepts)


def keyed(points: List[IndicatorValue]) -> Dict[Key, IndicatorValue]:
    return {(point.indicator, point.granularity, point.period_end): point for point in points}


@pytest.fixture
def builder() -> IndicatorPoints:
    return IndicatorPoints(CurrencyRates([]))


# A textbook company: working capital 100, retained earnings 300, EBIT 150, revenue 1,000, assets 1,000, liabilities
# 400, equity 600.
TEXTBOOK = {
    FinancialMetric.TOTAL_ASSETS: (1000.0, 1000.0, 1000.0),
    FinancialMetric.CURRENT_ASSETS: (300.0, 300.0, 300.0),
    FinancialMetric.CURRENT_LIABILITIES: (200.0, 200.0, 200.0),
    FinancialMetric.RETAINED_EARNINGS: (300.0, 300.0, 300.0),
    FinancialMetric.TOTAL_EQUITY: (600.0, 600.0, 600.0),
    FinancialMetric.TOTAL_LIABILITIES: (400.0, 400.0, 400.0),
    FinancialMetric.OPERATING_INCOME: (150.0, 150.0, 150.0),
    FinancialMetric.REVENUE: (1000.0, 1000.0, 1000.0),
}


class TestAltmanScore:
    def test_the_book_value_score_follows_the_1995_weights(self, builder: IndicatorPoints) -> None:
        points = keyed(AltmanScore(CurrencyRates([]), builder).compute("acme", book_of(TEXTBOOK), []))

        score = points[(CompanyIndicator.ALTMAN_Z_DOUBLE_PRIME, YEAR, ENDS[2])]
        assert score.value == pytest.approx(6.56 * 0.1 + 3.26 * 0.3 + 6.72 * 0.15 + 1.05 * 1.5)
        assert score.unit is IndicatorUnit.SCORE
        assert (CompanyIndicator.ALTMAN_Z, YEAR, ENDS[2]) not in points

    def test_the_market_score_needs_a_market_cap_near_the_period_end(self, builder: IndicatorPoints) -> None:
        cap = IndicatorValue(
            company="acme",
            indicator=CompanyIndicator.MARKET_CAP,
            period_end=date(2023, 12, 29),
            granularity=FinancialGranularity.WEEK,
            value=2000.0,
            unit=IndicatorUnit.CURRENCY,
            currency="USD",
            inputs="x",
        )

        points = keyed(AltmanScore(CurrencyRates([]), builder).compute("acme", book_of(TEXTBOOK), [cap]))

        expected = 1.2 * 0.1 + 1.4 * 0.3 + 3.3 * 0.15 + 0.6 * 2000 / 400 + 1.0 * 1.0
        assert points[(CompanyIndicator.ALTMAN_Z, YEAR, ENDS[2])].value == pytest.approx(expected)

    def test_no_score_without_retained_earnings_nor_for_a_bank(self, builder: IndicatorPoints) -> None:
        figures: Dict[FinancialMetric, Sequence[float]] = {
            metric: amounts for metric, amounts in TEXTBOOK.items() if metric is not FinancialMetric.RETAINED_EARNINGS
        }
        altman = AltmanScore(CurrencyRates([]), builder)

        assert altman.compute("acme", book_of(figures), []) == []
        assert altman.compute("acme", book_of(TEXTBOOK), [], StatementKind.BANK) == []


# Three years improving on every test (2023 against 2022 and 2021).
STRONG = {
    FinancialMetric.NET_INCOME: (50.0, 80.0, 120.0),
    FinancialMetric.OPERATING_CASH_FLOW: (60.0, 90.0, 150.0),
    FinancialMetric.TOTAL_ASSETS: (1000.0, 1000.0, 1000.0),
    FinancialMetric.LONG_TERM_DEBT: (300.0, 250.0, 200.0),
    FinancialMetric.CURRENT_ASSETS: (300.0, 320.0, 350.0),
    FinancialMetric.CURRENT_LIABILITIES: (200.0, 200.0, 200.0),
    FinancialMetric.SHARES_OUTSTANDING: (100.0, 100.0, 100.0),
    FinancialMetric.REVENUE: (800.0, 900.0, 1000.0),
    FinancialMetric.GROSS_PROFIT: (300.0, 360.0, 420.0),
}


class TestPiotroskiScore:
    def test_a_company_improving_everywhere_scores_nine(self, builder: IndicatorPoints) -> None:
        points = PiotroskiScore(builder).compute("acme", book_of(STRONG))

        assert [(point.period_end, point.value) for point in points] == [(ENDS[2], 9.0)]
        assert points[0].inputs.startswith("+ROA>0 +CFO>0")

    def test_a_company_worsening_everywhere_scores_zero(self, builder: IndicatorPoints) -> None:
        weak = {metric: tuple(reversed(amounts)) for metric, amounts in STRONG.items()}
        weak[FinancialMetric.NET_INCOME] = (10.0, -20.0, -50.0)
        weak[FinancialMetric.OPERATING_CASH_FLOW] = (5.0, -30.0, -80.0)
        weak[FinancialMetric.SHARES_OUTSTANDING] = (100.0, 110.0, 120.0)

        points = PiotroskiScore(builder).compute("acme", book_of(weak))

        assert [point.value for point in points] == [0.0]

    def test_no_score_without_three_years_or_a_test(self, builder: IndicatorPoints) -> None:
        partial: Dict[FinancialMetric, Sequence[float]] = {
            metric: amounts for metric, amounts in STRONG.items() if metric is not FinancialMetric.GROSS_PROFIT
        }

        assert PiotroskiScore(builder).compute("acme", book_of(partial)) == []


class TestGrowthAndRatios:
    def test_growth_needs_a_positive_year_before(self, builder: IndicatorPoints) -> None:
        book = book_of({FinancialMetric.REVENUE: (100.0, 120.0, 90.0), FinancialMetric.NET_INCOME: (-5.0, 10.0, 15.0)})

        points = keyed(GrowthIndicators(builder).compute("acme", book))

        assert points[(CompanyIndicator.REVENUE_GROWTH, YEAR, ENDS[1])].value == pytest.approx(20.0)
        assert points[(CompanyIndicator.REVENUE_GROWTH, YEAR, ENDS[2])].value == pytest.approx(-25.0)
        assert (CompanyIndicator.NET_INCOME_GROWTH, YEAR, ENDS[1]) not in points
        assert points[(CompanyIndicator.NET_INCOME_GROWTH, YEAR, ENDS[2])].value == pytest.approx(50.0)

    def test_coverage_conversion_payout_and_working_capital(self) -> None:
        book = book_of(
            {
                FinancialMetric.REVENUE: (1000.0, 1000.0, 1000.0),
                FinancialMetric.NET_INCOME: (100.0, 100.0, 100.0),
                FinancialMetric.OPERATING_INCOME: (150.0, 150.0, 150.0),
                FinancialMetric.INTEREST_EXPENSE: (30.0, 30.0, 30.0),
                FinancialMetric.OPERATING_CASH_FLOW: (140.0, 140.0, 140.0),
                FinancialMetric.CAPEX: (20.0, 20.0, 20.0),
                FinancialMetric.BUYBACKS: (60.0, 60.0, 60.0),
                FinancialMetric.CURRENT_ASSETS: (300.0, 300.0, 300.0),
                FinancialMetric.CURRENT_LIABILITIES: (200.0, 200.0, 200.0),
            }
        )

        points = keyed(FinancialIndicators(CurrencyRates([])).compute("acme", book))

        assert points[(CompanyIndicator.INTEREST_COVERAGE, YEAR, ENDS[2])].value == pytest.approx(5.0)
        assert points[(CompanyIndicator.CASH_CONVERSION, YEAR, ENDS[2])].value == pytest.approx(120.0)
        payout = points[(CompanyIndicator.PAYOUT_RATIO, YEAR, ENDS[2])]
        assert (payout.value, payout.inputs) == (pytest.approx(60.0), "(buybacks) / net-income")
        assert points[(CompanyIndicator.WORKING_CAPITAL, YEAR, ENDS[2])].value == pytest.approx(100.0)

    def test_a_bank_has_no_liquidity_ratio(self) -> None:
        book = book_of(
            {
                FinancialMetric.REVENUE: (1000.0, 1000.0, 1000.0),
                FinancialMetric.CURRENT_ASSETS: (300.0, 300.0, 300.0),
                FinancialMetric.CURRENT_LIABILITIES: (200.0, 200.0, 200.0),
            }
        )

        points = keyed(FinancialIndicators(CurrencyRates([])).compute("acme", book, StatementKind.BANK))

        assert not {key[0] for key in points} & {CompanyIndicator.CURRENT_RATIO, CompanyIndicator.WORKING_CAPITAL}


class TestPrivateProxies:
    def test_rounds_add_up_and_valuations_come_from_the_catalogue(self, builder: IndicatorPoints) -> None:
        values = [
            line(FinancialMetric.FUNDING_RAISED, date(2023, 1, 1), 300e6, INSTANT),
            line(FinancialMetric.FUNDING_RAISED, date(2023, 6, 1), 100e6, INSTANT),
            line(FinancialMetric.FUNDING_RAISED, date(2024, 2, 1), 500e6, INSTANT),
            line(FinancialMetric.EMPLOYEES, date(2024, 2, 1), 1200, INSTANT),
        ]
        book = FinancialBook(values, CompaniesCatalogLoader().concepts())
        valuation = ValuationPoint(
            company="acme",
            date="2024-02",
            kind="private-round",
            value_bn=18.5,
            label="Series C",
            source="press",
            tag="J",
        )

        points = keyed(PrivateProxies(builder).compute("acme", book, [valuation]))

        assert points[(CompanyIndicator.FUNDING_RAISED, YEAR, date(2023, 12, 31))].value == 400e6
        assert points[(CompanyIndicator.FUNDING_TOTAL, INSTANT, date(2024, 2, 1))].value == 900e6
        assert points[(CompanyIndicator.EMPLOYEES, INSTANT, date(2024, 2, 1))].unit is IndicatorUnit.COUNT
        assert points[(CompanyIndicator.VALUATION, INSTANT, date(2024, 2, 1))].value == 18.5e9
