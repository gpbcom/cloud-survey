from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytestqt.qtbot import QtBot

from catalogue.exception import CatalogueWriteError
from crawler.exception import CrawlerError
from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner, ProductCallback, SoftwareCallback
from gui.crawl_worker import CrawlWorker
from models.cloud.enums import CloudProvider, Country, SoftwareCategory, SoftwareType
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct


class FakeRunner(CatalogueRunner):
    """Runner announcing pre-defined products, without crawling."""

    def __init__(self, products: Dict[CloudProvider, List[str]], error: Optional[Exception] = None) -> None:
        super().__init__()
        self.products = products
        self.error = error

    async def run(self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None) -> Path:
        provider = CloudProvider(target)
        for name in self.products.get(provider, []):
            if on_product:
                on_product(provider, CloudProduct(name=name, description="Description"))
        if self.error:
            raise self.error
        return Path("output") / f"{provider.value}.json"

    async def run_all(
        self, on_product: Optional[ProductCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        targets = [provider for provider in self.products if providers is None or provider in providers]
        return {provider: await self.run(provider, on_product) for provider in targets}


def test_single_provider_crawl(qtbot: QtBot) -> None:
    worker = CrawlWorker(FakeRunner({CloudProvider.SCALEWAY: ["Instances", "Object Storage"]}), CloudProvider.SCALEWAY)

    with qtbot.waitSignals([worker.succeeded, worker.stopped]) as signals, qtbot.assertNotEmitted(worker.failed):
        worker.run()

    assert list(signals.all_signals_and_args[0].args) == [
        f"2 scaleway products written to {Path('output') / 'scaleway.json'}"
    ]
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
        ({provider: ["Compute"] for provider in CloudProvider}, "28 catalogues updated"),
        ({CloudProvider.AWS: ["Amazon EC2"]}, "1 catalogues updated, 27 failed (see the logs)"),
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
        (CatalogueWriteError(Path("output/aws.json"), "Permission denied"), "Cannot write the catalogue"),
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
    ) -> Path:
        provider = CloudProvider(target)
        for name in self.products.get(provider, []):
            if on_software:
                listing = MarketplaceSoftware(
                    name=name,
                    description="Description",
                    categories=[SoftwareCategory.DEVELOPER_TOOL],
                    types=[SoftwareType.MONITORING],
                )
                on_software(provider, listing)
        return Path("output") / "marketplaces" / f"{provider.value}.json"

    async def run_all_marketplaces(
        self, on_software: Optional[SoftwareCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        targets = [provider for provider in self.products if providers is None or provider in providers]
        return {provider: await self.run_marketplace(provider, on_software) for provider in targets}


def test_single_marketplace_crawl(qtbot: QtBot) -> None:
    runner = FakeMarketplaceRunner({CloudProvider.CIVO: ["Grafana", "Vault"]}, [CloudProvider.CIVO])
    worker = CrawlWorker(runner, CloudProvider.CIVO, source=CrawlWorker.MARKETPLACE)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [f"2 civo software written to {Path('output') / 'marketplaces' / 'civo.json'}"]


@pytest.mark.parametrize(
    ("country", "summary"),
    [(None, "1 marketplaces updated, 1 failed (see the logs)"), (Country.UNITED_KINGDOM, "1 marketplaces updated")],
)
def test_several_marketplaces_crawl(qtbot: QtBot, country: Optional[Country], summary: str) -> None:
    runner = FakeMarketplaceRunner({CloudProvider.CIVO: ["Grafana"]}, [CloudProvider.AWS, CloudProvider.CIVO])
    worker = CrawlWorker(runner, None, country=country, source=CrawlWorker.MARKETPLACE)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [summary]


def test_chosen_marketplaces_crawl(qtbot: QtBot, caplog: pytest.LogCaptureFixture) -> None:
    runner = FakeMarketplaceRunner(
        {CloudProvider.CIVO: ["Grafana"], CloudProvider.AWS: ["Datadog"]}, [CloudProvider.AWS, CloudProvider.CIVO]
    )
    caplog.set_level(logging.INFO, logger="gui.crawl_worker")
    worker = CrawlWorker(runner, None, source=CrawlWorker.MARKETPLACE, providers=[CloudProvider.CIVO])

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == ["1 marketplaces updated"]
    assert worker.counts == {CloudProvider.CIVO: 1}
    assert "Background crawl of civo (marketplace) started." in caplog.messages


def test_statistics_crawl(qtbot: QtBot) -> None:
    runner = FakeRunner({})
    runner.run_statistics = AsyncMock(return_value=Path("output") / "stats" / "synergy.json")  # type: ignore[method-assign]
    worker = CrawlWorker(runner, None, source=CrawlWorker.STATISTICS)

    with qtbot.waitSignal(worker.succeeded) as signal:
        worker.run()

    assert signal.args == [f"market statistics written to {Path('output') / 'stats' / 'synergy.json'}"]
