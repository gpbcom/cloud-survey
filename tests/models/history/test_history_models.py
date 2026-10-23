from __future__ import annotations

from typing import Dict, List, Tuple

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider
from models.history.catalog.company import Company
from models.history.chronology import Chronology
from models.history.enums import AdoptionCriterion, DatePrecision, EventKind
from models.history.exception import InvalidHistoryDateError
from models.history.timeline.notable_event import NotableEvent
from models.history.timeline.partial_date import PartialDate
from models.history.timeline.reign import Reign


def chronology(reigns: List[JsonValue], events: List[JsonValue]) -> Dict[str, JsonValue]:
    return {
        "as_of": "2026-10",
        "segments": [{"key": "pcs", "label": "PCs"}, {"key": "cloud", "label": "Cloud"}],
        "companies": [
            {"key": "ibm", "label": "IBM", "color": "#4F8CFF"},
            {"key": "lenovo", "label": "Lenovo", "color": "#e57373"},
            {"key": "amazon", "label": "Amazon", "color": "#ff9900", "provider": "amazon-web-services"},
        ],
        "reigns": reigns,
        "events": events,
    }


class TestPartialDate:
    @pytest.mark.parametrize(
        ("text", "parts", "fraction"),
        [
            ("1998", (1998, 1, 1, DatePrecision.YEAR), 1998.0),
            ("1998-07", (1998, 7, 1, DatePrecision.MONTH), 1998.5),
            ("2025-07-31", (2025, 7, 31, DatePrecision.DAY), 2025.5 + 30 / 31 / 12),
        ],
    )
    def test_dates_known_to_the_year_month_or_day(
        self, text: str, parts: Tuple[int, int, int, DatePrecision], fraction: float
    ) -> None:
        dates = PartialDate()

        assert dates.parts(text) == parts
        assert dates.fraction(text) == pytest.approx(fraction)

    @pytest.mark.parametrize("text", ["98", "1998-13", "1998-02-30", "1998/07", "July 1998"])
    def test_malformed_dates_are_refused(self, text: str) -> None:
        with pytest.raises(InvalidHistoryDateError):
            PartialDate().parts(text)


class TestReign:
    def test_a_reign_and_its_span(self) -> None:
        reign = Reign.model_validate(
            {
                "segment": "pcs",
                "company": "ibm",
                "start": 1981,
                "end": "1994",
                "criteria": ["compatibility"],
                "rise": " An\n open design. ",
            }
        )

        assert (reign.start, reign.end, reign.rise) == ("1981", "1994", "An open design.")
        assert reign.criteria == [AdoptionCriterion.COMPATIBILITY]
        assert reign.key() == "reign:pcs:ibm:1981"
        assert (reign.begins(), reign.ends("2026-10")) == (1981.0, 1994.0)

    def test_an_ongoing_reign_ends_at_the_date_of_the_chronology(self) -> None:
        reign = Reign.model_validate({"segment": "pcs", "company": "lenovo", "start": "2013"})

        assert reign.ends("2026-10") == pytest.approx(2026.75)

    @pytest.mark.parametrize(("field", "value"), [("end", "1980"), ("start", "1981-00"), ("criteria", ["luck"])])
    def test_invalid_reigns_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"segment": "pcs", "company": "ibm", "start": "1981", field: value}

        with pytest.raises(ValidationError):
            Reign.model_validate(raw)


class TestNotableEvent:
    def test_an_event(self) -> None:
        event = NotableEvent.model_validate(
            {
                "key": "cma-cloud",
                "date": "2025-07-31",
                "label": "CMA",
                "kind": "regulation",
                "companies": ["amazon", "amazon"],
            }
        )

        assert (event.year(), event.precision(), event.kind) == (2025, DatePrecision.DAY, EventKind.REGULATION)
        assert event.companies == ["amazon"]
        assert event.default is False

    @pytest.mark.parametrize(
        ("field", "value"), [("key", "Not A Key"), ("date", "2025-7"), ("kind", "rumour"), ("label", " ")]
    )
    def test_invalid_events_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"key": "x", "date": "2025", "label": "X", "kind": "product"}
        raw[field] = value

        with pytest.raises(ValidationError):
            NotableEvent.model_validate(raw)


class TestCompany:
    def test_a_company(self) -> None:
        company = Company.model_validate(
            {"key": "amazon", "label": " Amazon ", "color": "#FF9900", "provider": "amazon-web-services"}
        )

        assert (company.label, company.color, company.provider) == ("Amazon", "#ff9900", CloudProvider.AWS)

    @pytest.mark.parametrize(("field", "value"), [("color", "orange"), ("key", "Amazon"), ("provider", "nowhere")])
    def test_invalid_companies_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"key": "amazon", "label": "Amazon", "color": "#ff9900"}
        raw[field] = value

        with pytest.raises(ValidationError):
            Company.model_validate(raw)


class TestChronology:
    def test_lookups_and_span(self) -> None:
        loaded = Chronology.model_validate(
            chronology(
                [
                    {"segment": "pcs", "company": "lenovo", "start": "2013"},
                    {"segment": "pcs", "company": "ibm", "start": "1981", "end": "2013"},
                ],
                [
                    {"key": "late", "date": "2025", "label": "Late", "kind": "regulation"},
                    {
                        "key": "early",
                        "date": "1990",
                        "label": "Early",
                        "kind": "product",
                        "companies": ["ibm"],
                        "segment": "pcs",
                    },
                ],
            )
        )

        assert [reign.company for reign in loaded.reigns_of("pcs")] == ["ibm", "lenovo"], "a hand-over at the same date"
        assert [event.key for event in loaded.events_of()] == ["early", "late"]
        assert [event.key for event in loaded.events_of([EventKind.REGULATION])] == ["late"]
        company = loaded.company("ibm")
        segment = loaded.segment("cloud")
        assert company is not None
        assert company.label == "IBM"
        assert segment is not None
        assert segment.label == "Cloud"
        assert loaded.company("nobody") is None
        assert loaded.span() == (1981.0, pytest.approx(2026.75))

    @pytest.mark.parametrize(
        ("reigns", "events", "message"),
        [
            ([{"segment": "phones", "company": "ibm", "start": "1990"}], [], "Unknown segment"),
            ([{"segment": "pcs", "company": "apple", "start": "1990"}], [], "Unknown company"),
            (
                [
                    {"segment": "pcs", "company": "ibm", "start": "1981"},
                    {"segment": "pcs", "company": "lenovo", "start": "2013"},
                ],
                [],
                "starts before",
            ),
            (
                [
                    {"segment": "pcs", "company": "ibm", "start": "1981", "end": "1995"},
                    {"segment": "pcs", "company": "lenovo", "start": "1994"},
                ],
                [],
                "starts before",
            ),
            (
                [],
                [{"key": "a", "date": "2000", "label": "A", "kind": "product", "companies": ["apple"]}],
                "Unknown company",
            ),
            (
                [],
                [{"key": "a", "date": "2000", "label": "A", "kind": "product", "segment": "phones"}],
                "Unknown segment",
            ),
            (
                [],
                [
                    {"key": "a", "date": "2000", "label": "A", "kind": "product"},
                    {"key": "a", "date": "2001", "label": "B", "kind": "product"},
                ],
                "defined twice",
            ),
        ],
    )
    def test_inconsistent_chronologies_are_refused(
        self, reigns: List[JsonValue], events: List[JsonValue], message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            Chronology.model_validate(chronology(reigns, events))

    def test_duplicate_companies_are_refused(self) -> None:
        raw = chronology([], [])
        companies = raw["companies"]
        assert isinstance(companies, list)
        companies.append({"key": "ibm", "label": "IBM again", "color": "#000000"})

        with pytest.raises(ValidationError, match="company key 'ibm' is defined twice"):
            Chronology.model_validate(raw)
