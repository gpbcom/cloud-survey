from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from sqlalchemy import text

from conftest import CRAWLED_AT, build_product, build_report, build_software, seed_catalogue, seed_marketplace
from models.cloud.enums import CloudProvider, DeliveryMethod, MarketPlayer, SoftwareCategory
from models.correspondence.llm.concept_answer import ConceptAnswer
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.stats.market_statistics import MarketStatistics
from storage.exception import StorageImportError
from storage.repositories.metrics.manual_metric_loader import ManualMetricLoader
from storage.storage import Storage

pytestmark = pytest.mark.db

AWS, AZURE, OVH = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.OVH
NOW = datetime(2026, 10, 20, tzinfo=UTC)


async def execute(storage: Storage, sql: str, **parameters: str) -> None:
    async with storage.database.connect() as connection, connection.begin():
        await connection.execute(text(sql), parameters)


async def seed(storage: Storage) -> None:
    await storage.seeder.seed()
    await seed_catalogue(storage, AWS, [build_product(name) for name in ("SageMaker", "EC2", "RDS", "Old")])
    await seed_catalogue(storage, OVH, [build_product("Public Cloud Instances")])
    domains: List[Tuple[str, str, str]] = [
        ("SageMaker", "ai-machine-learning", "ai-ml"),
        ("EC2", "compute", "virtual-machines"),
        ("RDS", "databases", "relational-database"),
        ("Public Cloud Instances", "compute", "virtual-machines"),
    ]
    for name, domain, category in domains:
        await execute(
            storage,
            "UPDATE products SET service_domains = ARRAY[:domain], service_categories = ARRAY[:category] "
            "WHERE name = :name",
            domain=domain,
            category=category,
            name=name,
        )
    await execute(storage, "UPDATE products SET categories = '{developer-tool}' WHERE name IN ('EC2', 'RDS')")
    await execute(storage, "UPDATE products SET deleted_at = '2026-08-01' WHERE name = 'Old'")
    await execute(storage, "UPDATE products SET added_at = '2025-02-10' WHERE name IN ('SageMaker', 'EC2')")
    software = [
        build_software("Grafana", ["monitoring"], [SoftwareCategory.DEVELOPER_TOOL], publisher="Grafana Labs"),
        build_software("Llama", ["ai"], [SoftwareCategory.DEVELOPER_TOOL], DeliveryMethod.AI_MODEL, "Meta"),
        build_software("Loki", ["logs"], [SoftwareCategory.DEVELOPER_TOOL], publisher="Grafana Labs"),
    ]
    await seed_marketplace(storage, AZURE, software)


def by_key(values: List[ProviderMetricValue]) -> Dict[Tuple[CloudProvider, str, ProviderMetric], float]:
    return {(value.provider, value.period, value.metric): value.value for value in values}


class TestDeriver:
    async def test_the_catalogue_and_marketplace_measures_are_derived(self, storage: Storage) -> None:
        await seed(storage)

        values = by_key(await storage.metric_deriver.derive(NOW))

        assert values[(AWS, "2026Q4", ProviderMetric.PRODUCTS)] == 3
        assert values[(AWS, "2026Q4", ProviderMetric.DOMAINS)] == 3
        assert values[(AWS, "2026Q4", ProviderMetric.CATEGORIES)] == 3
        assert values[(AWS, "2026Q4", ProviderMetric.AI_SHARE)] == pytest.approx(1 / 3)
        assert values[(AWS, "2026Q4", ProviderMetric.COMPUTE_SHARE)] == pytest.approx(1 / 3)
        assert values[(AWS, "2026Q4", ProviderMetric.DATA_SHARE)] == pytest.approx(1 / 3)
        assert values[(AWS, "2026Q4", ProviderMetric.DEVELOPER_SHARE)] == pytest.approx(2 / 3)
        assert values[(OVH, "2026Q4", ProviderMetric.PRODUCTS)] == 1
        assert values[(AWS, "2025Q1", ProviderMetric.LAUNCHES)] == 2
        assert values[(AWS, "2026Q3", ProviderMetric.DELETIONS)] == 1
        assert values[(AZURE, "2026Q4", ProviderMetric.MARKETPLACE_SIZE)] == 3
        assert values[(AZURE, "2026Q4", ProviderMetric.PUBLISHERS)] == 2
        assert values[(AZURE, "2026Q4", ProviderMetric.AI_MODEL_SHARE)] == pytest.approx(1 / 3)
        assert values[(AZURE, "2026Q4", ProviderMetric.SAAS_SHARE)] == pytest.approx(2 / 3)
        assert not any(metric is ProviderMetric.PARITY for _, _, metric in values)

    async def test_the_parity_counts_the_services_matched_with_a_leader(self, storage: Storage) -> None:
        await seed(storage)
        async with storage.database.connect() as connection:
            ids = {
                str(name): int(row_id)
                for row_id, name in (await connection.execute(text("SELECT id, name FROM products"))).all()
            }
        answer = ConceptAnswer.model_validate(
            {"name": "Virtual machines", "members": [{"id": ids["EC2"]}, {"id": ids["Public Cloud Instances"]}]}
        )
        await storage.correspondences.apply_answer(
            "virtual-machines", [answer], [ids["EC2"], ids["Public Cloud Instances"]]
        )

        values = by_key(await storage.metric_deriver.derive(NOW))

        assert values[(OVH, "2026Q4", ProviderMetric.PARITY)] == 1
        assert values[(AWS, "2026Q4", ProviderMetric.PARITY)] == 0

    async def test_the_market_shares_revenues_and_mentions_are_read(self, storage: Storage) -> None:
        reports = [
            build_report(
                "2026Q2",
                [(MarketPlayer.AMAZON, 30.0), (MarketPlayer.MICROSOFT, 22.0)],
                market_size_bn=100.0,
                mentions=[{"name": "Oracle", "rank": 4}, {"name": "Nebius"}],
            ),
            build_report("2025", [(MarketPlayer.AMAZON, 31.0)], market_size_bn=300.0),
        ]
        await storage.statistics.replace(
            "synergy", MarketStatistics(source="Synergy Research Group", crawled_at=CRAWLED_AT, reports=reports)
        )

        values = await storage.metric_deriver.derive(NOW)
        keyed = by_key(values)

        assert keyed[(AWS, "2026Q2", ProviderMetric.MARKET_SHARE)] == 30
        assert keyed[(AWS, "2026Q2", ProviderMetric.REVENUE)] == pytest.approx(30)
        assert keyed[(AZURE, "2026Q2", ProviderMetric.REVENUE)] == pytest.approx(22)
        assert keyed[(CloudProvider.ORACLE, "2026Q2", ProviderMetric.MENTIONS)] == 1
        assert not any(period == "2025" for _, period, _ in keyed)
        assert {value.source for value in values if value.metric is ProviderMetric.MARKET_SHARE} == {
            MetricSource.SYNERGY
        }

    async def test_the_other_players_shares_and_revenues_are_read(self, storage: Storage) -> None:
        report = build_report(
            "2014Q3",
            [(MarketPlayer.AMAZON, 27.0), (MarketPlayer.IBM, 7.0), (MarketPlayer.ALIBABA, 2.0)],
            market_size_bn=4.0,
        )
        await storage.statistics.replace(
            "synergy", MarketStatistics(source="Synergy Research Group", crawled_at=CRAWLED_AT, reports=[report])
        )

        keyed = by_key(await storage.metric_deriver.derive(NOW))

        assert keyed[(CloudProvider.IBM, "2014Q3", ProviderMetric.MARKET_SHARE)] == 7
        assert keyed[(CloudProvider.IBM, "2014Q3", ProviderMetric.REVENUE)] == pytest.approx(0.28)
        assert keyed[(CloudProvider.ALIBABA, "2014Q3", ProviderMetric.REVENUE)] == pytest.approx(0.08)


class TestRepository:
    async def test_the_measures_are_replaced_by_source_and_read(self, storage: Storage) -> None:
        await seed(storage)
        manual = ProviderMetricValue(
            provider=OVH, period="2025Q4", metric=ProviderMetric.CLOUD_REVENUE, value=0.25, source=MetricSource.MANUAL
        )
        await storage.metrics.upsert([manual])

        assert await storage.refresh_metrics(NOW) > 0
        assert await storage.refresh_metrics(NOW) > 0

        products = await storage.metrics.list([ProviderMetric.PRODUCTS], [AWS])
        assert [(value.period, value.value) for value in products] == [("2026Q4", 3.0)]
        assert await storage.metrics.list([ProviderMetric.CLOUD_REVENUE]) == []

    async def test_rows_of_an_unknown_metric_or_source_are_skipped(
        self, storage: Storage, caplog: pytest.LogCaptureFixture
    ) -> None:
        kept = ProviderMetricValue(
            provider=AWS, period="2026Q1", metric=ProviderMetric.REGIONS, value=33.0, source=MetricSource.WIKIDATA
        )
        await storage.metrics.upsert([kept])
        for provider, metric, source in (
            (AWS.value, "retired-metric", "derived"),
            (AWS.value, "regions", "oracle"),
            ("gone-cloud", "regions", "derived"),
        ):
            await execute(
                storage,
                "INSERT INTO provider_metrics (provider, period, metric, source, value) "
                "VALUES (:provider, '2026Q1', :metric, :source, 1)",
                provider=provider,
                metric=metric,
                source=source,
            )

        with caplog.at_level("WARNING"):
            values = await storage.metrics.list()

        assert [(value.provider, value.metric, value.source) for value in values] == [
            (AWS, ProviderMetric.REGIONS, MetricSource.WIKIDATA)
        ]
        warning = next(record.getMessage() for record in caplog.records if "skipped" in record.getMessage())
        assert warning.startswith("2 stored provider metrics skipped")
        assert "regions/oracle" in warning
        assert "retired-metric/derived" in warning


class TestManualLoader:
    def test_the_manual_measures_are_read_as_manual(self, tmp_path: Path) -> None:
        path = tmp_path / "manual.yaml"
        path.write_text(
            "values:\n"
            "  - {provider: ovh-cloud, period: 2025q4, metric: cloud-revenue, value: 0.28, source_url: https://x}\n",
            encoding="utf-8",
        )

        (value,) = ManualMetricLoader(path).load()

        assert (value.period, value.source, value.value) == ("2025Q4", MetricSource.MANUAL, 0.28)
        assert ManualMetricLoader(tmp_path / "missing.yaml").load() == []

    def test_invalid_manual_measures_are_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "manual.yaml"
        path.write_text(
            "values:\n  - {provider: ovh-cloud, period: 2025-12, metric: cloud-revenue, value: 1}\n", encoding="utf-8"
        )

        with pytest.raises(StorageImportError):
            ManualMetricLoader(path).load()
