from __future__ import annotations

from typing import Dict, List, Tuple, Type

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from models.companies.catalog.company_entry import CompanyEntry
from models.companies.catalog.market_cap_source import MarketCapSource
from models.companies.catalog.openalex_affiliation import OpenAlexAffiliation
from models.companies.catalog.patent_search import PatentSearch
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concept import FinancialConcept
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.concepts.statement_layout import StatementLayout
from models.companies.concepts.statement_slot import StatementSlot
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.companies.facts.financial_fact import FinancialFact
from models.companies.papers.paper_authorship import PaperAuthorship
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_citation import PatentCitation
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.companies.settings.openalex_settings import OpenAlexSettings
from models.companies.settings.patents_settings import PatentsSettings
from models.companies.values.financial_value import FinancialValue
from models.companies.values.indicator_value import IndicatorValue
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
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json"

# A valid payload of every model.
VALID: Dict[Type[BaseModel], Dict[str, JsonValue]] = {
    PatentSearch: {
        "assignees": ["Nvidia Corp", "Mellanox Technologies"],
        "since": "1993-01-01",
        "exclude": ["^Nvidia Pty"],
    },
    OpenAlexAffiliation: {"institutions": ["https://openalex.org/I4210127875"]},
    MarketCapSource: {"listing": "nyse:baba", "shares_per_unit": 8, "since": "2019-07-30"},
    CompanyEntry: {
        "key": "nvidia",
        "sec_ciks": ["1045810", 1045810],
        "market_cap": {"listing": "NASDAQ:NVDA"},
        "patents": {"assignees": ["Nvidia Corp"], "since": "1993-01-01"},
        "openalex": {"institutions": ["I4210127875"]},
        "statements": "industrial",
    },
    FinancialConcept: {"metric": "revenue", "nature": "flow", "concepts": ["us-gaap:Revenues", "ifrs-full:Revenue"]},
    StatementSlot: {"metric": "capex", "slot": 103, "negate": True},
    StatementLayout: {
        "width": 106,
        "currency_slot": 16,
        "period_end_slot": 17,
        "quote_market_cap_slot": 16,
        "quote_currency_slot": 12,
        "slots": [{"metric": "revenue", "slot": 0}],
    },
    FinancialConcepts: {
        "concepts": [{"metric": "revenue", "nature": "flow", "concepts": ["us-gaap:Revenues"]}],
        "google_finance": {"slots": [{"metric": "revenue", "slot": 0}]},
        "fds": {"tags": [{"tag": "TOTAL-REVENUES", "metric": "revenue"}]},
    },
    PatentsSettings: {
        "window_cap": 900,
        "refresh_years": 3,
        "delay_seconds": 6,
        "max_blocks": 1,
        "page_budget": 2000,
        "page_budget_env": "CRAWLER_PATENT_PAGES",
        "split_countries": ["us", "CN"],
    },
    OpenAlexSettings: {
        "key_envs": ["OPENALEX_API_KEY_1"],
        "mailto_env": "CRAWLER_OPENALEX_MAILTO",
        "per_page": 200,
        "author_batch": 50,
        "max_works": 0,
        "delay_seconds": 0.2,
    },
    CompaniesCatalog: {
        "sec_user_agent_env": "CRAWLER_SEC_USER_AGENT",
        "patents": None,
        "openalex": {"key_envs": []},
        "companies": [{"key": "nvidia"}, {"key": "tsmc"}],
    },
    FinancialFact: {
        "company": "nvidia",
        "source": "edgar",
        "metric": "revenue",
        "concept": "us-gaap:Revenues",
        "filer": "0001045810",
        "start": "2024-01-29",
        "end": "2025-01-26",
        "granularity": None,
        "value": 130497000000,
        "currency": "usd",
        "form": "10-k",
        "fiscal_year": 2024,
        "fiscal_period": "fy",
        "filed": "2025-02-26",
        "source_url": URL,
    },
    PatentCitation: {
        "publication_number": "US-5093563-A",
        "kind": "cites",
        "examiner": True,
        "priority_date": "1987-02-05",
        "publication_date": "1992-03-03",
        "assignee": "Hughes Aircraft Company",
        "title": "Electronically phased detector array",
    },
    PatentRecord: {
        "company": "nvidia",
        "query": "Nvidia Corp",
        "publication_number": "US20230214654A1",
        "title": "Landmark detection using curve fitting",
        "assignee": "Nvidia Corporation",
        "inventors": "Minwoo Park, Yilin YANG, Minwoo Park",
        "priority_date": "2019-12-03",
        "filing_date": "2023-02-27",
        "publication_date": "2023-07-06",
        "grant_date": "",
        "source_url": "https://patents.google.com/patent/US20230214654A1/en",
    },
    PatentDetail: {
        "publication_number": "US10000000B2",
        "family_id": 54766427,
        "title": "Coherent LADAR using intra-pixel quadrature detection",
        "abstract": "  A frequency modulated (coherent) laser detection and ranging system.  ",
        "assignees_original": ["Raytheon Co"],
        "assignees_current": ["Raytheon Co"],
        "inventors": ["Joseph Marron"],
        "cpc": ["G01S 7/4914", "G01S17/32"],
        "claims": 20,
        "priority_date": "2015-03-10",
        "filing_date": "2015-03-10",
        "publication_date": "2018-06-19",
        "grant_date": "2018-06-19",
        "citations": [{"publication_number": "US5093563A", "kind": "cites"}],
        "source_url": "https://patents.google.com/patent/US10000000B2/en",
    },
    PatentWindow: {
        "company": "nvidia",
        "query": "Nvidia Corp",
        "after": "2020-01-01",
        "before": "2020-07-01",
        "country": "us",
        "expected": 812,
        "fetched": 812,
        "status": "complete",
    },
    PaperAuthorship: {
        "position": 0,
        "author_id": "https://openalex.org/A5023215207",
        "name": "Animashree Anandkumar",
        "orcid": "https://orcid.org/0000-0002-6974-6797",
        "institutions": ["https://openalex.org/I4210127875"],
        "company_affiliated": True,
    },
    PaperRecord: {
        "openalex_id": "https://openalex.org/W2904367110",
        "company": "nvidia",
        "doi": "https://doi.org/10.1109/CVPR.2019.00453",
        "title": "A Style-Based Generator Architecture for Generative Adversarial Networks",
        "publication_year": 2019,
        "publication_date": "2019-06-01",
        "type": "conference-paper",
        "venue": "CVPR",
        "language": "en",
        "cited_by_count": None,
        "fwci": 120.5,
        "is_oa": None,
        "topic": "Generative Adversarial Networks",
        "authorships": [{"position": 0, "name": "Tero Karras"}],
        "source_url": "https://api.openalex.org/works",
    },
    ResearcherRecord: {
        "author_id": "A5023215207",
        "company": "nvidia",
        "name": "Animashree Anandkumar",
        "orcid": None,
        "works_count": 656,
        "cited_by_count": None,
        "h_index": 75,
        "institution": None,
        "source_url": "https://api.openalex.org/authors",
    },
    PaperYearCount: {
        "company": "nvidia",
        "year": "2026",
        "papers": 1223,
        "source_url": "https://api.openalex.org/works",
    },
    FinancialValue: {
        "company": "nvidia",
        "metric": "revenue",
        "period_end": "2025-01-26",
        "granularity": "year",
        "source": "edgar",
        "value": 130497000000,
        "currency": "USD",
        "concept": "us-gaap:Revenues",
        "form": "10-K",
        "fiscal_year": None,
        "fiscal_period": None,
        "filed": "2025-02-26",
        "source_url": URL,
        "note": "Fiscal 2025 annual report.",
    },
    IndicatorValue: {
        "company": "nvidia",
        "indicator": "rd-intensity",
        "period_end": "2025-01-26",
        "granularity": "ttm",
        "value": 9.9,
        "unit": "percent",
        "currency": None,
        "value_usd": None,
        "inputs": "rd-expense / revenue",
    },
}

# One rejected value per field of every model, with the error it must raise.
INVALID: List[Tuple[Type[BaseModel], str, JsonValue, Type[ValueError]]] = [
    (PatentSearch, "assignees", "Nvidia", LIST),
    (PatentSearch, "since", "soon", DAY),
    (PatentSearch, "exclude", ["("], FORMAT),
    (OpenAlexAffiliation, "institutions", ["X12"], FORMAT),
    (OpenAlexAffiliation, "include_affiliations", ["Opera ("], FORMAT),
    (OpenAlexAffiliation, "exclude_affiliations", ["[IPAM"], FORMAT),
    (MarketCapSource, "listing", "BABA", FORMAT),
    (MarketCapSource, "shares_per_unit", 0, NUMBER),
    (MarketCapSource, "since", "later", DAY),
    (CompanyEntry, "key", "Nvidia Corp", FORMAT),
    (CompanyEntry, "sec_ciks", ["12345678901"], TEXT),
    (CompanyEntry, "market_cap", "NASDAQ:NVDA", FORMAT),
    (CompanyEntry, "patents", ["Nvidia"], FORMAT),
    (CompanyEntry, "openalex", "I4210127875", FORMAT),
    (CompanyEntry, "statements", "insurer", CHOICE),
    (FinancialConcept, "metric", "sales", CHOICE),
    (FinancialConcept, "nature", "stock", CHOICE),
    (FinancialConcept, "concepts", ["Revenues"], FORMAT),
    (FinancialConcept, "negate", "no", FLAG),
    (StatementSlot, "metric", "sales", CHOICE),
    (StatementSlot, "slot", 3.5, NUMBER),
    (StatementSlot, "negate", 1, FLAG),
    (StatementLayout, "width", -1, NUMBER),
    (StatementLayout, "currency_slot", 2000, NUMBER),
    (StatementLayout, "period_end_slot", "x", NUMBER),
    (StatementLayout, "quote_market_cap_slot", 1.5, NUMBER),
    (StatementLayout, "quote_currency_slot", None, NUMBER),
    (StatementLayout, "slots", [{"metric": "revenue", "slot": 0}, {"metric": "revenue", "slot": 1}], DUPLICATE),
    (
        FinancialConcepts,
        "concepts",
        [
            {"metric": "revenue", "nature": "flow", "concepts": ["us-gaap:Revenues"]},
            {"metric": "rd-expense", "nature": "flow", "concepts": ["us-gaap:Revenues"]},
        ],
        DUPLICATE,
    ),
    (FinancialConcepts, "google_finance", "slots", FORMAT),
    (FinancialConcepts, "fds", "tags", FORMAT),
    (PatentsSettings, "window_cap", -1, NUMBER),
    (PatentsSettings, "refresh_years", 1.5, NUMBER),
    (PatentsSettings, "delay_seconds", 601, NUMBER),
    (PatentsSettings, "max_blocks", "x", NUMBER),
    (PatentsSettings, "page_budget", -5, NUMBER),
    (PatentsSettings, "page_budget_env", "lower", FORMAT),
    (PatentsSettings, "split_countries", ["USA"], TEXT),
    (PatentsSettings, "resume_minutes", "x", NUMBER),
    (PatentsSettings, "browser", "yes", FLAG),
    (OpenAlexSettings, "key_envs", ["bad name"], FORMAT),
    (OpenAlexSettings, "mailto_env", 3, TEXT),
    (OpenAlexSettings, "per_page", -1, NUMBER),
    (OpenAlexSettings, "author_batch", 1.5, NUMBER),
    (OpenAlexSettings, "max_works", "x", NUMBER),
    (OpenAlexSettings, "delay_seconds", 61, NUMBER),
    (OpenAlexSettings, "min_affiliation_years", "x", NUMBER),
    (OpenAlexSettings, "min_company_papers", 1.5, NUMBER),
    (CompaniesCatalog, "sec_user_agent_env", "x y", FORMAT),
    (CompaniesCatalog, "patents", "x", FORMAT),
    (CompaniesCatalog, "openalex", 3, FORMAT),
    (CompaniesCatalog, "companies", [{"key": "nvidia"}, {"key": "nvidia"}], DUPLICATE),
    (FinancialFact, "company", "NVIDIA", FORMAT),
    (FinancialFact, "source", "sec", CHOICE),
    (FinancialFact, "metric", "sales", CHOICE),
    (FinancialFact, "concept", "", TEXT),
    (FinancialFact, "filer", "123", FORMAT),
    (FinancialFact, "start", "start", DAY),
    (FinancialFact, "end", "2024-01-01", FORMAT),
    (FinancialFact, "granularity", "month", CHOICE),
    (FinancialFact, "value", "abc", NUMBER),
    (FinancialFact, "currency", "us", FORMAT),
    (FinancialFact, "form", "x" * 13, TEXT),
    (FinancialFact, "fiscal_year", 1800, NUMBER),
    (FinancialFact, "fiscal_period", "x" * 13, TEXT),
    (FinancialFact, "filed", "filed", DAY),
    (FinancialFact, "source_url", "", TEXT),
    (PatentCitation, "publication_number", "1234", FORMAT),
    (PatentCitation, "kind", "cites-family", CHOICE),
    (PatentCitation, "examiner", "yes", FLAG),
    (PatentCitation, "priority_date", "x", DAY),
    (PatentCitation, "publication_date", "x", DAY),
    (PatentCitation, "assignee", 3, TEXT),
    (PatentCitation, "title", ["title"], TEXT),
    (PatentRecord, "company", "X", FORMAT),
    (PatentRecord, "query", "", TEXT),
    (PatentRecord, "publication_number", "12", FORMAT),
    (PatentRecord, "title", 3, TEXT),
    (PatentRecord, "assignee", 3, TEXT),
    (PatentRecord, "inventors", 3, LIST),
    (PatentRecord, "priority_date", "x", DAY),
    (PatentRecord, "filing_date", "x", DAY),
    (PatentRecord, "publication_date", "x", DAY),
    (PatentRecord, "grant_date", "x", DAY),
    (PatentRecord, "source_url", "", TEXT),
    (PatentDetail, "publication_number", "12", FORMAT),
    (PatentDetail, "family_id", "abc", FORMAT),
    (PatentDetail, "title", 3, TEXT),
    (PatentDetail, "abstract", 3, TEXT),
    (PatentDetail, "assignees_original", "Raytheon", LIST),
    (PatentDetail, "assignees_current", "Raytheon", LIST),
    (PatentDetail, "inventors", "Joseph Marron", LIST),
    (PatentDetail, "cpc", ["ZZZ"], FORMAT),
    (PatentDetail, "claims", -1, NUMBER),
    (PatentDetail, "priority_date", "x", DAY),
    (PatentDetail, "filing_date", "x", DAY),
    (PatentDetail, "publication_date", "x", DAY),
    (PatentDetail, "grant_date", "x", DAY),
    (PatentDetail, "citations", "US5093563A", LIST),
    (PatentDetail, "source_url", "", TEXT),
    (PatentWindow, "company", "X", FORMAT),
    (PatentWindow, "query", "", TEXT),
    (PatentWindow, "after", "x", DAY),
    (PatentWindow, "before", "2019-01-01", FORMAT),
    (PatentWindow, "country", "USA", TEXT),
    (PatentWindow, "expected", -1, NUMBER),
    (PatentWindow, "fetched", 1.5, NUMBER),
    (PatentWindow, "status", "done", CHOICE),
    (PaperAuthorship, "position", -1, NUMBER),
    (PaperAuthorship, "author_id", "B12345", FORMAT),
    (PaperAuthorship, "name", "", TEXT),
    (PaperAuthorship, "orcid", 3, TEXT),
    (PaperAuthorship, "institutions", ["X1"], FORMAT),
    (PaperAuthorship, "company_affiliated", "yes", FLAG),
    (PaperRecord, "openalex_id", "A1234", FORMAT),
    (PaperRecord, "company", "X", FORMAT),
    (PaperRecord, "doi", 3, TEXT),
    (PaperRecord, "title", 3, TEXT),
    (PaperRecord, "publication_year", 1700, NUMBER),
    (PaperRecord, "publication_date", "x", DAY),
    (PaperRecord, "type", 3, TEXT),
    (PaperRecord, "venue", 3, TEXT),
    (PaperRecord, "language", 3, TEXT),
    (PaperRecord, "cited_by_count", -1, NUMBER),
    (PaperRecord, "fwci", -1, NUMBER),
    (PaperRecord, "is_oa", "yes", FLAG),
    (PaperRecord, "topic", 3, TEXT),
    (PaperRecord, "authorships", "Tero Karras", LIST),
    (PaperRecord, "source_url", "", TEXT),
    (ResearcherRecord, "author_id", "W1234", FORMAT),
    (ResearcherRecord, "company", "X", FORMAT),
    (ResearcherRecord, "name", "", TEXT),
    (ResearcherRecord, "orcid", 3, TEXT),
    (ResearcherRecord, "works_count", -1, NUMBER),
    (ResearcherRecord, "cited_by_count", 1.5, NUMBER),
    (ResearcherRecord, "h_index", -1, NUMBER),
    (ResearcherRecord, "institution", 3, TEXT),
    (ResearcherRecord, "current_affiliation", "yes", FLAG),
    (ResearcherRecord, "affiliation_years", -1, NUMBER),
    (ResearcherRecord, "source_url", "", TEXT),
    (PaperYearCount, "company", "X", FORMAT),
    (PaperYearCount, "year", "x", NUMBER),
    (PaperYearCount, "papers", -1, NUMBER),
    (PaperYearCount, "source_url", "", TEXT),
    (FinancialValue, "company", "X", FORMAT),
    (FinancialValue, "metric", "sales", CHOICE),
    (FinancialValue, "period_end", "x", DAY),
    (FinancialValue, "granularity", "month", CHOICE),
    (FinancialValue, "source", "sec", CHOICE),
    (FinancialValue, "value", "abc", NUMBER),
    (FinancialValue, "currency", "us", FORMAT),
    (FinancialValue, "concept", "", TEXT),
    (FinancialValue, "form", 3, TEXT),
    (FinancialValue, "fiscal_year", 1800, NUMBER),
    (FinancialValue, "fiscal_period", 3, TEXT),
    (FinancialValue, "filed", "x", DAY),
    (FinancialValue, "source_url", 3, TEXT),
    (FinancialValue, "note", "x" * 501, TEXT),
    (IndicatorValue, "company", "X", FORMAT),
    (IndicatorValue, "indicator", "growth", CHOICE),
    (IndicatorValue, "period_end", "x", DAY),
    (IndicatorValue, "granularity", "month", CHOICE),
    (IndicatorValue, "value", "abc", NUMBER),
    (IndicatorValue, "unit", "kg", CHOICE),
    (IndicatorValue, "currency", "us", FORMAT),
    (IndicatorValue, "value_usd", "abc", NUMBER),
    (IndicatorValue, "inputs", "", TEXT),
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


class TestCleaning:
    def test_identifiers_are_normalised(self) -> None:
        entry = CompanyEntry.model_validate(VALID[CompanyEntry])
        paper = PaperRecord.model_validate(VALID[PaperRecord])
        record = PatentRecord.model_validate(VALID[PatentRecord])

        assert entry.sec_ciks == ["0001045810"]
        assert paper.openalex_id == "W2904367110"
        assert paper.doi == "10.1109/cvpr.2019.00453"
        assert paper.cited_by_count == 0
        assert record.inventors == ["Minwoo Park", "Yilin YANG"]
        assert record.grant_date is None

    def test_citations_and_classes_are_cleaned(self) -> None:
        detail = PatentDetail.model_validate(VALID[PatentDetail])

        assert detail.family_id == "54766427"
        assert detail.cpc == ["G01S7/4914", "G01S17/32"]
        assert detail.abstract == "A frequency modulated (coherent) laser detection and ranging system."
        assert detail.citations[0].publication_number == "US5093563A"

    def test_a_window_counts_its_days(self) -> None:
        assert PatentWindow.model_validate(VALID[PatentWindow]).days() == 182

    def test_the_catalogue_finds_its_entries(self) -> None:
        catalog = CompaniesCatalog.model_validate(VALID[CompaniesCatalog])

        assert catalog.entry("tsmc") is not None
        assert catalog.entry("intel") is None
        assert [entry.key for entry in catalog.entries(["tsmc"])] == ["tsmc"]
        assert [entry.key for entry in catalog.entries([])] == ["nvidia", "tsmc"]

    def test_the_concepts_rank_each_concept_of_a_line(self) -> None:
        concepts = FinancialConcepts.model_validate(
            {
                "concepts": [
                    {"metric": "revenue", "nature": "flow", "concepts": ["us-gaap:Revenues", "ifrs-full:Revenue"]}
                ]
            }
        )

        assert concepts.by_concept()["ifrs-full:Revenue"][1] == 1
        assert concepts.nature(concepts.concepts[0].metric) is not None
