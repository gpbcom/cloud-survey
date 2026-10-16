from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue

from catalogue.exception import CatalogueWriteError
from catalogue.store import CatalogueStore
from classifier.exception import ClassificationRulesFileError
from classifier.software_classifier import SoftwareClassifier
from crawler.exception import CrawlerError, EmptyCrawlError, UnknownCrawlerTargetError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, SoftwareCategory, SoftwareType
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct


class FakeCrawler:
    """Stand-in for a crawler, streaming pre-defined items."""

    def __init__(self, items: List[Dict[str, JsonValue]], error: Optional[Exception] = None) -> None:
        self.items = items
        self.error = error

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        for item in self.items:
            yield item
        if self.error:
            raise self.error


def product(name: str) -> Dict[str, JsonValue]:
    return {"name": name, "description": f"{name} description", "pricing_policy": []}


@pytest.fixture
def store(tmp_path: Path) -> CatalogueStore:
    return CatalogueStore(tmp_path / "output")


@pytest.fixture
def factory() -> MagicMock:
    return MagicMock(spec=CrawlerFactory)


@pytest.fixture
def runner(store: CatalogueStore, factory: MagicMock) -> CatalogueRunner:
    return CatalogueRunner(store=store, factory=factory)


def test_defaults() -> None:
    runner = CatalogueRunner()

    assert runner.store.output_dir == Path("output")
    assert isinstance(runner.factory, CrawlerFactory)
    assert runner.logger.name == "crawler.runner"


async def test_crawl_builds_the_catalogue(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get.return_value = FakeCrawler([product("Instances"), product("Object Storage")])
    received: List[Tuple[CloudProvider, str]] = []

    catalogue = await runner.crawl("scaleway", lambda provider, item: received.append((provider, item.name)))

    factory.get.assert_called_once_with("scaleway")
    assert catalogue.provider is CloudProvider.SCALEWAY
    assert catalogue.crawled_at.utcoffset() is not None
    assert catalogue.products == [
        CloudProduct(name="Instances", description="Instances description"),
        CloudProduct(name="Object Storage", description="Object Storage description"),
    ]
    assert received == [(CloudProvider.SCALEWAY, "Instances"), (CloudProvider.SCALEWAY, "Object Storage")]


async def test_run_writes_the_catalogue(runner: CatalogueRunner, factory: MagicMock, store: CatalogueStore) -> None:
    factory.get.return_value = FakeCrawler([product("Amazon EC2")])

    path = await runner.run(CloudProvider.AWS)

    assert path == store.path_for(CloudProvider.AWS)
    loaded = store.load(CloudProvider.AWS)
    assert loaded is not None
    assert [item.name for item in loaded.products] == ["Amazon EC2"]


async def test_empty_crawl_keeps_the_previous_file(
    runner: CatalogueRunner, factory: MagicMock, store: CatalogueStore, caplog: pytest.LogCaptureFixture
) -> None:
    factory.get.return_value = FakeCrawler([product("Amazon EC2")])
    await runner.run(CloudProvider.AWS)
    factory.get.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError) as exc_info:
        await runner.run(CloudProvider.AWS)

    assert exc_info.value.provider == "amazon-web-services"
    assert ("ERROR", "The amazon-web-services crawl produced no product: its file is kept.") in [
        (record.levelname, record.getMessage()) for record in caplog.records
    ]
    loaded = store.load(CloudProvider.AWS)
    assert loaded is not None
    assert [item.name for item in loaded.products] == ["Amazon EC2"]


async def test_unknown_target(store: CatalogueStore) -> None:
    with pytest.raises(UnknownCrawlerTargetError):
        await CatalogueRunner(store=store).run("unknown-cloud")


async def test_crawl_errors_propagate(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get.return_value = FakeCrawler([product("Instances")], error=CrawlerError("blocked"))

    with pytest.raises(CrawlerError, match="blocked"):
        await runner.run(CloudProvider.SCALEWAY)


async def test_run_all_continues_after_a_failure(
    runner: CatalogueRunner, factory: MagicMock, store: CatalogueStore, caplog: pytest.LogCaptureFixture
) -> None:
    outcomes: Dict[CloudProvider, Union[FakeCrawler, Exception]] = {
        CloudProvider.AWS: FakeCrawler([product("Amazon EC2")]),
        CloudProvider.AZURE: FakeCrawler([]),
        CloudProvider.GCP: FakeCrawler([product("Cloud Run")], error=CrawlerError("blocked")),
        CloudProvider.OVH: FakeCrawler([product("Compute")]),
        CloudProvider.SCALEWAY: FakeCrawler([product("Instances")]),
    }
    factory.get.side_effect = lambda provider: outcomes[provider]
    counts: Dict[CloudProvider, int] = {}

    written = await runner.run_all(
        lambda provider, item: counts.update({provider: counts.get(provider, 0) + 1}), list(outcomes)
    )

    assert set(written) == {CloudProvider.AWS, CloudProvider.OVH, CloudProvider.SCALEWAY}
    assert counts == {CloudProvider.AWS: 1, CloudProvider.GCP: 1, CloudProvider.OVH: 1, CloudProvider.SCALEWAY: 1}
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert errors == [
        "The microsoft-azure crawl produced no product: its file is kept.",
        "The microsoft-azure catalogue was not updated: "
        "The microsoft-azure crawl produced no product: its catalogue file is left unchanged.",
        "The google-cloud-platform catalogue was not updated: blocked",
    ]
    assert caplog.records[-1].getMessage() == "3 catalogues written, 2 failed."
    assert caplog.records[-1].levelno == logging.WARNING


async def test_run_all_store_errors_are_skipped(
    runner: CatalogueRunner, factory: MagicMock, store: CatalogueStore, caplog: pytest.LogCaptureFixture
) -> None:
    store.output_dir.parent.mkdir(parents=True, exist_ok=True)
    store.output_dir.write_text("not a folder", encoding="utf-8")
    factory.get.side_effect = lambda provider: FakeCrawler([product("Compute")])

    assert await runner.run_all() == {}
    assert sum(isinstance(record.exc_info, tuple) for record in caplog.records) == 0
    assert caplog.records[-1].getMessage() == "0 catalogues written, 28 failed."


async def test_run_all_success_is_info(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="crawler.runner")
    factory.get.side_effect = lambda provider: FakeCrawler([product("Compute")])

    written = await runner.run_all()

    assert len(written) == len(CloudProvider)
    assert (caplog.records[-1].levelno, caplog.records[-1].getMessage()) == (
        logging.INFO,
        "28 catalogues written, 0 failed.",
    )


def test_store_write_error_type() -> None:
    assert issubclass(CatalogueWriteError, Exception)


def software(name: str, categories: Optional[List[str]] = None) -> Dict[str, JsonValue]:
    labels: List[JsonValue] = list(categories or [])
    return {
        "name": name,
        "description": f"{name} description",
        "url": f"https://marketplace.example.com/{name}",
        "marketplace_categories": labels,
        "categories": ["developer-tool"],
        "types": ["monitoring"],
    }


def test_default_marketplace_store(store: CatalogueStore) -> None:
    assert CatalogueRunner().marketplace_store.output_dir == Path("output") / "marketplaces"
    assert CatalogueRunner(store=store).marketplace_store.output_dir == store.output_dir / "marketplaces"


async def test_marketplace_versions_are_merged(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler(
        [software("grafana", ["Monitoring"]), software("vault"), software("grafana", ["Monitoring", "Analytics"])]
    )
    received: List[Tuple[CloudProvider, str]] = []

    marketplace = await runner.crawl_marketplace("civo", lambda provider, item: received.append((provider, item.name)))

    assert marketplace.provider is CloudProvider.CIVO
    assert [(item.name, item.marketplace_categories) for item in marketplace.software] == [
        ("grafana", ["Monitoring", "Analytics"]),
        ("vault", []),
    ]
    assert received == [(CloudProvider.CIVO, "grafana"), (CloudProvider.CIVO, "vault")]


async def test_run_marketplace_writes_the_file(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])

    path = await runner.run_marketplace(CloudProvider.CIVO)

    assert path == runner.marketplace_store.path_for(CloudProvider.CIVO)
    loaded = runner.marketplace_store.load(CloudProvider.CIVO)
    assert loaded is not None
    assert [item.name for item in loaded.software] == ["grafana"]


async def test_empty_marketplace_is_an_error(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.get_marketplace.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError):
        await runner.run_marketplace(CloudProvider.CIVO)

    assert "The civo marketplace crawl produced no software: its file is kept." in caplog.messages


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
    assert caplog.records[-1].levelno == logging.WARNING


async def test_run_some_marketplaces(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="crawler.runner")
    factory.get_marketplace.side_effect = lambda provider, classifier: FakeCrawler([software("grafana")])

    written = await runner.run_all_marketplaces(providers=[CloudProvider.CIVO])

    assert list(written) == [CloudProvider.CIVO]
    factory.marketplace_providers.assert_not_called()
    assert (caplog.records[-1].levelno, caplog.records[-1].getMessage()) == (
        logging.INFO,
        "1 marketplaces written, 0 failed.",
    )


async def test_marketplace_crawls_share_one_classifier(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])

    await runner.crawl_marketplace(CloudProvider.CIVO)
    await runner.crawl_marketplace(CloudProvider.CIVO)

    classifiers = {id(call.args[1]) for call in factory.get_marketplace.call_args_list}
    assert len(classifiers) == 1
    assert isinstance(runner.classifier, SoftwareClassifier)


async def test_classification_errors_skip_the_marketplace(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.marketplace_providers.return_value = [CloudProvider.CIVO]
    error = ClassificationRulesFileError(Path("rules.yaml"), "the rules are invalid.")

    with patch("crawler.runner.SoftwareClassifier", side_effect=error):
        written = await runner.run_all_marketplaces()

    assert written == {}
    assert any("The civo marketplace was not updated" in message for message in caplog.messages)


def test_reclassify_marketplaces(
    runner: CatalogueRunner,
    make_marketplace: Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace],
    make_software: Callable[..., MarketplaceSoftware],
) -> None:
    stale = make_software("Grafana", [SoftwareType.CRM], [SoftwareCategory.END_USER_SOFTWARE])
    runner.marketplace_store.save(make_marketplace(CloudProvider.CIVO, [stale]))
    runner.marketplace_store.path_for(CloudProvider.AWS).write_text("{", encoding="utf-8")

    written = runner.reclassify_marketplaces()

    assert list(written) == [CloudProvider.CIVO]
    loaded = runner.marketplace_store.load(CloudProvider.CIVO)
    assert loaded is not None
    assert (loaded.software[0].types, loaded.software[0].categories) == (
        [SoftwareType.MONITORING],
        [SoftwareCategory.DEVELOPER_TOOL],
    )


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


def test_default_statistics_store(store: CatalogueStore) -> None:
    assert CatalogueRunner(store=store).statistics_store.output_dir == store.output_dir / "stats"


async def test_run_statistics(runner: CatalogueRunner, factory: MagicMock) -> None:
    crawler = FakeCrawler([market_report("2026Q2"), market_report("2026Q1", 128.6), market_report("2026Q2", 143.4)])
    crawler.source = "Synergy Research Group"  # type: ignore[attr-defined]
    factory.get_statistics.return_value = crawler
    received: List[str] = []

    path = await runner.run_statistics(on_report=lambda report: received.append(report.period))

    assert path == runner.statistics_store.path_for("synergy")
    loaded = runner.statistics_store.load("synergy")
    assert loaded is not None
    assert [(report.period, report.market_size_bn) for report in loaded.reports] == [
        ("2026Q1", 128.6),
        ("2026Q2", 143.4),
    ]
    assert loaded.source == "Synergy Research Group"
    assert received == ["2026Q2", "2026Q1"]
    factory.get_statistics.assert_called_once_with("synergy")


async def test_empty_statistics_crawl(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.get_statistics.return_value = FakeCrawler([])

    with pytest.raises(EmptyCrawlError):
        await runner.run_statistics()

    assert "The synergy statistics crawl produced no report: its file is kept." in caplog.messages


class SlowCrawler(FakeCrawler):
    """Crawler recording how many crawls run at the same time."""

    active = 0
    highest = 0

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        SlowCrawler.active += 1
        SlowCrawler.highest = max(SlowCrawler.highest, SlowCrawler.active)
        await asyncio.sleep(0.01)
        SlowCrawler.active -= 1
        for item in self.items:
            yield item


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


@pytest.mark.parametrize("marketplaces", [False, True])
async def test_crawls_run_in_parallel_within_the_limit(
    store: CatalogueStore, factory: MagicMock, marketplaces: bool
) -> None:
    runner = CatalogueRunner(store=store, factory=factory, concurrency=2)
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


async def test_runs_date_the_catalogue(
    runner: CatalogueRunner, factory: MagicMock, store: CatalogueStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="catalogue.item_history")
    factory.get.return_value = FakeCrawler([product("Amazon EC2"), product("Amazon S3")])
    await runner.run(CloudProvider.AWS)
    factory.get.return_value = FakeCrawler([product("Amazon EC2"), product("AWS Lambda")])

    await runner.run(CloudProvider.AWS)

    loaded = store.load(CloudProvider.AWS)
    assert loaded is not None
    dated = {item.name: item for item in loaded.products}
    assert (dated["Amazon EC2"].added_at, dated["Amazon EC2"].deleted_at) == (None, None)
    assert dated["AWS Lambda"].added_at == loaded.crawled_at
    assert dated["Amazon S3"].deleted_at == loaded.crawled_at
    assert loaded.size == 2
    assert "amazon-web-services catalogue history: 1 added, 0 updated, 1 deleted since the previous crawl." in (
        caplog.messages
    )


async def test_runs_date_the_marketplace(runner: CatalogueRunner, factory: MagicMock) -> None:
    factory.get_marketplace.return_value = FakeCrawler([software("grafana"), software("vault")])
    await runner.run_marketplace(CloudProvider.CIVO)
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])

    await runner.run_marketplace(CloudProvider.CIVO)

    loaded = runner.marketplace_store.load(CloudProvider.CIVO)
    assert loaded is not None
    assert [(item.name, item.is_deleted) for item in loaded.software] == [("grafana", False), ("vault", True)]
    assert loaded.size == 1


@pytest.mark.parametrize("marketplace", [False, True])
async def test_unusable_previous_file_loses_the_history(
    runner: CatalogueRunner, factory: MagicMock, caplog: pytest.LogCaptureFixture, marketplace: bool
) -> None:
    factory.get.return_value = FakeCrawler([product("Instances")])
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])
    target_store = runner.marketplace_store if marketplace else runner.store
    target_store.output_dir.mkdir(parents=True)
    target_store.path_for(CloudProvider.SCALEWAY).write_text("{", encoding="utf-8")

    if marketplace:
        await runner.run_marketplace(CloudProvider.SCALEWAY)
    else:
        await runner.run(CloudProvider.SCALEWAY)

    noun = "marketplace" if marketplace else "catalogue"
    assert any(f"The previous scaleway {noun} is unusable, its history is lost" in m for m in caplog.messages)


@pytest.mark.parametrize("marketplace", [False, True])
async def test_running_crawls_write_the_items_crawled_so_far(
    store: CatalogueStore, factory: MagicMock, marketplace: bool
) -> None:
    runner = CatalogueRunner(store=store, factory=factory, save_interval=0)
    factory.get.return_value = FakeCrawler([product("Old"), product("Kept")])
    factory.get_marketplace.return_value = FakeCrawler([software("old"), software("kept")])
    run = runner.run_marketplace if marketplace else runner.run
    target_store = runner.marketplace_store if marketplace else runner.store
    await run(CloudProvider.CIVO)
    names = ["kept", "new"] if marketplace else ["Kept", "New"]
    factory.get.return_value = FakeCrawler([product(name) for name in names])
    factory.get_marketplace.return_value = FakeCrawler([software(name) for name in names])
    snapshots: List[List[Tuple[str, bool]]] = []
    save = target_store.save

    def recording_save(document: Union[CloudMarketplace, CloudCatalogue]) -> Path:
        items = document.software if isinstance(document, CloudMarketplace) else document.products
        snapshots.append([(item.name, item.is_deleted) for item in items])
        assert document.in_progress == (len(snapshots) < 3)
        return save(document)  # type: ignore[arg-type]

    with patch.object(target_store, "save", side_effect=recording_save):
        await run(CloudProvider.CIVO)

    old = "old" if marketplace else "Old"
    assert snapshots == [
        [(names[0], False), (old, False)],
        [(names[0], False), (names[1], False), (old, False)],
        [(names[0], False), (names[1], False), (old, True)],
    ]


async def test_failing_partial_write_does_not_stop_the_crawl(
    store: CatalogueStore, factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    runner = CatalogueRunner(store=store, factory=factory, save_interval=0)
    factory.get.return_value = FakeCrawler([product("Instances")])
    error = CatalogueWriteError(store.path_for(CloudProvider.SCALEWAY), "the disk is full")

    with patch.object(store, "save", side_effect=[error, store.path_for(CloudProvider.SCALEWAY)]):
        path = await runner.run(CloudProvider.SCALEWAY)

    assert path == store.path_for(CloudProvider.SCALEWAY)
    assert any("The scaleway catalogue crawled so far could not be written" in m for m in caplog.messages)


def test_save_interval_default(store: CatalogueStore) -> None:
    assert CatalogueRunner(store=store).save_interval == CatalogueRunner.SAVE_INTERVAL


@pytest.mark.parametrize("marketplace", [False, True])
async def test_unknown_target_has_no_history(store: CatalogueStore, marketplace: bool) -> None:
    runner = CatalogueRunner(store=store)

    with pytest.raises(UnknownCrawlerTargetError):
        await (runner.run_marketplace if marketplace else runner.run)("unknown-cloud")
