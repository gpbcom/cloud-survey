from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator, Dict, List, Mapping, Optional, Sequence, Set
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from analytics.prices.coverage_catalog_reader import CoverageCatalogReader
from analytics.prices.price_collector import PriceCollector
from analytics.prices.prices_run import PricesRun
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.settings.prices_settings import PricesSettings
from models.cloud.prices.stored.price_source import PriceSource
from models.cloud.products.product import CloudProduct
from storage.storage import Storage

pytestmark = pytest.mark.db

SHEET = "https://example.com/prices.csv"
FREE = "https://example.com/free"


class FakePriceCrawler:
    """A crawler in price mode: one source of two prices and a free offer, read once (then unchanged)."""

    def __init__(self, amount: str) -> None:
        self.amount = amount
        self.price_reads: Dict[str, PriceSource] = {}
        self.price_failures: Set[str] = set()
        self.provider = CloudProvider.SCALEWAY

    def use_prices(
        self,
        provider: CloudProvider,
        sources: Mapping[str, PriceSource],
        delay_s: float = 2.0,
        products: Optional[Mapping[str, Optional[str]]] = None,
        pages: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        self.provider = provider
        self.known = dict(sources)
        self.products = dict(products or {})
        self.pages = {name: list(urls) for name, urls in (pages or {}).items()}

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        if SHEET in self.known and self.known[SHEET].version == self.amount:
            self.price_reads[SHEET] = self.known[SHEET].model_copy(update={"status": PriceSourceStatus.UNCHANGED})
            return
        for sku in ("dev1-s", "dev1-m"):
            fact = ServicePrice(
                provider=self.provider,
                sku_key=sku,
                service="Instances",
                region="fr-par-1",
                unit=PriceUnit.HOUR,
                unit_raw="hour",
                price=Decimal(self.amount),
                currency="EUR",
                source_url=SHEET,
                source_kind=PriceSourceKind.API,
            )
            yield {"fact": "price", **fact.model_dump(mode="json")}
        tier = FreeTier(
            provider=self.provider,
            free_key="object-storage",
            service="Object Storage",
            kind="always-free",
            quantity=Decimal(75),
            unit=PriceUnit.GIB_MONTH,
            source_url=SHEET,
            source_kind=PriceSourceKind.PAGE,
        )
        yield {"fact": "free-tier", **tier.model_dump(mode="json")}
        yield {"fact": "unknown"}
        self.price_reads[SHEET] = PriceSource(
            provider=self.provider, source_key=SHEET, version=self.amount, rows=3, status=PriceSourceStatus.FETCHED
        )


@pytest.fixture(autouse=True)
def no_shipped_coverage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Read the curated coverage from an empty folder, not the catalogues shipped in `conf/prices/coverage`."""
    monkeypatch.setattr(CoverageCatalogReader.__init__, "__defaults__", (tmp_path / "coverage", None))


def runner_for(storage: Storage, crawler: FakePriceCrawler) -> CatalogueRunner:
    factory = MagicMock()
    factory.get.return_value = crawler
    return CatalogueRunner(storage=storage, factory=factory)


async def test_a_price_crawl_is_merged_then_skipped_when_unchanged(storage: Storage) -> None:
    settings = PricesSettings(batch_rows=100)

    first = await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), settings).run([CloudProvider.SCALEWAY])
    second = await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), settings).run([CloudProvider.SCALEWAY])
    third = await PricesRun(runner_for(storage, FakePriceCrawler("0.02")), settings).run([CloudProvider.SCALEWAY])

    assert first == {CloudProvider.SCALEWAY: (0, 3)}
    assert second == {CloudProvider.SCALEWAY: (0, 0)}, "an unchanged source is not read, its prices kept"
    assert third == {CloudProvider.SCALEWAY: (2, 2)}
    prices: List[Decimal] = [row.price for row in await storage.prices.list({"provider": ["scaleway"]}) if row.price]
    assert prices == [Decimal("0.02"), Decimal("0.02")]
    assert len(await storage.free_tiers.list({"provider": ["scaleway"]})) == 1
    source = await storage.price_sources.read("scaleway", SHEET)
    assert source is not None
    assert source.version == "0.02"


async def test_a_failed_crawl_keeps_the_stored_prices(storage: Storage) -> None:
    await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), PricesSettings(batch_rows=100)).run(
        [CloudProvider.SCALEWAY]
    )
    broken = FakePriceCrawler("0.05")
    broken.stream = MagicMock(side_effect=OSError("network down"))  # type: ignore[method-assign]
    factory = MagicMock()
    factory.get.return_value = broken

    results = await PricesRun(CatalogueRunner(storage=storage, factory=factory), PricesSettings(batch_rows=100)).run(
        [CloudProvider.SCALEWAY]
    )

    assert results == {CloudProvider.SCALEWAY: (0, 0)}
    assert len(await storage.prices.list({"provider": ["scaleway"]})) == 2


async def test_the_prices_are_linked_to_the_catalogue_product_of_their_service(storage: Storage) -> None:
    async with storage.catalogues.writer(CloudProvider.SCALEWAY, datetime(2026, 10, 1, tzinfo=UTC), 60.0) as writer:
        await writer.add(CloudProduct(name="Scaleway Instances", description="VMs", url="https://scaleway.example/vm"))
        await writer.finish()

    await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), PricesSettings(batch_rows=100)).run(
        [CloudProvider.SCALEWAY]
    )

    rows = await storage.prices.list({"provider": ["scaleway"]})
    assert len(rows) == 2
    assert all(row.product_id is not None for row in rows)


async def test_the_curated_coverage_states_and_links_without_crawling(storage: Storage, tmp_path: Path) -> None:
    async with storage.catalogues.writer(CloudProvider.SCALEWAY, datetime(2026, 10, 1, tzinfo=UTC), 60.0) as writer:
        await writer.add(CloudProduct(name="Compute", description="VMs", url="https://scaleway.example/vm"))
        await writer.add(CloudProduct(name="Scaleway CLI", description="Tool", url="https://scaleway.example/cli"))
        await writer.add(CloudProduct(name="Medium", description="VM", url="https://scaleway.example/m"))
        await writer.finish()
    await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), PricesSettings(batch_rows=100)).run(
        [CloudProvider.SCALEWAY]
    )
    (tmp_path / "scaleway.yaml").write_text(
        "provider: scaleway\ncurrency: EUR\nlinks:\n  Compute: ['^Instances$']\nrow_links:\n  Medium: ['dev1-m ']\n"
        "statements:\n"
        "  - {product: Scaleway CLI, model: free, reason: Open source., source: 'https://scaleway.example/cli'}\n",
        encoding="utf-8",
    )
    collector = PriceCollector(storage)
    collector.coverage = CoverageCatalogReader(tmp_path)

    first = await collector.curate(CloudProvider.SCALEWAY, ["Scaleway "])
    second = await collector.curate(CloudProvider.SCALEWAY, ["Scaleway "])

    assert first == (0, 1, 3)
    assert second == (0, 0, 3)
    assert await storage.prices.coverage("scaleway") == [
        ("Compute", True, False),
        ("Medium", True, False),
        ("Scaleway CLI", True, False),
    ]
    statement = next(row for row in await storage.prices.list({"provider": ["scaleway"]}) if row.price == 0)
    assert (statement.source_url, statement.currency) == ("https://scaleway.example/cli#price-coverage", "EUR")


async def test_a_statement_is_dropped_once_its_product_has_a_crawled_price(storage: Storage, tmp_path: Path) -> None:
    async with storage.catalogues.writer(CloudProvider.SCALEWAY, datetime(2026, 10, 1, tzinfo=UTC), 60.0) as writer:
        await writer.add(CloudProduct(name="Compute", description="VMs", url="https://scaleway.example/vm"))
        await writer.add(CloudProduct(name="Scaleway CLI", description="Tool", url="https://scaleway.example/cli"))
        await writer.finish()
    await PricesRun(runner_for(storage, FakePriceCrawler("0.01")), PricesSettings(batch_rows=100)).run(
        [CloudProvider.SCALEWAY]
    )
    (tmp_path / "scaleway.yaml").write_text(
        "provider: scaleway\ncurrency: EUR\nlinks:\n  Compute: ['^Instances$']\nstatements:\n"
        "  - {product: Compute, model: quote, reason: Contact sales., source: 'https://scaleway.example/vm'}\n"
        "  - {product: Scaleway CLI, model: free, reason: Open source., source: 'https://scaleway.example/cli'}\n",
        encoding="utf-8",
    )
    collector = PriceCollector(storage)
    collector.coverage = CoverageCatalogReader(tmp_path)

    first = await collector.curate(CloudProvider.SCALEWAY, ["Scaleway "])
    second = await collector.curate(CloudProvider.SCALEWAY, ["Scaleway "])

    assert first[:2] == (1, 2), "both statements written, then the one of the crawled product closed"
    assert second[:2] == (0, 0), "a dropped statement is not written again"
    current = await storage.prices.list({"provider": ["scaleway"]})
    assert sorted(row.sku_key for row in current if row.sku_key.startswith("curated/")) == ["curated/Scaleway CLI"]
