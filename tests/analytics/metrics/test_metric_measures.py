from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from pydantic import JsonValue

from analytics.metrics.measures.adoption_measures import AdoptionMeasures
from analytics.metrics.measures.capex_quarters import CapexQuarters
from analytics.metrics.measures.company_measures import CompanyMeasures
from analytics.metrics.measures.network_measures import NetworkMeasures
from analytics.metrics.metric_measurer import MetricMeasurer
from models.cloud.enums import CloudProvider
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.facts.capex_fact import CapexFact
from models.drivers.facts.company_fact import CompanyFact
from models.drivers.facts.network_fact import NetworkFact
from models.drivers.facts.repository_fact import RepositoryFact
from models.drivers.metrics.provider_metric_value import ProviderMetricValue

NOW = datetime(2026, 10, 20, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "metrics"
SEC = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"


def filed(provider: CloudProvider, fixture: str) -> List[CapexFact]:
    """The capex facts of a recorded `companyfacts` document, as the EDGAR crawler streams them."""
    document = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    return [
        CapexFact(
            provider=provider,
            concept=concept,
            start=fact["start"],
            end=fact["end"],
            value=fact["val"],
            form=fact["form"],
            source_url=SEC,
        )
        for concept, found in document["facts"]["us-gaap"].items()
        for fact in found["units"]["USD"]
    ]


def by_period(values: List[ProviderMetricValue]) -> Dict[str, float]:
    return {value.period: round(value.value, 3) for value in values}


class TestCapexQuarters:
    def test_year_to_date_facts_give_quarters(self) -> None:
        values = CapexQuarters().measure(filed(CloudProvider.AZURE, "edgar-microsoft.json"))

        quarters = by_period(values)
        assert quarters["2025Q1"] == 16.745, "published as a 3-month fact"
        assert quarters["2025Q2"] == pytest.approx(64.551 - 47.472), "the 10-K minus the nine months"
        assert quarters["2026Q2"] == pytest.approx(115.948 - 80.146)
        assert {(value.metric, value.source, value.source_url) for value in values} == {
            (ProviderMetric.CAPEX, MetricSource.EDGAR, SEC)
        }
        assert [value.period for value in values] == sorted(value.period for value in values)

    def test_a_later_concept_fills_the_missing_quarters(self) -> None:
        early = CapexFact(
            provider=CloudProvider.AWS,
            concept="Old",
            start="2016-01-01",
            end="2016-03-31",
            value=1e9,
            form="10-Q",
            source_url=SEC,
        )
        late = early.model_copy(update={"concept": "New", "value": 9e9})
        recent = late.model_copy(update={"start": datetime(2026, 4, 1).date(), "end": datetime(2026, 6, 30).date()})

        quarters = by_period(CapexQuarters().measure([early, late, recent]))

        assert quarters == {"2016Q1": 1.0, "2026Q2": 9.0}

    def test_no_fact_no_measure(self) -> None:
        assert CapexQuarters().measure([]) == []


class TestCompanyMeasures:
    def test_age_from_the_earliest_founding_and_dated_employees(self) -> None:
        facts = [
            CompanyFact(
                provider=CloudProvider.OVH, item="Q568183", inception=datetime(1999, 10, 15, tzinfo=UTC), source_url="u"
            ),
            CompanyFact(
                provider=CloudProvider.OVH, item="Q568183", inception=datetime(2001, 1, 1, tzinfo=UTC), source_url="u"
            ),
            CompanyFact(
                provider=CloudProvider.OVH,
                item="Q568183",
                employees=3074,
                employees_at=datetime(2023, 5, 1, tzinfo=UTC),
                source_url="u",
            ),
            CompanyFact(provider=CloudProvider.OVH, item="Q568183", employees=2900, source_url="u"),
        ]

        values = CompanyMeasures().measure(facts, NOW)

        found: Dict[Tuple[ProviderMetric, str], float] = {(value.metric, value.period): value.value for value in values}
        assert found[(ProviderMetric.AGE, "2026Q4")] == pytest.approx(27.0, abs=0.05)
        assert found[(ProviderMetric.EMPLOYEES, "2023Q2")] == 3074
        assert found[(ProviderMetric.EMPLOYEES, "2026Q4")] == 2900, "undated: the quarter of the collection"


class TestNetworkMeasures:
    def test_each_exchange_and_facility_counts_once_per_provider(self) -> None:
        facts = [
            NetworkFact(provider=CloudProvider.AWS, asn=16509, exchanges=[1, 2], facilities=[5], source_url="u"),
            NetworkFact(provider=CloudProvider.AWS, asn=14618, exchanges=[2, 3], facilities=[5, 6], source_url="u"),
        ]

        values = NetworkMeasures().measure(facts, NOW)

        assert {(value.metric, value.value, value.period) for value in values} == {
            (ProviderMetric.NETWORK_EXCHANGES, 3.0, "2026Q4"),
            (ProviderMetric.FACILITIES, 2.0, "2026Q4"),
        }


class TestAdoptionMeasures:
    def test_the_stars_of_the_repositories_are_summed(self) -> None:
        facts = [
            RepositoryFact(provider=CloudProvider.SCALEWAY, repository="scaleway/a", stars=10, source_url="u"),
            RepositoryFact(provider=CloudProvider.SCALEWAY, repository="scaleway/b", stars=5, source_url="u"),
            RepositoryFact(provider=CloudProvider.SCALEWAY, repository="scaleway/b", stars=5, source_url="u"),
        ]

        (value,) = AdoptionMeasures().measure(facts, NOW)

        assert (value.metric, value.value, value.source_url) == (
            ProviderMetric.SDK_STARS,
            15.0,
            "https://github.com/scaleway/a",
        )


class TestMetricMeasurer:
    def test_each_source_is_measured_by_its_measure(self) -> None:
        stars: Dict[str, JsonValue] = {
            "provider": "civo",
            "repository": "civo/terraform-provider-civo",
            "stars": 7,
            "source_url": "u",
        }
        network: Dict[str, JsonValue] = {
            "provider": "civo",
            "asn": 1,
            "exchanges": [4],
            "facilities": [],
            "source_url": "u",
        }
        measurer = MetricMeasurer()

        (adoption,) = measurer.measure(MetricSource.GITHUB, [stars], NOW)
        reach = measurer.measure(MetricSource.PEERINGDB, [network], NOW)

        assert (adoption.metric, adoption.value) == (ProviderMetric.SDK_STARS, 7.0)
        assert {value.metric for value in reach} == {ProviderMetric.NETWORK_EXCHANGES, ProviderMetric.FACILITIES}

    def test_an_invalid_item_is_left_out(self, caplog: pytest.LogCaptureFixture) -> None:
        values = MetricMeasurer().measure(MetricSource.GITHUB, [{"provider": "civo", "stars": -1}], NOW)

        assert values == []
        assert any("Invalid RepositoryFact item" in message for message in caplog.messages)

    def test_a_source_without_facts_has_no_measure(self) -> None:
        assert MetricMeasurer().measure(MetricSource.MANUAL, [{"anything": 1}], NOW) == []

    def test_the_wikidata_and_edgar_facts_are_measured(self) -> None:
        company: Dict[str, JsonValue] = {
            "provider": "scaleway",
            "item": "Q3352745",
            "inception": "2000-08-30T00:00:00Z",
            "source_url": "u",
        }
        capex = [fact.model_dump(mode="json") for fact in filed(CloudProvider.AZURE, "edgar-microsoft.json")]
        measurer = MetricMeasurer()

        assert [value.metric for value in measurer.measure(MetricSource.WIKIDATA, [company], NOW)] == [
            ProviderMetric.AGE
        ]
        assert measurer.measure(MetricSource.EDGAR, capex, NOW)
