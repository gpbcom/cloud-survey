from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import TracebackType
from typing import Dict, List, Optional, Tuple, Type, Union
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import JsonValue
from pytestqt.qtbot import QtBot

from analytics.companies.companies_run import CompaniesRun
from analytics.markets.markets_collector import MarketsCollector
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner, FactSink, ProductCallback, SoftwareCallback
from gui.crawl_worker import CrawlWorker
from models.cloud.enums import CloudProvider, Country, SoftwareCategory
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.companies.enums import CompanyFeed
from models.configuration.storage.storage_settings import StorageSettings
from models.curated.enums import CuratedFile
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.markets_catalog import MarketsCatalog
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus, DatasetKind
from storage.exception import StorageWriteError
from storage.repositories.curated.catalog_provider import CatalogProvider
from storage.storage import Storage


class OfflineCatalogs(CatalogProvider):
    """The curated catalogues of the bundle, as a database never seeded gives them."""

    async def _revisions(self, *files: CuratedFile) -> Optional[Tuple[int, ...]]:
        return None


class OfflineStorage(Storage):
    """Storage opened and closed without a database: the fake runners write nothing."""

    def __init__(self, settings: StorageSettings) -> None:
        super().__init__(settings)
        self.catalogs = OfflineCatalogs(
            self.curated_state,
            self.curated_records,
            self.company_profiles,
            self.company_identifiers,
            self.reported_companies,
            self.reported_years,
            self.reported_events,
            self.launches,
        )

    async def __aenter__(self) -> Storage:
        return self

    async def __aexit__(
        self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException], traceback: Optional[TracebackType]
    ) -> None:
        return None


def summary(kind: DatasetKind, dataset: str, found: int) -> CrawlSummary:
    return CrawlSummary(
        crawl_id=1,
        kind=kind,
        dataset=dataset,
        status=CrawlStatus.SUCCEEDED,
        started_at=datetime.now(UTC),
        found=found,
        added=found,
    )


class FakeRunner(CatalogueRunner):
    """Runner announcing pre-defined products, without crawling."""

    def __init__(self, products: Dict[CloudProvider, List[str]], error: Optional[Exception] = None) -> None:
        super().__init__(storage=OfflineStorage(StorageSettings()))
        self.products = products
        self.error = error

    async def run(
        self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None
    ) -> CrawlSummary:
        provider = CloudProvider(target)
        for name in self.products.get(provider, []):
            if on_product:
                on_product(provider, CloudProduct(name=name, description="Description"))
        if self.error:
            raise self.error
        return summary(DatasetKind.CATALOGUE, provider.value, len(self.products.get(provider, [])))

    async def run_all(
        self, on_product: Optional[ProductCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, CrawlSummary]:
        targets = [provider for provider in self.products if providers is None or provider in providers]
        return {provider: await self.run(provider, on_product) for provider in targets}


def test_single_provider_crawl(qtbot: QtBot) -> None:
    worker = CrawlWorker(FakeRunner({CloudProvider.SCALEWAY: ["Instances", "Object Storage"]}), CloudProvider.SCALEWAY)

    with qtbot.waitSignals([worker.succeeded, worker.stopped]) as signals, qtbot.assertNotEmitted(worker.failed):
        worker.run()

    assert list(signals.all_signals_and_args[0].args) == ["2 scaleway products written (2 added, 0 updated, 0 deleted)"]
    assert worker.counts == {CloudProvider.SCALEWAY: 2}


def test_progress_is_emitted(qtbot: QtBot) -> None:
    worker = CrawlWorker(FakeRunner({CloudProvider.AWS: ["Amazon EC2", "Amazon S3"]}), CloudProvider.AWS)
    progress: List[List[Union[str, int]]] = []
    worker.product_crawled.connect(lambda provider, count: progress.append([provider, count]))

    worker.run()

    assert progress == [["amazon-web-services", 1], ["amazon-web-services", 2]]


@pytest.mark.parametrize(
    ("products", "summary"),
    [
        ({provider: ["Compute"] for provider in CloudProvider}, "32 catalogues updated"),
        ({CloudProvider.AWS: ["Amazon EC2"]}, "1 catalogues updated, 31 failed (see the logs)"),
    ],
)
def test_all_providers_crawl(qtbot: QtBot, products: Dict[CloudProvider, List[str]], summary: str) -> None:
    worker = CrawlWorker(FakeRunner(products), None)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [summary]


def test_country_crawl(qtbot: QtBot, caplog: pytest.LogCaptureFixture) -> None:
    runner = FakeRunner({CloudProvider.CIVO: ["Kubernetes"], CloudProvider.AWS: ["Amazon EC2"]})
    worker = CrawlWorker(runner, None, country=Country.UNITED_KINGDOM)
    caplog.set_level(logging.INFO, logger="gui.crawl_worker")

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["1 catalogues updated, 1 failed (see the logs)"]
    assert worker.counts == {CloudProvider.CIVO: 1}
    assert "Background crawl of gb (catalogue) started." in caplog.messages


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (CrawlerError("blocked"), "blocked"),
        (StorageWriteError("aws catalogue", "disk full"), "Cannot write the aws catalogue"),
        (RuntimeError("browser crashed"), "Unexpected error: RuntimeError('browser crashed')"),
    ],
)
def test_failed_crawl(qtbot: QtBot, error: Exception, message: str) -> None:
    worker = CrawlWorker(FakeRunner({CloudProvider.AWS: ["Amazon EC2"]}, error=error), CloudProvider.AWS)

    with qtbot.waitSignals([worker.failed, worker.stopped]) as signals, qtbot.assertNotEmitted(worker.succeeded):
        worker.run()

    assert message in signals.all_signals_and_args[0].args[0]


class FakeMarketplaceRunner(FakeRunner):
    """Runner announcing pre-defined marketplace software, without crawling."""

    def __init__(self, products: Dict[CloudProvider, List[str]], marketplace_providers: List[CloudProvider]) -> None:
        super().__init__(products)
        self.factory = MagicMock(spec=CrawlerFactory)
        self.factory.marketplace_providers.return_value = marketplace_providers

    async def run_marketplace(
        self, target: Union[CloudProvider, str], on_software: Optional[SoftwareCallback] = None
    ) -> CrawlSummary:
        provider = CloudProvider(target)
        for name in self.products.get(provider, []):
            if on_software:
                listing = MarketplaceSoftware(
                    name=name,
                    description="Description",
                    categories=[SoftwareCategory.DEVELOPER_TOOL],
                )
                on_software(provider, listing)
        return summary(DatasetKind.MARKETPLACE, provider.value, len(self.products.get(provider, [])))

    async def run_all_marketplaces(
        self, on_software: Optional[SoftwareCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, CrawlSummary]:
        targets = [provider for provider in self.products if providers is None or provider in providers]
        return {provider: await self.run_marketplace(provider, on_software) for provider in targets}


def test_single_marketplace_crawl(qtbot: QtBot) -> None:
    runner = FakeMarketplaceRunner({CloudProvider.CIVO: ["Grafana", "Vault"]}, [CloudProvider.CIVO])
    worker = CrawlWorker(runner, CloudProvider.CIVO, source=CrawlSource.MARKETPLACE)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["2 civo software written (2 added, 0 updated, 0 deleted)"]


@pytest.mark.parametrize(
    ("country", "summary"),
    [(None, "1 marketplaces updated, 1 failed (see the logs)"), (Country.UNITED_KINGDOM, "1 marketplaces updated")],
)
def test_several_marketplaces_crawl(qtbot: QtBot, country: Optional[Country], summary: str) -> None:
    runner = FakeMarketplaceRunner({CloudProvider.CIVO: ["Grafana"]}, [CloudProvider.AWS, CloudProvider.CIVO])
    worker = CrawlWorker(runner, None, country=country, source=CrawlSource.MARKETPLACE)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [summary]


def test_chosen_marketplaces_crawl(qtbot: QtBot, caplog: pytest.LogCaptureFixture) -> None:
    runner = FakeMarketplaceRunner(
        {CloudProvider.CIVO: ["Grafana"], CloudProvider.AWS: ["Datadog"]}, [CloudProvider.AWS, CloudProvider.CIVO]
    )
    caplog.set_level(logging.INFO, logger="gui.crawl_worker")
    worker = CrawlWorker(runner, None, source=CrawlSource.MARKETPLACE, providers=[CloudProvider.CIVO])

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["1 marketplaces updated"]
    assert worker.counts == {CloudProvider.CIVO: 1}
    assert "Background crawl of civo (marketplace) started." in caplog.messages


def test_statistics_crawl(qtbot: QtBot) -> None:
    runner = FakeRunner({})
    runner.run_statistics = AsyncMock(return_value=summary(DatasetKind.STATISTICS, "synergy", 12))  # type: ignore[method-assign]
    worker = CrawlWorker(runner, None, source=CrawlSource.STATISTICS)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["12 market reports written"]


def test_markets_crawl_streams_each_source_then_derives(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = FakeRunner({})
    streamed: List[MarketFeed] = []

    async def stream_markets(
        feed: MarketFeed, sink: FactSink, catalog: Optional[MarketsCatalog], scope: Optional[CrawlScope]
    ) -> int:
        streamed.append(feed)
        return 10

    finish = AsyncMock(return_value=5)
    runner.stream_markets = stream_markets  # type: ignore[method-assign, assignment]
    monkeypatch.setattr(MarketsCollector, "finish", finish)
    worker = CrawlWorker(runner, None, source=CrawlSource.MARKETS, feeds=[MarketFeed.STATCOUNTER, MarketFeed.IDC])

    with qtbot.waitSignal(worker.succeeded) as blocker:
        worker.run()

    assert streamed == [MarketFeed.WORLD_BANK, MarketFeed.STATCOUNTER, MarketFeed.IDC], "the weights join StatCounter"
    assert blocker.args == ["35 markets rows written from worldbank, statcounter, idc"]
    finish.assert_awaited_once_with(streamed)


def history_runner(
    monkeypatch: pytest.MonkeyPatch, products: Optional[Dict[CloudProvider, List[str]]] = None
) -> FakeRunner:
    runner = FakeRunner(products or {})
    runner.run_statistics = AsyncMock(return_value=summary(DatasetKind.STATISTICS, "synergy", 12))  # type: ignore[method-assign]
    runner.storage.refresh_metrics = AsyncMock(return_value=9)  # type: ignore[method-assign]
    monkeypatch.setattr(MarketsCollector, "write_stored_shares", AsyncMock(return_value=7))
    return runner


def test_market_history_crawl_derives_the_shares_and_metrics(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = history_runner(monkeypatch)
    worker = CrawlWorker(runner, None, source=CrawlSource.STATISTICS, market_history=True)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["12 market reports written, 7 market shares and 9 provider metrics derived"]
    runner.storage.refresh_metrics.assert_awaited_once()  # type: ignore[attr-defined]


def test_market_history_without_new_report_derives_from_the_stored_one(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = history_runner(monkeypatch)
    runner.run_statistics = AsyncMock(side_effect=EmptyCrawlError("synergy"))  # type: ignore[method-assign]
    worker = CrawlWorker(runner, None, source=CrawlSource.STATISTICS, market_history=True)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["no new market report, 7 market shares and 9 provider metrics derived"]


def test_statistics_crawl_without_report_fails(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = history_runner(monkeypatch)
    runner.run_statistics = AsyncMock(side_effect=EmptyCrawlError("synergy"))  # type: ignore[method-assign]
    worker = CrawlWorker(runner, None, source=CrawlSource.STATISTICS)

    with qtbot.waitSignal(worker.failed), qtbot.assertNotEmitted(worker.succeeded):
        worker.run()

    runner.storage.refresh_metrics.assert_not_awaited()  # type: ignore[attr-defined]


def test_compounding_crawl_runs_the_catalogues_then_the_history(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    products = {CloudProvider.AWS: ["Amazon EC2"], CloudProvider.SCALEWAY: ["Instances"], CloudProvider.CIVO: ["K8s"]}
    runner = history_runner(monkeypatch, products)
    worker = CrawlWorker(runner, None, providers=[CloudProvider.AWS, CloudProvider.SCALEWAY], market_history=True)
    caplog.set_level(logging.INFO, logger="gui.crawl_worker")

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [
        "2 catalogues updated, 12 market reports written, 7 market shares and 9 provider metrics derived"
    ]
    assert worker.counts == {CloudProvider.AWS: 1, CloudProvider.SCALEWAY: 1}
    assert "Background crawl of amazon-web-services, scaleway (catalogue, market history) started." in caplog.messages


def test_chosen_catalogues_crawl(qtbot: QtBot) -> None:
    runner = FakeRunner({CloudProvider.AWS: ["Amazon EC2"], CloudProvider.CIVO: ["K8s"]})
    worker = CrawlWorker(runner, None, providers=[CloudProvider.AWS, CloudProvider.EXOSCALE])

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["1 catalogues updated, 1 failed (see the logs)"]
    assert worker.counts == {CloudProvider.AWS: 1}


def test_a_companies_crawl_reads_the_companies_picked_and_streams_its_batches(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = AsyncMock(return_value=12)
    monkeypatch.setattr("gui.crawl_worker.CompaniesRun.run", run)
    worker = CrawlWorker(
        FakeRunner({}), None, source=CrawlSource.COMPANIES, company_feeds=[CompanyFeed.OPENALEX], companies=["opera"]
    )
    batches: List[Tuple[str, int, int]] = []
    worker.company_batch.connect(lambda feed, items, rows: batches.append((feed, len(items), rows)))

    with qtbot.waitSignal(worker.succeeded) as blocker:
        worker.run()

    call = run.await_args
    assert call is not None
    feeds, scope = call.args
    assert feeds == [CompanyFeed.OPENALEX]
    assert scope.companies == ["opera"]
    assert call.kwargs["batch_size"] == CrawlWorker.STREAM_BATCH
    call.kwargs["observer"](CompanyFeed.OPENALEX, [{"kind": "paper"}], 1)
    assert batches == [("openalex", 1, 1)]
    assert blocker.args == ["12 companies rows written from openalex"]


def test_a_stopped_companies_crawl_says_so(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gui.crawl_worker.CompaniesRun.run", AsyncMock(return_value=3))
    worker = CrawlWorker(FakeRunner({}), None, source=CrawlSource.COMPANIES, company_feeds=[CompanyFeed.OPENALEX])

    worker.request_stop()
    with qtbot.waitSignal(worker.succeeded) as blocker:
        worker.run()

    assert worker.stop_event.is_set()
    assert blocker.args == ["3 companies rows written from openalex (stopped)"]


def test_a_refused_companies_crawl_says_why(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    async def refused(self: CompaniesRun, *args: JsonValue, **kwargs: JsonValue) -> int:
        self.refusals = {CompanyFeed.GOOGLE_PATENTS: "Google Patents refused the search (HTTP 429)"}
        return 4

    monkeypatch.setattr("gui.crawl_worker.CompaniesRun.run", refused)
    worker = CrawlWorker(FakeRunner({}), None, source=CrawlSource.COMPANIES, company_feeds=[CompanyFeed.GOOGLE_PATENTS])

    with qtbot.waitSignal(worker.succeeded) as blocker:
        worker.run()

    assert blocker.args == [
        "4 companies rows written from google-patents. Google Patents refused the search (HTTP 429) (refused)"
    ]
