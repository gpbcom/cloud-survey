from __future__ import annotations

from datetime import date

import pytest

from analytics.companies.companies_collector import CompaniesCollector
from analytics.companies.exception import CompaniesCollectorError
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyIndicator, FinancialGranularity, FinancialMetric, FinancialSource
from models.companies.figures.reported_figures import ReportedFigures
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
from models.markets.markets_catalog import MarketsCatalog
from storage.storage import Storage

pytestmark = pytest.mark.db

YEAR = FinancialGranularity.YEAR


def point(company: str, end: date, amount: float) -> IndicatorValue:
    return IndicatorValue(
        company=company,
        indicator=CompanyIndicator.REVENUE,
        period_end=end,
        granularity=YEAR,
        value=amount,
        unit="currency",
        currency="USD",
        inputs="revenue",
    )


def line(source: FinancialSource, url: str, note: str = "") -> FinancialValue:
    return FinancialValue(
        company="dec",
        metric=FinancialMetric.REVENUE,
        period_end=date(1997, 6, 28),
        granularity=YEAR,
        source=source,
        value=13046.8e6,
        currency="USD",
        concept="x",
        source_url=url,
        note=note or None,
    )


class TestFinancialReads:
    async def test_the_series_of_several_companies_and_their_latest_points(self, storage: Storage) -> None:
        points = [
            point("dec", date(1996, 6, 29), 14.5),
            point("dec", date(1997, 6, 28), 13.0),
            point("sun", date(1997, 6, 30), 8.6),
        ]
        await storage.indicators.replace(["dec", "sun"], [CompanyIndicator.REVENUE], points)

        series = await storage.indicators.list(["dec", "sun"], CompanyIndicator.REVENUE, [YEAR])
        latest = await storage.indicators.latest(["dec", "sun"], [CompanyIndicator.REVENUE])

        assert [(item.company, item.period_end.year) for item in series] == [
            ("dec", 1996),
            ("dec", 1997),
            ("sun", 1997),
        ]
        assert sorted((item.company, item.value) for item in latest) == [("dec", 13.0), ("sun", 8.6)]
        assert await storage.indicators.list([], CompanyIndicator.REVENUE) == []

    async def test_the_note_is_kept_and_the_filed_document_is_preferred(self, storage: Storage) -> None:
        await storage.financials.upsert(
            [
                line(FinancialSource.REPORTED, "https://example.com/annual-report-1997.pdf", "Annual report."),
                line(FinancialSource.EDGAR_FDS, "https://www.sec.gov/Archives/edgar/data/28887/x.txt"),
            ]
        )

        stored = await storage.financials.list(["dec"])
        documents = await storage.financials.documents(["dec"])

        assert {value.source: value.note for value in stored}[FinancialSource.REPORTED] == "Annual report."
        assert documents[("dec", "revenue", date(1997, 6, 28))][0] is FinancialSource.EDGAR_FDS

    async def test_the_researched_figures_are_written_then_deleted_when_removed(
        self,
        storage: Storage,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        figures = ReportedFigures.model_validate(
            {
                "companies": [
                    {
                        "company": "dec",
                        "currency": "USD",
                        "fiscal_year_end": "06-30",
                        "years": [
                            {
                                "fiscal_year": 1985,
                                "basis": "annual-report",
                                "source": "https://example.com/dec-1985.pdf",
                                "figures": {"revenue": 6686.3, "employees": 89000},
                            }
                        ],
                    }
                ]
            }
        )
        collector = CompaniesCollector(companies_catalog, financial_concepts, markets_catalog, storage, ["dec"])

        written = await collector.write_reported(figures)
        with pytest.raises(CompaniesCollectorError):
            await CompaniesCollector(
                companies_catalog, financial_concepts, markets_catalog, storage, ["dec"]
            ).write_reported(ReportedFigures())
        kept = [value for value in await storage.financials.list(["dec"]) if value.source is FinancialSource.REPORTED]
        others = ReportedFigures.model_validate({"companies": [{"company": "ibm", "currency": "USD"}]})
        removed = await CompaniesCollector(
            companies_catalog, financial_concepts, markets_catalog, storage, ["dec"]
        ).write_reported(others)

        assert written == 2
        assert collector.crawled == {"dec"}
        assert len(kept) == 2, "empty figures never delete the stored ones"
        assert removed == 0
        assert [
            value for value in await storage.financials.list(["dec"]) if value.source is FinancialSource.REPORTED
        ] == []
