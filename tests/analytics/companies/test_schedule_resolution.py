from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from analytics.companies.financials.financial_resolver import FinancialResolver
from models.companies.catalog.company_entry import CompanyEntry
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import FinancialSource
from models.companies.facts.financial_fact import FinancialFact
from models.companies.values.financial_value import FinancialValue

ENTRY = CompanyEntry(key="dec", sec_ciks=["28887"])


def schedule(
    tag: str,
    metric: str,
    end: str,
    value: float,
    start: Optional[str] = None,
    period: str = "FY",
    filed: str = "1997-09-17",
    url: str = "https://www.sec.gov/Archives/edgar/data/28887/0000950135-97-003873.txt",
) -> FinancialFact:
    return FinancialFact(
        company="dec",
        source="edgar-fds",
        metric=metric,
        concept=f"fds:{tag}",
        filer="0000028887",
        start=start,
        end=end,
        value=value,
        currency="USD",
        form="10-K",
        fiscal_period=period,
        filed=filed,
        source_url=url,
    )


def lines(facts: List[FinancialFact]) -> Dict[Tuple[str, str, date], FinancialValue]:
    values = resolver().resolve(ENTRY, facts)
    return {(line.metric.value, line.granularity.value, line.period_end): line for line in values}


def resolver() -> FinancialResolver:
    return FinancialResolver(FinancialConcepts.model_validate(CONCEPTS))


CONCEPTS = {
    "concepts": [
        {"metric": "revenue", "nature": "flow", "concepts": ["us-gaap:Revenues"]},
        {"metric": "total-equity", "nature": "balance", "concepts": ["us-gaap:StockholdersEquity"]},
        {"metric": "net-income", "nature": "flow", "concepts": ["us-gaap:NetIncomeLoss"]},
    ],
    "fds": {
        "tags": [
            {"tag": "TOTAL-REVENUES", "metric": "revenue"},
            {"tag": "SALES", "metric": "revenue", "rank": 1},
            {"tag": "NET-INCOME", "metric": "net-income"},
            {"tag": "COMMON", "metric": "total-equity", "sum": True},
            {"tag": "OTHER-SE", "metric": "total-equity", "sum": True},
            {"tag": "PREFERRED", "metric": "total-equity", "sum": True},
        ]
    },
}


class TestScheduleResolution:
    def test_the_equity_is_the_sum_of_its_tags_in_one_schedule(self) -> None:
        facts = [
            schedule("COMMON", "total-equity", "1997-06-28", 130.0),
            schedule("OTHER-SE", "total-equity", "1997-06-28", 4400.0),
            schedule("PREFERRED", "total-equity", "1997-06-28", 0.0),
        ]

        equity = lines(facts)[("total-equity", "instant", date(1997, 6, 28))]

        assert (equity.value, equity.source, equity.concept) == (4530.0, FinancialSource.EDGAR_FDS, "fds:total-equity")

    def test_a_year_without_stated_start_starts_twelve_months_before_its_end(self) -> None:
        resolved = lines([schedule("TOTAL-REVENUES", "revenue", "1997-06-28", 13046.8)])

        assert resolved[("revenue", "year", date(1997, 6, 28))].value == 13046.8

    def test_the_fourth_quarter_is_derived_from_the_year_and_nine_months(self) -> None:
        facts = [
            schedule("TOTAL-REVENUES", "revenue", "1997-06-28", 13046.8, start="1996-06-30"),
            schedule("TOTAL-REVENUES", "revenue", "1997-03-29", 9700.0, start="1996-06-30", period="9M"),
        ]

        fourth = lines(facts)[("revenue", "quarter", date(1997, 6, 28))]
        assert round(fourth.value, 1) == 3346.8
        assert fourth.concept == "derived:fds:TOTAL-REVENUES"

    def test_the_latest_filing_and_the_preferred_tag_win(self) -> None:
        later = "https://www.sec.gov/Archives/edgar/data/28887/0000950135-98-000001.txt"
        facts = [
            schedule("TOTAL-REVENUES", "revenue", "1997-06-28", 13000.0, start="1996-06-30"),
            schedule(
                "TOTAL-REVENUES", "revenue", "1997-06-28", 13046.8, start="1996-06-30", filed="1998-09-01", url=later
            ),
            schedule("SALES", "revenue", "1997-06-28", 9000.0, start="1996-06-30"),
        ]

        assert lines(facts)[("revenue", "year", date(1997, 6, 28))].value == 13046.8

    def test_the_schedules_and_the_xbrl_facts_stay_apart(self) -> None:
        xbrl = FinancialFact(
            company="dec",
            source="edgar",
            metric="revenue",
            concept="us-gaap:Revenues",
            filer="0000028887",
            start="2009-01-01",
            end="2009-12-31",
            value=1.0,
            currency="USD",
            form="10-K",
            filed="2010-02-01",
            source_url="u",
        )

        values = resolver().resolve(
            ENTRY, [xbrl, schedule("NET-INCOME", "net-income", "1997-06-28", 141.0, start="1996-06-30")]
        )

        assert sorted(value.source.value for value in values) == ["edgar", "edgar-fds"]
