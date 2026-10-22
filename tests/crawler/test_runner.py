from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue

from classifier.exception import ClassificationRulesFileError
from classifier.software_classifier import SoftwareClassifier
from conftest import CRAWLED_AT
from crawler.exception import CrawlerError, EmptyCrawlError, UnknownCrawlerTargetError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider, DateSource, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.drivers.enums import MetricSource
from models.storage.enums import CrawlStatus
from storage.storage import Storage

DEV = SoftwareCategory.DEVELOPER_TOOL


class FakeCrawler:
    """Stand-in for a crawler, streaming pre-defined items."""

    source = "Synergy Research Group"

    def __init__(self, items: List[Dict[str, JsonValue]], error: Optional[Exception] = None) -> None:
        self.items = items
        self.error = error

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        for item in self.items:
            yield item
        if self.error:
            raise self.error


class SlowCrawler(FakeCrawler):
    """Crawler recording how many crawls run at the same time."""

    active = 0
    highest = 0

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        SlowCrawler.active += 1
        SlowCrawler.highest = max(SlowCrawler.highest, SlowCrawler.active)
        await asyncio.sleep(0.05)
        SlowCrawler.active -= 1
        for item in self.items:
            yield item


def product(name: str, description: Optional[str] = None) -> Dict[str, JsonValue]:
    return {"name": name, "description": description or f"{name} description", "pricing_policy": []}


def software(name: str, categories: Optional[List[str]] = None) -> Dict[str, JsonValue]:
    labels: List[JsonValue] = list(categories or [])
    return {
        "name": name,
        "description": f"{name} description",
        "url": f"https://marketplace.example.com/{name}",
        "marketplace_categories": labels,
        "categories": ["developer-tool"],
    }


def market_report(period: str, size: Optional[float] = None) -> Dict[str, JsonValue]:
    return {
        "period": period,
        "region": "worldwide",
        "segment": "cloud-infrastructure-services",
        "market_size_bn": size,
        "source_url": "https://www.srgresearch.com/articles/x",
        "title": "Cloud market",
        "published": "2026-07-30",
    }


@pytest.fixture
def factory() -> MagicMock:
    return MagicMock(spec=CrawlerFactory)


@pytest.fixture
def runner(storage: Storage, factory: MagicMock) -> CatalogueRunner:
    return CatalogueRunner(storage=storage, factory=factory, save_interval=0)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWLER_DATABASE_URL", raising=False)
    runner = CatalogueRunner()

    assert isinstance(runner.storage, Storage)
    assert not runner.storage.database.is_open
    assert isinstance(runner.factory, CrawlerFactory)
    assert runner.logger.name == "crawler.runner"
    assert runner.save_interval == CatalogueRunner.SAVE_INTERVAL


async def test_crawl_builds_the_catalogue_without_writing_it(factory: MagicMock) -> None:
    factory.get.return_value = FakeCrawler([product("Instances"), product("Object Storage")])
    received: List[Tuple[CloudProvider, str]] = []

    catalogue = await CatalogueRunner(factory=factory).crawl(
        "scaleway", lambda provider, item: received.append((provider, item.name))
    )

    factory.get.assert_called_once_with("scaleway")
    assert catalogue.provider is CloudProvider.SCALEWAY
    assert catalogue.crawled_at.utcoffset() is not None
    assert catalogue.products == [
        CloudProduct(name="Instances", description="Instances description", categories=[DEV]),
        CloudProduct(name="Object Storage", description="Object Storage description", categories=[DEV]),
    ]
    assert received == [(CloudProvider.SCALEWAY, "Instances"), (CloudProvider.SCALEWAY, "Object Storage")]


async def test_marketplace_listings_seen_again_are_merged(factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler(
        [software("grafana", ["Monitoring"]), software("vault"), software("grafana", ["Monitoring", "Analytics"])]
    )
    received: List[Tuple[CloudProvider, str]] = []

    marketplace = await CatalogueRunner(factory=factory).crawl_marketplace(
        "civo", lambda provider, item: received.append((provider, item.name))
    )

    assert marketplace.provider is CloudProvider.CIVO
    assert [(item.name, item.marketplace_categories) for item in marketplace.software] == [
        ("grafana", ["Monitoring", "Analytics"]),
        ("vault", []),
    ]
    assert received == [(CloudProvider.CIVO, "grafana"), (CloudProvider.CIVO, "vault")]


async def test_unknown_target(factory: MagicMock) -> None:
    with pytest.raises(UnknownCrawlerTargetError):
        await CatalogueRunner().run("unknown-cloud")


@pytest.mark.parametrize(("raw", "expected"), [(None, 4), ("2", 2), (" 6 ", 6), ("0", 4), ("many", 4)])
def test_concurrency_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, raw: Optional[str], expected: int
) -> None:
    if raw is None:
        monkeypatch.delenv("CRAWLER_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("CRAWLER_CONCURRENCY", raw)

    assert CatalogueRunner().concurrency == expected
    assert (raw in ("0", "many")) == any("is not a positive number" in message for message in caplog.messages)


def test_explicit_concurrency_is_at_least_one() -> None:
    assert (CatalogueRunner(concurrency=3).concurrency, CatalogueRunner(concurrency=0).concurrency) == (3, 1)


async def test_marketplace_crawls_share_one_classifier(factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])
    runner = CatalogueRunner(factory=factory)

    await runner.crawl_marketplace(CloudProvider.CIVO)
    await runner.crawl_marketplace(CloudProvider.CIVO)

    classifiers = {id(call.args[1]) for call in factory.get_marketplace.call_args_list}
    assert len(classifiers) == 1
    assert isinstance(runner.classifier, SoftwareClassifier)


@pytest.mark.db
async def test_run_writes_and_dates_the_catalogue(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage
) -> None:
    factory.get.return_value = FakeCrawler([product("Amazon EC2"), product("Amazon S3")])
    first = await runner.run(CloudProvider.AWS)
    factory.get.return_value = FakeCrawler([product("Amazon EC2", "Changed"), product("Amazon Lambda")])

    second = await runner.run(CloudProvider.AWS)

    assert (first.status, first.found, first.added) == (CrawlStatus.SUCCEEDED, 2, 0)
    assert (second.found, second.added, second.updated, second.deleted, second.size) == (2, 1, 1, 1, 2)
    catalogue = await storage.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    by_name = {item.name: item for item in catalogue.products}
    assert by_name["Amazon EC2"].updated_from is DateSource.CRAWL
    assert by_name["Amazon Lambda"].added_at == second.started_at
    assert by_name["Amazon S3"].deleted_at == second.started_at


@pytest.mark.db
async def test_empty_crawl_keeps_the_stored_catalogue(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    factory.get.return_value = FakeCrawler([product("Amazon EC2")])
    await runner.run(CloudProvider.AWS)
    factory.get.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError) as exc_info:
        await runner.run(CloudProvider.AWS)

    assert exc_info.value.provider == "amazon-web-services"
    assert "The amazon-web-services crawl produced no product: its catalogue is unchanged." in caplog.messages
    catalogue = await storage.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    assert [item.deleted_at for item in catalogue.products] == [None]


@pytest.mark.db
async def test_crawl_errors_propagate_and_keep_what_was_written(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage
) -> None:
    factory.get.return_value = FakeCrawler([product("Instances")], error=CrawlerError("blocked"))

    with pytest.raises(CrawlerError, match="blocked"):
        await runner.run(CloudProvider.SCALEWAY)

    catalogue = await storage.catalogues.load(CloudProvider.SCALEWAY)
    assert catalogue is not None
    assert [item.name for item in catalogue.products] == ["Instances"]
    assert not catalogue.in_progress


@pytest.mark.db
async def test_a_running_crawl_is_visible_to_the_readers(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage
) -> None:
    seen: List[Tuple[bool, int]] = []

    class WatchedCrawler(FakeCrawler):
        async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
            for item in self.items:
                yield item
                stamps = {stamp.dataset: stamp for stamp in await storage.datasets.stamps()}
                stamp = stamps["civo"]
                seen.append((stamp.in_progress, stamp.size))

    factory.get.return_value = WatchedCrawler([product("Compute"), product("Storage")])

    await runner.run(CloudProvider.CIVO)

    assert seen == [(True, 1), (True, 2)]
    (stamp,) = await storage.datasets.stamps()
    assert (stamp.in_progress, stamp.size) == (False, 2)


@pytest.mark.db
async def test_run_all_continues_after_a_failure(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    outcomes: Dict[CloudProvider, Union[FakeCrawler, Exception]] = {
        CloudProvider.AWS: FakeCrawler([product("Amazon EC2")]),
        CloudProvider.AZURE: FakeCrawler([]),
        CloudProvider.GCP: FakeCrawler([product("Cloud Run")], error=CrawlerError("blocked")),
        CloudProvider.OVH: FakeCrawler([product("Compute")]),
    }
    factory.get.side_effect = lambda provider: outcomes[provider]
    counts: Dict[CloudProvider, int] = {}

    written = await runner.run_all(
        lambda provider, item: counts.update({provider: counts.get(provider, 0) + 1}), list(outcomes)
    )

    assert set(written) == {CloudProvider.AWS, CloudProvider.OVH}
    assert counts == {CloudProvider.AWS: 1, CloudProvider.GCP: 1, CloudProvider.OVH: 1}
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert "The google-cloud-platform catalogue was not updated: blocked" in errors
    assert caplog.records[-1].getMessage() == "2 catalogues written, 2 failed."
    assert caplog.records[-1].levelno == logging.WARNING


@pytest.mark.db
@pytest.mark.parametrize("marketplaces", [False, True])
async def test_crawls_run_in_parallel_within_the_limit(
    storage: Storage, factory: MagicMock, marketplaces: bool
) -> None:
    runner = CatalogueRunner(storage=storage, factory=factory, concurrency=2, save_interval=0)
    SlowCrawler.highest = 0
    targets = [CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP, CloudProvider.OVH, CloudProvider.CIVO]
    factory.get.side_effect = lambda provider: SlowCrawler([product("Compute")])
    factory.get_marketplace.side_effect = lambda provider, classifier: SlowCrawler([software("grafana")])

    if marketplaces:
        written = await runner.run_all_marketplaces(providers=targets)
    else:
        written = await runner.run_all(providers=targets)

    assert list(written) == targets
    assert SlowCrawler.highest == 2


@pytest.mark.db
async def test_run_marketplace_writes_and_merges_the_listings(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage
) -> None:
    factory.get_marketplace.return_value = FakeCrawler(
        [software("grafana", ["Monitoring"]), software("vault"), software("grafana", ["Monitoring", "Analytics"])]
    )

    summary = await runner.run_marketplace(CloudProvider.CIVO)

    assert (summary.found, summary.size) == (2, 2)
    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    assert sorted((item.name, tuple(item.marketplace_categories)) for item in marketplace.software) == [
        ("grafana", ("Monitoring", "Analytics")),
        ("vault", ()),
    ]


@pytest.mark.db
async def test_empty_marketplace_is_an_error(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.get_marketplace.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError):
        await runner.run_marketplace(CloudProvider.CIVO)

    assert "The civo marketplace crawl produced no software: its marketplace is unchanged." in caplog.messages


@pytest.mark.db
async def test_run_all_marketplaces(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.marketplace_providers.return_value = [CloudProvider.CIVO, CloudProvider.STACKIT, CloudProvider.AWS]
    outcomes = {
        CloudProvider.CIVO: FakeCrawler([software("grafana")]),
        CloudProvider.STACKIT: FakeCrawler([], error=CrawlerError("blocked")),
        CloudProvider.AWS: FakeCrawler([software("datadog")]),
    }
    factory.get_marketplace.side_effect = lambda provider, classifier: outcomes[provider]

    written = await runner.run_all_marketplaces()

    assert set(written) == {CloudProvider.CIVO, CloudProvider.AWS}
    assert "The stackit marketplace was not updated: blocked" in caplog.messages
    assert caplog.records[-1].getMessage() == "2 marketplaces written, 1 failed."


@pytest.mark.db
async def test_classification_errors_skip_the_marketplace(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.marketplace_providers.return_value = [CloudProvider.CIVO]
    error = ClassificationRulesFileError(Path("rules.yaml"), "the rules are invalid.")

    with patch("crawler.runner.SoftwareClassifier", side_effect=error):
        written = await runner.run_all_marketplaces()

    assert written == {}
    assert any("The civo marketplace was not updated" in message for message in caplog.messages)


@pytest.mark.db
async def test_reclassify_marketplaces(
    runner: CatalogueRunner, storage: Storage, make_software: Callable[..., MarketplaceSoftware]
) -> None:
    stale: MarketplaceSoftware = make_software("Grafana", ["crm"], [SoftwareCategory.END_USER_SOFTWARE])
    await storage.marketplaces.import_items(CloudProvider.CIVO, CRAWLED_AT, [stale])

    changed = await runner.reclassify_marketplaces()

    assert changed == {CloudProvider.CIVO: 1}
    marketplace = await storage.marketplaces.load(CloudProvider.CIVO)
    assert marketplace is not None
    assert marketplace.software[0].categories == [SoftwareCategory.DEVELOPER_TOOL]


@pytest.mark.db
async def test_the_crawled_products_are_classified(
    runner: CatalogueRunner, factory: MagicMock, storage: Storage
) -> None:
    factory.get.return_value = FakeCrawler([product("Elastic Compute"), product("Acme CRM", "Customer relationship")])

    await runner.run(CloudProvider.AWS)

    catalogue = await storage.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    assert {item.name: item.categories for item in catalogue.products} == {
        "Elastic Compute": [SoftwareCategory.DEVELOPER_TOOL],
        "Acme CRM": [SoftwareCategory.END_USER_SOFTWARE],
    }


@pytest.mark.db
async def test_reclassify_catalogues(runner: CatalogueRunner, storage: Storage) -> None:
    stale = CloudProduct(name="Elastic Compute", description="Virtual machines")
    await storage.catalogues.import_items(CloudProvider.AWS, CRAWLED_AT, [stale])

    changed = await runner.reclassify_catalogues()

    assert changed == {CloudProvider.AWS: 1}
    catalogue = await storage.catalogues.load(CloudProvider.AWS)
    assert catalogue is not None
    assert catalogue.products[0].categories == [SoftwareCategory.DEVELOPER_TOOL]


@pytest.mark.db
async def test_run_statistics(runner: CatalogueRunner, factory: MagicMock, storage: Storage) -> None:
    factory.get_statistics.return_value = FakeCrawler(
        [market_report("2026Q2"), market_report("2026Q1", 128.6), market_report("2026Q2", 143.4)]
    )
    received: List[str] = []

    summary = await runner.run_statistics(on_report=lambda report: received.append(report.period))

    assert (summary.dataset, summary.found) == ("synergy", 2)
    statistics = await storage.statistics.load("synergy")
    assert statistics is not None
    assert [(report.period, report.market_size_bn) for report in statistics.reports] == [
        ("2026Q1", 128.6),
        ("2026Q2", 143.4),
    ]
    assert statistics.source == "Synergy Research Group"
    assert received == ["2026Q2", "2026Q1"]
    factory.get_statistics.assert_called_once_with("synergy")


async def test_empty_statistics_crawl(factory: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    factory.get_statistics.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError):
        await CatalogueRunner(factory=factory).run_statistics()

    assert "The synergy statistics crawl produced no report: the stored statistics are kept." in caplog.messages


async def test_crawl_metrics_keeps_the_sources_with_facts(factory: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    stars: Dict[str, JsonValue] = {"provider": "civo", "repository": "civo/cli", "stars": 3, "source_url": "u"}
    factory.METRICS_MAP = {MetricSource.GITHUB: object, MetricSource.EDGAR: object}
    factory.get_metrics.side_effect = [FakeCrawler([stars]), FakeCrawler([])]

    crawled = await CatalogueRunner(factory=factory).crawl_metrics()

    assert crawled == {MetricSource.GITHUB: [stars]}
    assert [call.args[0] for call in factory.get_metrics.call_args_list] == [MetricSource.GITHUB, MetricSource.EDGAR]
    assert "The edgar metrics crawl produced no fact: its stored measures are kept." in caplog.messages
