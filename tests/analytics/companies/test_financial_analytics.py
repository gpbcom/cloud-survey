from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pytest

from analytics.companies.financials.financial_resolver import FinancialResolver
from analytics.companies.financials.flow_quarters import FlowQuarters
from analytics.companies.indicators.currency_rates import CurrencyRates
from analytics.companies.indicators.financial_book import FinancialBook
from analytics.companies.indicators.financial_indicators import FinancialIndicators
from analytics.companies.indicators.market_value import MarketValue
from analytics.companies.indicators.research_indicators import ResearchIndicators
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorUnit,
)
from models.companies.facts.financial_fact import FinancialFact
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
from models.markets.facts.price_point import PricePoint
from models.markets.listings.stock_listing import StockListing
from models.markets.values.fx_rate import FxRate

ENTRY = CompanyEntry(key="acme", sec_ciks=["1", "2"])
FY_END = date(2024, 12, 31)


def fact(
    metric: str,
    end: str,
    value: float,
    start: Optional[str] = None,
    concept: str = "us-gaap:Revenues",
    filer: str = "0000000001",
    filed: str = "2025-02-01",
) -> FinancialFact:
    return FinancialFact(
        company="acme",
        source="edgar",
        metric=metric,
        concept=concept,
        filer=filer,
        start=start,
        end=end,
        value=value,
        currency="USD",
        form="10-Q",
        filed=filed,
        source_url="u",
    )


def value(metric: FinancialMetric, end: date, amount: float, granularity: FinancialGranularity) -> FinancialValue:
    return FinancialValue(
        company="acme",
        metric=metric,
        period_end=end,
        granularity=granularity,
        source=FinancialSource.EDGAR,
        value=amount,
        currency="EUR",
        concept="test",
    )


def keyed(points: List[IndicatorValue]) -> Dict[Tuple[CompanyIndicator, FinancialGranularity, date], IndicatorValue]:
    return {(point.indicator, point.granularity, point.period_end): point for point in points}


class TestFlowQuarters:
    def test_the_quarters_are_filed_or_derived_and_the_years_kept(self) -> None:
        flows = FlowQuarters()
        durations = {
            (date(2024, 1, 1), date(2024, 3, 31)): 10.0,
            (date(2024, 1, 1), date(2024, 6, 30)): 25.0,
            (date(2024, 1, 1), date(2024, 9, 30)): 45.0,
            (date(2024, 1, 1), date(2024, 12, 31)): 70.0,
        }

        filed, derived = flows.quarters(durations)

        assert filed == {date(2024, 3, 31): 10.0}
        assert derived == {date(2024, 6, 30): 15.0, date(2024, 9, 30): 20.0, date(2024, 12, 31): 25.0}
        assert flows.years(durations) == {date(2024, 12, 31): 70.0}


class TestFinancialResolver:
    def test_the_latest_filing_the_current_filer_and_the_first_concept_win(
        self, financial_concepts: FinancialConcepts
    ) -> None:
        facts = [
            fact("revenue", "2024-12-31", 70.0, "2024-01-01", filed="2025-02-01"),
            fact("revenue", "2024-12-31", 72.0, "2024-01-01", filed="2026-02-01"),
            fact("revenue", "2024-12-31", 99.0, "2024-01-01", filer="0000000002"),
            fact("revenue", "2024-12-31", 98.0, "2024-01-01", concept="ifrs-full:Revenue"),
            fact("revenue", "2024-03-31", 10.0, "2024-01-01"),
            fact("revenue", "2024-06-30", 25.0, "2024-01-01"),
            fact("total-assets", "2024-12-31", 500.0, concept="us-gaap:Assets"),
        ]

        values = FinancialResolver(financial_concepts).resolve(ENTRY, facts)
        lines = {(line.metric.value, line.granularity.value, line.period_end): line for line in values}

        assert lines[("revenue", "year", FY_END)].value == 72.0
        assert lines[("revenue", "quarter", date(2024, 3, 31))].concept == "us-gaap:Revenues"
        derived = lines[("revenue", "quarter", date(2024, 6, 30))]
        assert (derived.value, derived.concept) == (15.0, "derived:us-gaap:Revenues")
        assert lines[("total-assets", "instant", FY_END)].value == 500.0
        assert lines[("revenue", "year", FY_END)].fiscal_year is None

    def test_a_former_filer_only_fills_the_periods_before_the_current_one(
        self, financial_concepts: FinancialConcepts
    ) -> None:
        facts = [
            fact("revenue", "2016-12-31", 50.0, "2016-01-01"),
            fact("revenue", "2014-12-31", 40.0, "2014-01-01", filer="0000000002"),
            fact("revenue", "2017-12-31", 99.0, "2017-01-01", filer="0000000002"),
        ]

        values = FinancialResolver(financial_concepts).resolve(ENTRY, facts)

        assert sorted((line.period_end.year, line.value) for line in values) == [(2014, 40.0), (2016, 50.0)]

    def test_the_google_figures_are_kept_as_stated(self, financial_concepts: FinancialConcepts) -> None:
        google = FinancialFact(
            company="acme",
            source="gfinance",
            metric="rd-expense",
            concept="gfinance:39",
            end="2024-12-31",
            granularity="year",
            value=7.0,
            currency="KRW",
            fiscal_year=2024,
            fiscal_period="FY",
            source_url="u",
        )

        (line,) = FinancialResolver(financial_concepts).resolve(ENTRY, [google])

        assert (line.source, line.granularity, line.fiscal_period, line.value) == (
            FinancialSource.GOOGLE_FINANCE,
            FinancialGranularity.YEAR,
            "FY",
            7.0,
        )


class TestCurrencyRates:
    def test_the_rate_of_the_day_or_a_near_one(self) -> None:
        rates = CurrencyRates(
            [
                FxRate(currency="EUR", day=date(2024, 12, 27), usd_per_unit=1.04),
                FxRate(currency="KRW", day=date(2024, 12, 31), usd_per_unit=0.0007),
            ]
        )

        assert rates.usd_per_unit("USD", FY_END) == 1.0
        assert rates.to_usd(100.0, "EUR", FY_END) == pytest.approx(104.0)
        assert rates.usd_per_unit("EUR", FY_END + timedelta(days=30)) is None
        assert rates.usd_per_unit("JPY", FY_END) is None
        assert rates.convert(1.0, "EUR", "KRW", FY_END) == pytest.approx(1.04 / 0.0007)


class TestFinancialIndicators:
    @pytest.fixture
    def book(self, financial_concepts: FinancialConcepts) -> FinancialBook:
        year, quarter, instant = FinancialGranularity.YEAR, FinancialGranularity.QUARTER, FinancialGranularity.INSTANT
        lines = [
            value(FinancialMetric.REVENUE, FY_END, 1000.0, year),
            value(FinancialMetric.GROSS_PROFIT, FY_END, 600.0, year),
            value(FinancialMetric.OPERATING_INCOME, FY_END, 300.0, year),
            value(FinancialMetric.DEPRECIATION, FY_END, 50.0, year),
            value(FinancialMetric.NET_INCOME, FY_END, 200.0, year),
            value(FinancialMetric.RD_EXPENSE, FY_END, 150.0, year),
            value(FinancialMetric.INCOME_TAX, FY_END, 50.0, year),
            value(FinancialMetric.PRETAX_INCOME, FY_END, 250.0, year),
            value(FinancialMetric.OPERATING_CASH_FLOW, FY_END, 400.0, year),
            value(FinancialMetric.CAPEX, FY_END, 100.0, year),
            value(FinancialMetric.REVENUE, date(2023, 12, 31), 800.0, year),
            value(FinancialMetric.RD_EXPENSE, date(2023, 12, 31), 100.0, year),
            value(FinancialMetric.TOTAL_EQUITY, FY_END, 1200.0, instant),
            value(FinancialMetric.TOTAL_EQUITY, date(2023, 12, 31), 800.0, instant),
            value(FinancialMetric.TOTAL_ASSETS, FY_END, 2000.0, instant),
            value(FinancialMetric.CASH, FY_END, 300.0, instant),
            value(FinancialMetric.SHORT_TERM_INVESTMENTS, FY_END, 100.0, instant),
            value(FinancialMetric.LONG_TERM_DEBT, FY_END, 500.0, instant),
            value(FinancialMetric.CURRENT_DEBT, FY_END, 100.0, instant),
            value(FinancialMetric.CURRENT_ASSETS, FY_END, 900.0, instant),
            value(FinancialMetric.CURRENT_LIABILITIES, FY_END, 450.0, instant),
            value(FinancialMetric.INVENTORY, FY_END, 90.0, instant),
        ]
        for index, amount in enumerate((200.0, 250.0, 260.0, 290.0)):
            lines.append(
                value(FinancialMetric.REVENUE, date(2024, 3, 31) + timedelta(days=91 * index), amount, quarter)
            )
        return FinancialBook(lines, financial_concepts)

    def test_the_indicators_of_a_year_are_computed_by_hand(self, book: FinancialBook) -> None:
        rates = CurrencyRates([FxRate(currency="EUR", day=FY_END, usd_per_unit=1.1)])

        points = keyed(FinancialIndicators(rates).compute("acme", book))
        year = {
            indicator: point
            for (indicator, granularity, end), point in points.items()
            if granularity is FinancialGranularity.YEAR and end == FY_END
        }

        assert year[CompanyIndicator.REVENUE].value_usd == pytest.approx(1100.0)
        assert year[CompanyIndicator.EBITDA].value == 350.0
        assert year[CompanyIndicator.FREE_CASH_FLOW].value == 300.0
        assert year[CompanyIndicator.GROSS_MARGIN].value == pytest.approx(60.0)
        assert year[CompanyIndicator.NET_MARGIN].value == pytest.approx(20.0)
        assert year[CompanyIndicator.RD_INTENSITY].value == pytest.approx(15.0)
        assert year[CompanyIndicator.ROE].value == pytest.approx(20.0)
        assert year[CompanyIndicator.ROA].value == pytest.approx(10.0)
        assert year[CompanyIndicator.ROIC].value == pytest.approx(300 * 0.8 / (1200 + 600 - 400) * 100)
        assert year[CompanyIndicator.CASH].value == 400.0
        assert year[CompanyIndicator.TOTAL_DEBT].value == 600.0
        assert year[CompanyIndicator.NET_DEBT].value == 200.0
        assert year[CompanyIndicator.NET_DEBT_TO_EBITDA].value == pytest.approx(200 / 350)
        assert year[CompanyIndicator.DEBT_TO_EQUITY].value == pytest.approx(0.5)
        assert year[CompanyIndicator.CURRENT_RATIO].value == pytest.approx(2.0)
        assert year[CompanyIndicator.QUICK_RATIO].value == pytest.approx(1.8)
        assert year[CompanyIndicator.RD_RETURN].value == pytest.approx(2.0)
        assert year[CompanyIndicator.RD_INTENSITY].unit is IndicatorUnit.PERCENT

    def test_the_twelve_months_add_four_consecutive_quarters(self, book: FinancialBook) -> None:
        last = date(2024, 3, 31) + timedelta(days=91 * 3)

        points = keyed(FinancialIndicators(CurrencyRates([])).compute("acme", book))

        assert points[(CompanyIndicator.REVENUE, FinancialGranularity.TTM, last)].value == 1000.0
        assert points[(CompanyIndicator.REVENUE, FinancialGranularity.QUARTER, last)].value == 290.0
        assert (CompanyIndicator.REVENUE, FinancialGranularity.TTM, date(2024, 3, 31)) not in points


class TestMarketValue:
    def test_the_capitalisation_follows_the_shares_in_force(self, financial_concepts: FinancialConcepts) -> None:
        lines = [
            value(FinancialMetric.SHARES_OUTSTANDING, date(2024, 1, 15), 100.0, FinancialGranularity.INSTANT),
            value(FinancialMetric.SHARES_OUTSTANDING, date(2024, 7, 15), 120.0, FinancialGranularity.INSTANT),
            value(FinancialMetric.LONG_TERM_DEBT, date(2023, 12, 31), 50.0, FinancialGranularity.INSTANT),
            value(FinancialMetric.CASH, date(2023, 12, 31), 20.0, FinancialGranularity.INSTANT),
        ]
        book = FinancialBook(lines, financial_concepts)
        listing = StockListing(company="acme", symbol="NYSE:ACME", currency="EUR")
        prices = [
            PricePoint(listing="NYSE:ACME", day=day, close=10.0, currency="EUR", source_url="u")
            for day in (date(2024, 1, 5), date(2024, 2, 2), date(2024, 8, 2))
        ]
        entry = CompanyEntry(key="acme", market_cap={"listing": "NYSE:ACME", "shares_per_unit": 2})

        points = MarketValue(CurrencyRates([])).compute(entry, listing, prices, book)
        caps = {point.period_end: point.value for point in points if point.indicator is CompanyIndicator.MARKET_CAP}
        values = {
            point.period_end: point.value for point in points if point.indicator is CompanyIndicator.ENTERPRISE_VALUE
        }

        assert caps == {date(2024, 2, 2): 500.0, date(2024, 8, 2): 600.0}
        assert values == {date(2024, 2, 2): 530.0}

    def test_a_depositary_listing_uses_google_counts_as_they_are(self, financial_concepts: FinancialConcepts) -> None:
        shares = [
            FinancialValue(
                company="acme",
                metric=FinancialMetric.SHARES_OUTSTANDING,
                period_end=date(2024, 1, 15),
                granularity=FinancialGranularity.QUARTER,
                source=FinancialSource.GOOGLE_FINANCE,
                value=30.0,
                concept="gfinance:27",
            ),
            value(FinancialMetric.SHARES_OUTSTANDING, date(2024, 1, 20), 240.0, FinancialGranularity.INSTANT),
        ]
        listing = StockListing(company="acme", symbol="NYSE:ACME", currency="USD")
        prices = [PricePoint(listing="NYSE:ACME", day=date(2024, 2, 2), close=10.0, currency="USD", source_url="u")]
        entry = CompanyEntry(key="acme", market_cap={"listing": "NYSE:ACME", "shares_per_unit": 8})

        (cap,) = MarketValue(CurrencyRates([])).compute(
            entry, listing, prices, FinancialBook(shares, financial_concepts)
        )

        assert cap.value == 300.0


class TestResearchIndicators:
    def test_the_yearly_figures_become_points_of_the_31_december(self) -> None:
        research = ResearchIndicators()

        points = research.from_years(
            {
                ("acme", CompanyIndicator.PATENT_FILINGS, 2020): 12.0,
                ("acme", CompanyIndicator.CITATIONS_PER_PATENT, 2020): 1.5,
            }
        )
        (papers,) = research.from_counts([PaperYearCount(company="acme", year=2021, papers=7, source_url="u")])

        assert {(point.indicator, point.period_end, point.unit) for point in points} == {
            (CompanyIndicator.PATENT_FILINGS, date(2020, 12, 31), IndicatorUnit.COUNT),
            (CompanyIndicator.CITATIONS_PER_PATENT, date(2020, 12, 31), IndicatorUnit.RATIO),
        }
        assert (papers.indicator, papers.value, papers.granularity) == (
            CompanyIndicator.PAPERS,
            7.0,
            FinancialGranularity.YEAR,
        )
