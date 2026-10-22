from __future__ import annotations

from datetime import date
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider
from models.drivers.facts.capex_fact import CapexFact
from models.drivers.facts.company_fact import CompanyFact
from models.drivers.facts.network_fact import NetworkFact
from models.drivers.facts.repository_fact import RepositoryFact


class TestCapexFact:
    def test_a_filed_fact(self) -> None:
        fact = CapexFact.model_validate(
            {
                "provider": "microsoft-azure",
                "concept": " PaymentsToAcquirePropertyPlantAndEquipment ",
                "start": "2025-07-01",
                "end": "2026-03-31",
                "value": 80146000000,
                "form": "10-Q",
                "source_url": "https://data.sec.gov/x.json",
            }
        )

        assert (fact.provider, fact.concept, fact.start, fact.end) == (
            CloudProvider.AZURE,
            "PaymentsToAcquirePropertyPlantAndEquipment",
            date(2025, 7, 1),
            date(2026, 3, 31),
        )

    @pytest.mark.parametrize(
        ("field", "value"), [("end", "2025-06-30"), ("value", -1), ("concept", " "), ("form", ""), ("start", "soon")]
    )
    def test_invalid_facts_are_refused(self, field: str, value: JsonValue) -> None:
        raw = {
            "provider": "microsoft-azure",
            "concept": "Capex",
            "start": "2025-07-01",
            "end": "2025-09-30",
            "value": 1.0,
            "form": "10-Q",
            "source_url": "u",
        }
        raw[field] = value

        with pytest.raises(ValidationError):
            CapexFact.model_validate(raw)


class TestCompanyFact:
    def test_an_entity_url_gives_its_item(self) -> None:
        fact = CompanyFact.model_validate(
            {
                "provider": "ovh-cloud",
                "item": "http://www.wikidata.org/entity/q568183",
                "employees": "3074",
                "source_url": "u",
            }
        )

        assert (fact.item, fact.employees, fact.inception) == ("Q568183", 3074.0, None)

    @pytest.mark.parametrize(("field", "value"), [("item", "P571"), ("employees", -3), ("inception", "unknown")])
    def test_invalid_facts_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"provider": "ovh-cloud", "item": "Q568183", "source_url": "u", field: value}

        with pytest.raises(ValidationError):
            CompanyFact.model_validate(raw)


class TestNetworkFact:
    def test_the_links_are_kept_once(self) -> None:
        fact = NetworkFact.model_validate(
            {"provider": "scaleway", "asn": 12876, "exchanges": [3, 3, 1], "facilities": [2, 2], "source_url": "u"}
        )

        assert (fact.exchanges, fact.facilities) == ([3, 1], [2])

    @pytest.mark.parametrize(("field", "value"), [("asn", 0), ("exchanges", ["x"]), ("source_url", "")])
    def test_invalid_facts_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"provider": "scaleway", "asn": 12876, "source_url": "u", field: value}

        with pytest.raises(ValidationError):
            NetworkFact.model_validate(raw)


class TestRepositoryFact:
    def test_a_repository(self) -> None:
        fact = RepositoryFact.model_validate(
            {"provider": "civo", "repository": " civo/cli ", "stars": 3, "source_url": "u"}
        )

        assert (fact.repository, fact.stars) == ("civo/cli", 3)

    @pytest.mark.parametrize(("field", "value"), [("repository", "civo"), ("stars", -1), ("repository", "a/b/c")])
    def test_invalid_facts_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"provider": "civo", "repository": "civo/cli", "stars": 3, "source_url": "u"}
        raw[field] = value

        with pytest.raises(ValidationError):
            RepositoryFact.model_validate(raw)
