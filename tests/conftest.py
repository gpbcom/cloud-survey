from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Tuple, Union
from unittest.mock import MagicMock, patch

import asyncpg
import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response
from sqlalchemy import text
from sqlalchemy.engine import make_url

from crawler.cloud.base import BaseCloudCrawler
from crawler.markets.catalog_loader import MarketsCatalogLoader
from crawler.metrics.catalog_loader import CollectorCatalogLoader
from crawler.tls.ca_bundle import CaBundle
from gui.paging.identified_row import IdentifiedRow
from gui.paging.page.paged_table_model import PagedTableModel
from gui.storage_bridge.storage_loop import StorageLoop
from models.cloud.dated_item import DatedItem
from models.cloud.enums import (
    CloudProvider,
    DateCaveat,
    DateSource,
    DeliveryMethod,
    MarketPlayer,
    MarketRegion,
    MarketSegment,
    PricingPolicy,
    SoftwareCategory,
)
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace import CloudMarketplace
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.storage.storage_settings import StorageSettings
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.history.chronology import Chronology
from models.markets.markets_catalog import MarketsCatalog
from models.stats.market_report import MarketReport
from models.storage.enums import StorageTable
from scripts.migrate_database import DatabaseMigrator
from storage.storage import Storage

# The GUI tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CRAWLED_AT = datetime(2026, 10, 16, 7, 24, tzinfo=UTC)
# The PostgreSQL server of the `db` tests (`uv run install-stack --test`): without it they are skipped.
TEST_DATABASE_VARIABLE = "STORAGE_TEST_DATABASE_URL"
STORAGE_TABLES = ", ".join(StorageTable)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="Run the live tests, which crawl the real websites.")


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="Live test: run it with `pytest --live`.")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def isolated_ca_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the merged CA bundle of the crawlers in the test folder, and restore the variables it installs."""
    cache_file = tmp_path / "ca-bundle.pem"
    monkeypatch.setattr(CaBundle, "CACHE_FILE", cache_file)
    for variable in (*CaBundle.INSTALLED_VARIABLES, CaBundle.SOURCES_VARIABLE):
        monkeypatch.setenv(variable, os.environ.get(variable, ""))
    return cache_file


@pytest.fixture(autouse=True)
def no_language_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset the language model keys and settings: no test ever calls a paid model."""
    for variable in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CRAWLER_LLM_CONFIG"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(autouse=True)
def stealth_session_cls(request: pytest.FixtureRequest) -> Iterator[MagicMock]:
    """Replace the stealth browser session so no test ever touches a real browser, except the live tests."""
    if request.node.get_closest_marker("live"):
        yield MagicMock()
        return
    with patch("crawler.cloud.base.AsyncStealthySession", autospec=True) as mock_cls:
        yield mock_cls


@pytest.fixture
def make_response() -> Callable[[str, str], Response]:
    """Build an offline scrapling response from a fixture file of `tests/fixtures/crawler`."""

    def build(url: str, fixture: str) -> Response:
        content = (FIXTURES_DIR / "crawler" / fixture).read_bytes()
        return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})

    return build


@pytest.fixture(scope="session")
def metric_catalog() -> CollectorCatalog:
    """The shipped catalogue of where each provider is found at the metric sources (`conf/metrics/collectors.yaml`)."""
    return CollectorCatalogLoader().load()


@pytest.fixture
def metric_page() -> Callable[[str, str, Dict[str, JsonValue]], Response]:
    """Build an offline response from a recorded document of `tests/fixtures/metrics`, with its request meta."""

    def build(url: str, fixture: str, meta: Dict[str, JsonValue]) -> Response:
        content = (FIXTURES_DIR / "metrics" / fixture).read_bytes()
        return Response(
            url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
        )

    return build


@pytest.fixture(scope="session")
def markets_catalog() -> MarketsCatalog:
    """The shipped markets catalogue (`conf/history/markets.yaml`), checked against the chronology."""
    return MarketsCatalogLoader().load()


@pytest.fixture(scope="session")
def markets_chronology() -> Chronology:
    """The shipped chronology naming the companies of the markets catalogue."""
    return MarketsCatalogLoader().chronology()


@pytest.fixture
def market_page() -> Callable[[str, str, Dict[str, JsonValue]], Response]:
    """Build an offline response from a recorded document of `tests/fixtures/markets`, with its request meta."""

    def build(url: str, fixture: str, meta: Dict[str, JsonValue]) -> Response:
        content = (FIXTURES_DIR / "markets" / fixture).read_bytes()
        return Response(
            url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
        )

    return build


@pytest.fixture
def crawl_page() -> Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]:
    """Collect everything a crawler yields for a page: the products and the follow-up requests."""

    async def crawl(crawler: BaseCloudCrawler, response: Response) -> List[Union[Dict[str, JsonValue], Request]]:
        return [result async for result in crawler.parse(response)]

    return crawl


@pytest.fixture
def pricing_payload() -> Dict[str, JsonValue]:
    """A valid raw pricing policy, as it would come out of a scraper."""
    return {
        "pricing_policy": PricingPolicy.BY_RESOURCE.value,
        "free_limit": 10.0,
        "amount": 0.25,
        "currency": "EUR",
    }


@pytest.fixture
def product_payload(pricing_payload: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
    """A valid raw cloud product, as it would come out of a scraper."""
    return {
        "name": "Object Storage",
        "description": "S3 compatible object storage.",
        "pricing_policy": [pricing_payload],
    }


@pytest.fixture
def plain_formatter_payload() -> Dict[str, JsonValue]:
    """The `plain` formatter of `logging_config_payload`."""
    return {"format": "%(levelname)s - %(message)s"}


@pytest.fixture
def console_handler_payload() -> Dict[str, JsonValue]:
    """The `console` handler of `logging_config_payload`."""
    return {"class": "logging.StreamHandler", "formatter": "plain", "stream": "ext://sys.stdout"}


@pytest.fixture
def file_handler_payload(tmp_path: Path) -> Dict[str, JsonValue]:
    """The `file` handler of `logging_config_payload`."""
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "plain",
        "filename": str(tmp_path / "app.log"),
        "maxBytes": 1024,
        "backupCount": 2,
    }


@pytest.fixture
def app_logger_payload() -> Dict[str, JsonValue]:
    """The `app` logger of `logging_config_payload`."""
    return {"level": "info", "handlers": ["file"], "propagate": False}


@pytest.fixture
def root_logger_payload() -> Dict[str, JsonValue]:
    """The root logger of `logging_config_payload`."""
    return {"level": "DEBUG", "handlers": ["console"]}


@pytest.fixture
def logging_config_payload(
    plain_formatter_payload: Dict[str, JsonValue],
    console_handler_payload: Dict[str, JsonValue],
    file_handler_payload: Dict[str, JsonValue],
    app_logger_payload: Dict[str, JsonValue],
    root_logger_payload: Dict[str, JsonValue],
) -> Dict[str, JsonValue]:
    """A minimal valid logging configuration, written with `dictConfig` key names.

    It references the section fixtures: mutating a section fixture mutates this configuration.
    """
    return {
        "version": 1,
        "formatters": {"plain": plain_formatter_payload},
        "handlers": {"console": console_handler_payload, "file": file_handler_payload},
        "loggers": {"app": app_logger_payload},
        "root": root_logger_payload,
    }


@pytest.fixture
def isolated_logging() -> Iterator[None]:
    """Snapshot the global logging state and restore it once the test reconfigured logging."""
    root = logging.getLogger()
    root_state = (root.level, root.handlers[:])
    loggers = {
        name: (logger.level, logger.handlers[:], logger.propagate, logger.disabled)
        for name, logger in logging.Logger.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }

    yield

    for handler in root.handlers:
        if handler not in root_state[1]:
            handler.close()
    root.setLevel(root_state[0])
    root.handlers[:] = root_state[1]
    for name, (level, handlers, propagate, disabled) in loggers.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.disabled = disabled


@pytest.fixture
def make_marketplace() -> Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace]:
    """Build a marketplace of the given software."""

    def build(provider: CloudProvider, software: List[MarketplaceSoftware]) -> CloudMarketplace:
        return CloudMarketplace(provider=provider, crawled_at=CRAWLED_AT, software=software)

    return build


def build_software(
    name: str,
    labels: List[str],
    categories: List[SoftwareCategory],
    delivery: DeliveryMethod = DeliveryMethod.SAAS,
    publisher: str = "ACME",
) -> MarketplaceSoftware:
    """Build a marketplace software."""
    return MarketplaceSoftware(
        name=name,
        description=f"{name} description",
        publisher=publisher,
        url=f"https://marketplace.example.com/{name.casefold().replace(' ', '-')}",
        delivery=delivery,
        marketplace_categories=labels,
        categories=categories,
    )


@pytest.fixture
def make_software() -> Callable[..., MarketplaceSoftware]:
    """Build a marketplace software: name, marketplace labels, audiences, then optionally the delivery and publisher."""
    return build_software


def build_report(
    label: str,
    top_shares: List[Tuple[MarketPlayer, float]],
    region: MarketRegion = MarketRegion.WORLDWIDE,
    segment: MarketSegment = MarketSegment.CLOUD_INFRASTRUCTURE,
    **fields: JsonValue,
) -> MarketReport:
    """Build a market report with top-level shares, the other fields given as JSON values."""
    values: Dict[str, JsonValue] = {
        "period": label,
        "region": region.value,
        "segment": segment.value,
        "shares": [{"player": player.value, "share_pct": pct} for player, pct in top_shares],
        "source_url": f"https://www.srgresearch.com/articles/{label.casefold()}",
        "title": f"Cloud market {label}",
        "published": "2026-07-30",
    }
    values.update(fields)
    return MarketReport.model_validate(values)


@pytest.fixture
def make_report() -> Callable[..., MarketReport]:
    """Build a market report: period, (player, share) pairs, then optionally the region, segment and other fields."""
    return build_report


@pytest.fixture
def make_catalogue() -> Callable[[CloudProvider, List[str]], CloudCatalogue]:
    """Build a catalogue of products named after the given names."""

    def build(provider: CloudProvider, names: List[str]) -> CloudCatalogue:
        products = [CloudProduct(name=name, description=f"{name} description") for name in names]
        return CloudCatalogue(provider=provider, crawled_at=CRAWLED_AT, products=products)

    return build


async def run_on_server(url: str, statement: str) -> None:
    """Run a statement on the maintenance database of the test server (creating or dropping a database)."""
    server = make_url(url).set(drivername="postgresql", database="postgres")
    connection = await asyncpg.connect(server.render_as_string(hide_password=False))
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create a throw-away database migrated to the head revision, one per test worker, dropped at the end."""
    base = os.getenv(TEST_DATABASE_VARIABLE, "").strip()
    if not base:
        pytest.skip(f"Database test: set {TEST_DATABASE_VARIABLE} (see `uv run install-stack --test`).")
    name = f"poc_crawler_test_{uuid.uuid4().hex[:12]}"
    # From template0, which no session uses: concurrent test runs never wait for each other.
    asyncio.run(run_on_server(base, f'CREATE DATABASE "{name}" TEMPLATE template0'))
    url = make_url(base).set(database=name).render_as_string(hide_password=False)
    try:
        DatabaseMigrator(StorageSettings(url=url)).upgrade()
        yield url
    finally:
        asyncio.run(run_on_server(base, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def storage_settings(database_url: str) -> StorageSettings:
    """The settings of the test database, with small batches so that the tests write several of them."""
    return StorageSettings(url=database_url, pool_size=2, max_overflow=8, batch_size=3)


@pytest.fixture
async def storage(storage_settings: StorageSettings) -> AsyncIterator[Storage]:
    """An open storage on an empty test database."""
    async with Storage(storage_settings) as opened:
        async with opened.database.connect() as connection:
            await connection.execute(text(f"TRUNCATE {STORAGE_TABLES} RESTART IDENTITY CASCADE"))
            await connection.commit()
        yield opened


@pytest.fixture
def gui_loop(storage: Storage, storage_settings: StorageSettings) -> Iterator[StorageLoop]:
    """The storage thread of the GUI, on the emptied test database (seeded through `storage`)."""
    loop = StorageLoop(Storage(storage_settings))
    yield loop
    loop.stop()


def build_product(name: str, deleted: bool = False, caveat: bool = False) -> CloudProduct:
    """Build a product added a week before the crawl, optionally deleted or with an approximate date."""
    return CloudProduct(
        name=name,
        description=f"{name} description",
        url=f"https://cloud.example/{name.casefold().replace(' ', '-')}",
        added_at=CRAWLED_AT - timedelta(days=7),
        added_from=DateSource.WEBSITE,
        added_caveat=DateCaveat.YEAR_ONLY if caveat else None,
        deleted_at=CRAWLED_AT if deleted else None,
    )


async def seed_catalogue(storage: Storage, provider: CloudProvider, products: List[CloudProduct]) -> None:
    """Store a catalogue as it is, with the dates of its products."""
    await storage.catalogues.import_items(provider, CRAWLED_AT, products)


async def seed_marketplace(storage: Storage, provider: CloudProvider, software: List[MarketplaceSoftware]) -> None:
    """Store a marketplace as it is, with the dates of its software."""
    await storage.marketplaces.import_items(provider, CRAWLED_AT, software)


def fill_table[T: DatedItem, R: IdentifiedRow](table: PagedTableModel[T, R], rows: List[R]) -> None:
    """Show rows in a paged table without the storage: they are put in its cache, as read."""
    table._resize(len(rows))
    for start in range(0, max(len(rows), 1), table.PAGE_SIZE):
        table.cache.store(start // table.PAGE_SIZE, rows[start : start + table.PAGE_SIZE])


@pytest.fixture
def offline_loop() -> Iterator[StorageLoop]:
    """A storage thread of the GUI which is never started: the tables are filled by `fill_table`."""
    loop = StorageLoop(Storage(StorageSettings()))
    yield loop
    loop.stop()
