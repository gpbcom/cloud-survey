from __future__ import annotations

from datetime import date
from typing import Dict, List

import pytest
from pydantic import JsonValue

from analytics.companies.companies_collector import CompaniesCollector
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import (
    CompanyFeed,
    CompanyIndicator,
    FinancialGranularity,
    FinancialMetric,
    FinancialSource,
    IndicatorUnit,
    PatentWindowStatus,
)
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
from models.markets.markets_catalog import MarketsCatalog
from storage.storage import Storage

pytestmark = pytest.mark.db


def record(number: str, priority: str, grant: str = "", company: str = "nvidia") -> PatentRecord:
    return PatentRecord(
        company=company,
        query="Nvidia Corp",
        publication_number=number,
        title=f"Invention {number}",
        assignee="Nvidia Corporation",
        inventors=["Minwoo Park", "Jan Kautz"],
        priority_date=priority,
        grant_date=grant,
        source_url=f"https://patents.google.com/patent/{number}/en",
    )


def edgar(metric: str, start: str, end: str, value: float, concept: str) -> Dict[str, JsonValue]:
    return {
        "kind": "financial",
        "company": "nvidia",
        "source": "edgar",
        "metric": metric,
        "concept": concept,
        "filer": "0001045810",
        "start": start,
        "end": end,
        "value": value,
        "currency": "USD",
        "form": "10-K",
        "filed": "2025-02-26",
        "source_url": "u",
    }


class TestFinancialsAndIndicators:
    async def test_the_lines_are_upserted_by_period_and_source(self, storage: Storage) -> None:
        line = FinancialValue(
            company="nvidia",
            metric=FinancialMetric.REVENUE,
            period_end=date(2025, 1, 26),
            granularity=FinancialGranularity.YEAR,
            source=FinancialSource.EDGAR,
            value=130497000000,
            currency="USD",
            concept="us-gaap:Revenues",
        )

        await storage.financials.upsert([line, line.model_copy(update={"source": FinancialSource.GOOGLE_FINANCE})])
        await storage.financials.upsert([line.model_copy(update={"value": 1.0})])

        stored = await storage.financials.list(["nvidia"])
        assert sorted((item.source.value, item.value) for item in stored) == [
            ("edgar", 1.0),
            ("gfinance", 130497000000),
        ]

    async def test_the_sec_lines_of_a_company_are_replaced_whole(self, storage: Storage) -> None:
        def line(year: int, source: FinancialSource) -> FinancialValue:
            return FinancialValue(
                company="hp",
                metric=FinancialMetric.SHARES_OUTSTANDING,
                period_end=date(year, 8, 27),
                granularity=FinancialGranularity.INSTANT,
                source=source,
                value=1.0,
                concept="dei:EntityCommonStockSharesOutstanding",
            )

        await storage.financials.upsert([line(2025, FinancialSource.EDGAR), line(2025, FinancialSource.GOOGLE_FINANCE)])
        await storage.financials.replace("hp", FinancialSource.EDGAR, [line(2026, FinancialSource.EDGAR)])
        await storage.financials.replace("hp", FinancialSource.EDGAR, [])

        stored = await storage.financials.list(["hp"])
        assert sorted((item.source.value, item.period_end.year) for item in stored) == [
            ("edgar", 2026),
            ("gfinance", 2025),
        ]

    async def test_the_series_are_replaced_read_and_covered(self, storage: Storage) -> None:
        def point(end: date, value: float) -> IndicatorValue:
            return IndicatorValue(
                company="nvidia",
                indicator=CompanyIndicator.RD_INTENSITY,
                period_end=end,
                granularity=FinancialGranularity.YEAR,
                value=value,
                unit=IndicatorUnit.PERCENT,
                inputs="rd-expense / revenue",
            )

        await storage.indicators.replace(
            ["nvidia"],
            [CompanyIndicator.RD_INTENSITY],
            [point(date(2023, 1, 29), 27.2), point(date(2024, 1, 28), 14.2)],
        )
        await storage.indicators.replace(["nvidia"], [CompanyIndicator.RD_INTENSITY], [point(date(2025, 1, 26), 9.9)])

        series = await storage.indicators.series("nvidia", CompanyIndicator.RD_INTENSITY)
        coverage = await storage.indicators.coverage()
        assert [(item.period_end, item.value) for item in series] == [(date(2025, 1, 26), 9.9)]
        assert coverage[("nvidia", "rd-intensity", "year")] == (date(2025, 1, 26), date(2025, 1, 26), 1)


class TestPatents:
    async def test_the_publications_wait_for_their_pages_granted_ones_first(self, storage: Storage) -> None:
        await storage.patents.upsert_records(
            [record("US20230214654A1", "2019-12-03"), record("US11000000B2", "2018-01-31", "2021-05-11")]
        )

        assert await storage.patents.queue(["nvidia"]) == ["US11000000B2", "US20230214654A1"]
        assert await storage.patents.queue(["tsmc"]) == []

    async def test_a_page_replaces_the_details_and_leaves_the_queue(self, storage: Storage) -> None:
        await storage.patents.upsert_records([record("US11000000B2", "2018-01-31", "2021-05-11")])
        detail = PatentDetail(
            publication_number="US11000000B2",
            family_id="123",
            inventors=["Jonathan White"],
            assignees_original=["Nvidia Corp"],
            cpc=["G06F9/50", "G06N3/08"],
            citations=[
                {"publication_number": "US5093563A", "kind": "cites", "examiner": True},
                {"publication_number": "US11353558B2", "kind": "cited-by"},
                {"publication_number": "US11400000B2", "kind": "cited-by"},
            ],
            source_url="u",
        )

        await storage.patents.upsert_details([detail])

        assert await storage.patents.queue(["nvidia"]) == []
        yearly = await storage.patents.yearly(["nvidia"])
        assert yearly[("nvidia", CompanyIndicator.PATENT_FILINGS, 2018)] == 1.0
        assert yearly[("nvidia", CompanyIndicator.PATENT_GRANTS, 2021)] == 1.0
        assert yearly[("nvidia", CompanyIndicator.PATENT_CITATIONS, 2018)] == 2.0
        assert yearly[("nvidia", CompanyIndicator.CITATIONS_PER_PATENT, 2018)] == 2.0
        inventors, assignees = await storage.patent_profiles.rebuild()
        assert (inventors, assignees) == (1, 1)

    async def test_the_windows_are_upserted_and_read_back(self, storage: Storage) -> None:
        window = PatentWindow(
            company="nvidia", query="Nvidia Corp", after="2019-01-01", before="2019-02-01", expected=3, status="split"
        )

        await storage.patents.upsert_windows([window])
        await storage.patents.upsert_windows(
            [window.model_copy(update={"status": PatentWindowStatus.COMPLETE, "fetched": 3})]
        )

        (stored,) = await storage.patents.read_windows(["nvidia"])
        assert (stored.status, stored.fetched, stored.country) == (PatentWindowStatus.COMPLETE, 3, None)


class TestPapers:
    async def test_the_papers_and_researchers_are_written_and_summed_per_year(self, storage: Storage) -> None:
        paper = PaperRecord(
            openalex_id="W1001",
            company="nvidia",
            publication_year=2019,
            cited_by_count=40,
            fwci=2.0,
            authorships=[{"position": 0, "author_id": "A5001", "name": "Author 1", "company_affiliated": True}],
            source_url="u",
        )

        await storage.papers.upsert_papers(
            [paper, paper.model_copy(update={"openalex_id": "W1002", "cited_by_count": 10, "fwci": 1.0})]
        )
        await storage.papers.upsert_researchers(
            [ResearcherRecord(author_id="A5001", company="nvidia", name="Author 1", source_url="u")]
        )

        yearly = await storage.papers.yearly(["nvidia"])
        assert yearly[("nvidia", CompanyIndicator.PAPER_CITATIONS, 2019)] == 50.0
        assert yearly[("nvidia", CompanyIndicator.PAPER_FWCI, 2019)] == pytest.approx(1.5)


class TestCompaniesCollector:
    async def test_the_statement_facts_become_lines_then_indicator_series(
        self,
        storage: Storage,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        collector = CompaniesCollector(companies_catalog, financial_concepts, markets_catalog, storage, ["nvidia"])
        items: List[Dict[str, JsonValue]] = [
            edgar("revenue", "2024-01-29", "2025-01-26", 130497000000, "us-gaap:Revenues"),
            edgar("rd-expense", "2024-01-29", "2025-01-26", 12914000000, "us-gaap:ResearchAndDevelopmentExpense"),
            {"kind": "unknown"},
        ]

        await collector.write(CompanyFeed.EDGAR, items)
        await collector.finish([CompanyFeed.EDGAR])

        intensity = await storage.indicators.series("nvidia", CompanyIndicator.RD_INTENSITY, FinancialGranularity.YEAR)
        assert [round(point.value, 2) for point in intensity] == [9.9]

    async def test_the_homonyms_of_a_company_are_left_out(
        self,
        storage: Storage,
        companies_catalog: CompaniesCatalog,
        financial_concepts: FinancialConcepts,
        markets_catalog: MarketsCatalog,
    ) -> None:
        entry = companies_catalog.entry("nvidia")
        assert entry is not None
        assert entry.patents is not None
        patents = entry.patents.model_copy(update={"exclude": ["Pty"]})
        catalog = companies_catalog.model_copy(update={"companies": [entry.model_copy(update={"patents": patents})]})
        collector = CompaniesCollector(catalog, financial_concepts, markets_catalog, storage, ["nvidia"])
        homonym = record("AU2019100000A4", "2019-01-01").model_copy(update={"assignee": "Nvidia Pty Ltd"})
        items = [
            {"kind": "patent", **item.model_dump(mode="json")}
            for item in (record("US11000000B2", "2018-01-31"), homonym)
        ]

        await collector.write(CompanyFeed.GOOGLE_PATENTS, items)

        assert await storage.patents.queue(["nvidia"]) == ["US11000000B2"]
        assert collector.rejected == 1


class TestResearchCoverage:
    async def test_the_patents_coverage_counts_the_pages_and_the_windows(self, storage: Storage) -> None:
        await storage.patents.upsert_records(
            [record("US11000000B2", "2018-01-31", "2021-05-11"), record("US11000001B2", "2019-01-31")]
        )
        await storage.patents.upsert_details([PatentDetail(publication_number="US11000000B2", source_url="u")])
        window = PatentWindow(
            company="nvidia", query="Nvidia Corp", after="2019-01-01", before="2019-02-01", expected=3
        )
        await storage.patents.upsert_windows(
            [
                window.model_copy(update={"status": PatentWindowStatus.COMPLETE}),
                window.model_copy(update={"after": date(2019, 2, 1), "before": date(2019, 3, 1)}),
            ]
        )

        coverage = await storage.patents.coverage(["nvidia"])

        assert coverage == {"nvidia": (2, 1, 1, 1)}
        assert await storage.patents.coverage(["amd"]) == {}

    async def test_the_papers_coverage_counts_the_papers_and_the_researchers(self, storage: Storage) -> None:
        paper = PaperRecord(openalex_id="W1001", company="nvidia", publication_year=2019, source_url="u")
        await storage.papers.upsert_papers([paper, paper.model_copy(update={"openalex_id": "W1002"})])
        await storage.papers.upsert_researchers(
            [ResearcherRecord(author_id="A5001", company="amd", name="Author 1", source_url="u")]
        )

        coverage = await storage.papers.coverage()

        assert coverage == {"nvidia": (2, 0), "amd": (0, 1)}
