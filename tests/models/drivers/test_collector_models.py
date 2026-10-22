from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.collectors.metric_source_entry import MetricSourceEntry


class TestMetricSourceEntry:
    def test_identifiers_are_normalized(self) -> None:
        entry = MetricSourceEntry.model_validate(
            {
                "provider": "scaleway",
                "cik": 789019,
                "wikidata": " q3352745 ",
                "asns": ["12876", 12876, 1],
                "repositories": ["scaleway/terraform-provider-scaleway", "scaleway/terraform-provider-scaleway"],
            }
        )

        assert entry.provider is CloudProvider.SCALEWAY
        assert entry.cik == "0000789019"
        assert entry.wikidata == "Q3352745"
        assert entry.asns == [12876, 1]
        assert entry.repositories == ["scaleway/terraform-provider-scaleway"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("cik", "12345678901"),
            ("cik", "12a"),
            ("wikidata", "P571"),
            ("asns", [0]),
            ("asns", ["AS16509"]),
            ("repositories", ["no-owner"]),
            ("repositories", ["a/b/c"]),
        ],
    )
    def test_malformed_identifiers_are_refused(self, field: str, value: JsonValue) -> None:
        with pytest.raises(ValidationError):
            MetricSourceEntry.model_validate({"provider": "scaleway", field: value})

    def test_the_defaults_are_empty(self) -> None:
        entry = MetricSourceEntry(provider=CloudProvider.CIVO)

        assert (entry.cik, entry.wikidata, entry.asns, entry.repositories) == (None, None, [], [])


class TestCollectorCatalog:
    def test_the_last_entry_of_a_provider_wins_and_concepts_are_unique(self) -> None:
        catalog = CollectorCatalog.model_validate(
            {
                "user_agent": "  bot  ",
                "capex_concepts": ["A", " A ", "B", ""],
                "entries": [{"provider": "civo", "asns": [1]}, {"provider": "civo", "asns": [2]}],
            }
        )

        assert catalog.user_agent == "bot"
        assert catalog.capex_concepts == ["A", "B"]
        assert [entry.asns for entry in catalog.entries] == [[2]]
        assert catalog.sec_user_agent_env == "CRAWLER_SEC_USER_AGENT"

    def test_a_user_agent_is_required(self) -> None:
        with pytest.raises(ValidationError):
            CollectorCatalog.model_validate({"user_agent": " "})

    def test_unknown_keys_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            CollectorCatalog.model_validate({"user_agent": "bot", "token": "secret"})
