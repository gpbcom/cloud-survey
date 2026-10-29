from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional
from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from gui.analysis.financials.financials_panel import CompanyFinancialsPanel
from gui.theme import Theme
from models.companies.enums import (
    CompanyIndicator,
    FinancialGranularity,
    FinancialSource,
    IndicatorFamily,
    IndicatorUnit,
)
from models.companies.values.indicator_value import IndicatorValue
from storage.repositories.companies.financial_repository import Document, DocumentKey

YEAR = FinancialGranularity.YEAR


def panel(qtbot: QtBot) -> CompanyFinancialsPanel:
    built = CompanyFinancialsPanel(Theme(), MagicMock())
    for body in (built.chart_body, built.table_body):
        qtbot.addWidget(body)
        body.resize(1200, 480)
        body.show()
    return built


def point(
    company: str,
    year: int,
    value: float,
    currency: str = "USD",
    usd: Optional[float] = None,
    inputs: str = "edgar:us-gaap:NetIncomeLoss",
    indicator: CompanyIndicator = CompanyIndicator.NET_INCOME,
) -> IndicatorValue:
    return IndicatorValue(
        company=company,
        indicator=indicator,
        period_end=date(year, 12, 31),
        granularity=YEAR,
        value=value,
        unit=IndicatorUnit.CURRENCY,
        currency=currency,
        value_usd=usd if usd is not None else value,
        inputs=inputs,
    )


def draw(built: CompanyFinancialsPanel, series: List[IndicatorValue], in_usd: bool = False) -> None:
    built.generation = 1
    query = (("ibm", "sap"), CompanyIndicator.NET_INCOME, YEAR, in_usd)
    built._on_read(1, query, (series, series, {}))


class TestCompanyFinancialsPanel:
    def test_the_indicator_menu_lists_every_family_in_order(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        menu = built.controls.indicator_button.menu()
        assert menu is not None

        sections = [action.text() for action in menu.actions() if action.isSeparator()]
        checkable = [str(action.data()) for action in menu.actions() if action.isCheckable()]

        assert sections[:3] == ["Size and value", "Profit", "Liquidity"]
        assert len(checkable) == len(CompanyIndicator)
        assert built.controls.indicator() is CompanyIndicator.NET_INCOME
        assert "Net income" in built.controls.indicator_button.text()

    def test_a_line_per_company_and_currency_never_bridging_a_missing_year(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        series = [point("ibm", 2018, 8.7e9), point("ibm", 2019, 9.4e9), point("ibm", 2021, 5.7e9)]
        series += [point("sap", 1998, 1.0e9, "DEM", 0.6e9), point("sap", 2002, 0.5e9, "EUR", 0.47e9)]

        draw(built, series)

        assert sorted(line.label for line in built.chart.values) == ["IBM", "SAP (DEM)", "SAP (EUR)"]
        assert built.chart._gap_days() == 400
        assert built.chart.unit == ""

    def test_estimates_are_drawn_apart_dashed(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        series = [point("ibm", 2018, 8.7e9), point("ibm", 2019, 9.0e9, inputs="revenue [reported:estimate]")]

        draw(built, series)
        estimates = [line for line in built.chart.values if line.dashed]

        assert len(built.chart.values) == 2
        assert [len(line.points) for line in estimates] == [1]
        assert estimates[0].label.endswith("estimates")

    def test_the_us_dollar_switch_draws_the_converted_amounts(self, qtbot: QtBot) -> None:
        built = panel(qtbot)

        draw(built, [point("sap", 2002, 0.5e9, "EUR", 0.47e9), point("sap", 2003, 1.0e9, "EUR", 1.13e9)], True)

        assert [value for _, value in built.chart.values[0].points] == [0.47e9, 1.13e9]
        assert built.chart.unit == "USD"

    def test_a_late_answer_is_dropped(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        built.generation = 2

        built._on_read(1, (("ibm",), CompanyIndicator.NET_INCOME, YEAR, False), ([point("ibm", 2018, 1.0)], [], {}))

        assert built.chart.values == []

    def test_the_latest_values_name_their_basis_and_source(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        revenue = point("ibm", 1985, 50.0e9, inputs="reported:annual-report", indicator=CompanyIndicator.REVENUE)
        documents: Dict[DocumentKey, Document] = {
            ("ibm", "revenue", date(1985, 12, 31)): (FinancialSource.REPORTED, "https://example.com/ibm-1985.pdf", None)
        }
        built.generation = 1

        built._on_read(1, (("ibm",), CompanyIndicator.REVENUE, YEAR, False), ([revenue], [revenue], documents))
        row = built.table.model_.rows[0]

        assert row[0] == "IBM"
        assert row[3] == "50.00 bn"
        assert row[6] == "researched"
        assert built.table.model_.source(0) == "https://example.com/ibm-1985.pdf"

    def test_no_data_says_what_to_crawl(self, qtbot: QtBot) -> None:
        built = panel(qtbot)
        built.generation = 1

        built._on_read(1, (("ibm",), CompanyIndicator.PIOTROSKI_F, YEAR, False), ([], [], {}))

        assert "Companies menu" in built.chart.message
        assert built._family(CompanyIndicator.PIOTROSKI_F) is IndicatorFamily.SCORES
