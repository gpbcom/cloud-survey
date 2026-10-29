from __future__ import annotations

import logging
import runpy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import JsonValue

import main as main_module
from crawler.exception import CrawlerError
from models.cloud.enums import CloudProvider
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.cloud.products.catalogue import CloudCatalogue
from models.companies.enums import CompanyFeed
from models.drivers.enums import MetricSource
from storage.storage import Storage

MAIN_PATH = Path(main_module.__file__)


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

    def use_launches(self, catalog: LaunchCatalog) -> None:
        self.launches = catalog


def product(name: str) -> Dict[str, JsonValue]:
    return {"name": name, "description": f"{name} description", "pricing_policy": []}


def software(name: str) -> Dict[str, JsonValue]:
    return {
        "name": name,
        "description": f"{name} description",
        "url": f"https://marketplace.example.com/{name}",
        "categories": ["developer-tool"],
        "marketplace_categories": ["monitoring"],
    }


def report() -> Dict[str, JsonValue]:
    return {
        "period": "2026Q2",
        "region": "worldwide",
        "segment": "cloud-infrastructure-services",
        "source_url": "https://www.srgresearch.com/articles/q2",
        "title": "Q2",
        "published": "2026-07-30",
    }


@pytest.fixture(autouse=True)
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in a temporary directory, without crawl variables."""
    monkeypatch.chdir(tmp_path)
    for variable in ("CRAWLER_SOURCE", "CRAWLER_TARGET", "CRAWLER_IMPORT_DIR", "CRAWLER_IMPORT_REPLACE"):
        monkeypatch.delenv(variable, raising=False)
    return tmp_path


@pytest.fixture
def database(storage: Storage, database_url: str, monkeypatch: pytest.MonkeyPatch) -> Storage:
    """Point the program at the (emptied) test database, the `storage` fixture reading it."""
    monkeypatch.setenv("CRAWLER_DATABASE_URL", database_url)
    return storage


@pytest.fixture
def caplog_info(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="main")
    return caplog


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    factory_cls = MagicMock()
    monkeypatch.setattr(main_module, "CrawlerFactory", factory_cls)
    return factory_cls.return_value


def last_message(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    return [record for record in caplog.records if record.name == "main"][-1]


@pytest.mark.parametrize("source", [None, "marketplace", "both"])
async def test_no_target_defined(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, source: Optional[str]
) -> None:
    if source:
        monkeypatch.setenv("CRAWLER_SOURCE", source)

    await main_module.main()

    assert (last_message(caplog_info).levelno, last_message(caplog_info).getMessage()) == (
        logging.ERROR,
        "No target defined.",
    )
    factory.get.assert_not_called()


async def test_unknown_source_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_SOURCE", "Pricing")

    await main_module.main()

    assert last_message(caplog_info).getMessage() == (
        "Unknown crawl source 'pricing': "
        "CRAWLER_SOURCE must be one of catalogue, marketplace, both, reclassify, statistics, import-json, translate, "
        "correspond, metrics, markets, launch-dates, companies, prices, price-coverage."
    )
    factory.get.assert_not_called()


async def test_an_unavailable_storage_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_DATABASE_URL", "postgresql+asyncpg://u:secret@127.0.0.1:9/nowhere")

    await main_module.main()

    record = last_message(caplog_info)
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("The storage is unavailable: Cannot use the database")
    assert "secret" not in record.getMessage()


def test_script_entrypoint_sets_up_logging_and_runs_main(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture
) -> None:
    setup_logging = MagicMock()
    monkeypatch.setattr("logger.setup_logging", setup_logging)
    caplog_info.set_level(logging.INFO, logger="__main__")

    runpy.run_path(str(MAIN_PATH), run_name="__main__")

    setup_logging.assert_called_once_with()
    assert "No target defined." in caplog_info.messages


def test_importing_main_does_not_set_up_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_logging = MagicMock()
    monkeypatch.setattr("logger.setup_logging", setup_logging)

    runpy.run_path(str(MAIN_PATH), run_name="not_main")

    setup_logging.assert_not_called()


@pytest.mark.db
@pytest.mark.parametrize("source", [None, " "])
async def test_writes_the_target_catalogue(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    source: Optional[str],
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    if source is not None:
        monkeypatch.setenv("CRAWLER_SOURCE", source)
    factory.get.return_value = FakeCrawler([product("Instances")])

    await main_module.main()

    catalogue = await database.catalogues.load(CloudProvider.SCALEWAY)
    assert catalogue is not None
    assert [item.name for item in catalogue.products] == ["Instances"]
    assert (
        last_message(caplog_info)
        .getMessage()
        .startswith("The scaleway catalogue has been written (crawl 1: 1 products")
    )
    factory.get_marketplace.assert_not_called()


@pytest.mark.db
async def test_writes_every_catalogue(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    factory.get.side_effect = lambda provider: FakeCrawler([product("Compute")])

    await main_module.main()

    assert len(await database.datasets.list()) == len(CloudProvider)
    assert last_message(caplog_info).getMessage() == f"32 catalogues written to {database.url}."


@pytest.mark.db
async def test_translate_without_a_model_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    tmp_path: Path,
) -> None:
    settings = tmp_path / "llm.yaml"
    settings.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CRAWLER_SOURCE", "translate")
    monkeypatch.setenv("CRAWLER_LLM_CONFIG", str(settings))

    await main_module.main()

    messages = [record.getMessage() for record in caplog_info.records]
    assert "0 labels translated, 0 items categorized by the language model." in messages
    assert last_message(caplog_info).getMessage() == "0 services matched with their equivalents by the language model."


@pytest.mark.db
@pytest.mark.usefixtures("database")
async def test_metrics_are_computed_without_a_target(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "metrics")
    stars: Dict[str, JsonValue] = {"provider": "scaleway", "repository": "a/b", "stars": 4, "source_url": "u"}
    crawl = AsyncMock(return_value={MetricSource.GITHUB: [stars]})
    monkeypatch.setattr(main_module.CatalogueRunner, "crawl_metrics", crawl)

    await main_module.main()

    assert last_message(caplog_info).getMessage().endswith("provider metrics computed again.")
    crawl.assert_awaited_once()
    factory.get.assert_not_called()


@pytest.mark.db
@pytest.mark.usefixtures("database")
async def test_correspond_without_a_model_does_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, tmp_path: Path
) -> None:
    settings = tmp_path / "llm.yaml"
    settings.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CRAWLER_SOURCE", "correspond")
    monkeypatch.setenv("CRAWLER_LLM_CONFIG", str(settings))

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "0 services matched with their equivalents by the language model."
    factory.get.assert_not_called()
    factory.get_marketplace.assert_not_called()


@pytest.mark.db
async def test_broken_language_model_settings_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    tmp_path: Path,
) -> None:
    settings = tmp_path / "llm.yaml"
    settings.write_text("batch_size: 0\n", encoding="utf-8")
    monkeypatch.setenv("CRAWLER_SOURCE", "translate")
    monkeypatch.setenv("CRAWLER_LLM_CONFIG", str(settings))

    await main_module.main()

    record = last_message(caplog_info)
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("The language model tasks stopped:")


@pytest.mark.db
@pytest.mark.parametrize(
    ("crawler", "message", "level"),
    [
        (FakeCrawler([]), "No product fetched from target: scaleway (see the crawl errors above).", logging.WARNING),
        (FakeCrawler([], CrawlerError("blocked")), "The following target is unavailable: scaleway", logging.ERROR),
        (FakeCrawler([], RuntimeError("boom")), "The crawl of the target scaleway failed unexpectedly.", logging.ERROR),
    ],
)
async def test_catalogue_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    crawler: FakeCrawler,
    message: str,
    level: int,
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    factory.get.return_value = crawler

    await main_module.main()

    assert (last_message(caplog_info).levelno, last_message(caplog_info).getMessage()) == (level, message)


@pytest.mark.db
async def test_no_catalogue_written_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    factory.get.side_effect = lambda provider: FakeCrawler([])

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "No catalogue written (see the crawl errors above)."


@pytest.mark.db
async def test_writes_the_target_and_every_marketplace(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    factory.get_marketplace.side_effect = lambda provider, classifier: FakeCrawler([software("grafana")])
    factory.marketplace_providers.return_value = [CloudProvider.CIVO, CloudProvider.AWS]

    await main_module.main()
    single = last_message(caplog_info).getMessage()
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    await main_module.main()

    assert single.startswith("The civo marketplace has been written (crawl 1: 1 software")
    assert last_message(caplog_info).getMessage() == f"2 marketplaces written to {database.url}."


@pytest.mark.db
@pytest.mark.parametrize(
    ("target", "crawler", "message"),
    [
        ("civo", FakeCrawler([]), "No software fetched from the marketplace of: civo (see the crawl errors above)."),
        (
            "civo",
            FakeCrawler([], CrawlerError("blocked")),
            "The marketplace of the following target is unavailable: civo",
        ),
        (
            "civo",
            FakeCrawler([], RuntimeError("boom")),
            "The marketplace crawl of the target civo failed unexpectedly.",
        ),
        ("all", FakeCrawler([]), "No marketplace written (see the crawl errors above)."),
    ],
)
async def test_marketplace_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    target: str,
    crawler: FakeCrawler,
    message: str,
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    monkeypatch.setenv("CRAWLER_TARGET", target)
    factory.get_marketplace.return_value = crawler
    factory.marketplace_providers.return_value = [CloudProvider.CIVO]

    await main_module.main()

    assert last_message(caplog_info).getMessage() == message


@pytest.mark.db
async def test_both_sources(monkeypatch: pytest.MonkeyPatch, factory: MagicMock, database: Storage) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "BOTH")
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    factory.get.return_value = FakeCrawler([product("Compute")])
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])

    await main_module.main()

    assert await database.catalogues.load(CloudProvider.CIVO) is not None
    assert await database.marketplaces.load(CloudProvider.CIVO) is not None


@pytest.mark.db
async def test_launch_dates_needs_no_target(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "launch-dates")
    factory.CRAWLER_MAP = {}

    await main_module.main()

    assert "0 catalogues dated, 0 products changed." in [record.getMessage() for record in caplog_info.records]


@pytest.mark.db
async def test_reclassify_needs_no_target(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "reclassify")

    await main_module.main()

    messages = [record.getMessage() for record in caplog_info.records]
    assert "0 marketplaces classified again, 0 software changed." in messages
    assert "0 catalogues classified again, 0 products changed." in messages
    assert last_message(caplog_info).getMessage().startswith("Run `VACUUM (ANALYZE) software, products`")
    factory.get_marketplace.assert_not_called()


@pytest.mark.db
@pytest.mark.parametrize(
    ("crawler", "message", "level"),
    [
        (FakeCrawler([report()]), "The market statistics have been written (crawl 1: 1 reports).", "INFO"),
        (FakeCrawler([]), "No market statistics fetched (see the crawl errors above).", "WARNING"),
        (FakeCrawler([], CrawlerError("blocked")), "The market statistics are unavailable.", "ERROR"),
        (FakeCrawler([], RuntimeError("boom")), "The market statistics crawl failed unexpectedly.", "ERROR"),
    ],
)
async def test_statistics_crawls_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    database: Storage,
    crawler: FakeCrawler,
    message: str,
    level: str,
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "statistics")
    factory.get_statistics.return_value = crawler

    await main_module.main()

    assert (last_message(caplog_info).levelname, last_message(caplog_info).getMessage()) == (level, message)


@pytest.mark.db
async def test_import_json_imports_the_output_folder(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    database: Storage,
    environment: Path,
    make_catalogue: Callable[[CloudProvider, List[str]], CloudCatalogue],
) -> None:
    (environment / "exported").mkdir()
    (environment / "exported" / "civo.json").write_text(
        make_catalogue(CloudProvider.CIVO, ["Compute"]).model_dump_json()
    )
    monkeypatch.setenv("CRAWLER_SOURCE", "import-json")
    monkeypatch.setenv("CRAWLER_IMPORT_DIR", "exported")
    monkeypatch.setenv("CRAWLER_IMPORT_REPLACE", "yes")

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "1 files imported (1 items) from exported."
    assert await database.catalogues.load(CloudProvider.CIVO) is not None


@pytest.mark.db
async def test_import_json_needs_a_folder(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, database: Storage
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "import-json")

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "The folder output to import does not exist."


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("", ["fred", "worldbank", "google-finance", "statcounter", "trendforce", "idc"]),
        ("all", ["fred", "worldbank", "google-finance", "statcounter", "trendforce", "idc"]),
        ("statcounter", ["worldbank", "statcounter"]),
        ("google-finance, FRED, nasdaq", ["fred", "google-finance"]),
    ],
)
def test_the_markets_sources_are_read_from_the_target(target: str, expected: List[str]) -> None:
    feeds = main_module.market_feeds(target, logging.getLogger("test"))

    assert [feed.value for feed in feeds] == expected


async def test_an_invalid_markets_scope_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MARKETS_SINCE", "2026")
    runner, storage = MagicMock(), MagicMock()

    with caplog.at_level(logging.ERROR):
        await main_module.collect_markets(runner, storage, "fred", logging.getLogger("test"))

    assert "The markets crawl scope is invalid" in caplog.text
    runner.stream_markets.assert_not_called()


class TestCompanyFeeds:
    def test_a_full_run_leaves_the_identity_resolvers_out(self) -> None:
        feeds = main_module.company_feeds("", logging.getLogger(__name__))

        assert CompanyFeed.EDGAR in feeds
        assert CompanyFeed.REPORTED in feeds
        assert not set(feeds) & {
            CompanyFeed.SEC_IDENTITY,
            CompanyFeed.OPENALEX_IDENTITY,
            CompanyFeed.ASSIGNEE_IDENTITY,
            CompanyFeed.FIGURE_CHECK,
        }

    def test_a_resolver_runs_when_named(self) -> None:
        feeds = main_module.company_feeds("sec-identity,assignee-identity", logging.getLogger(__name__))

        assert feeds == [CompanyFeed.SEC_IDENTITY, CompanyFeed.ASSIGNEE_IDENTITY]


async def test_the_price_coverage_lists_the_products_without_price(
    caplog_info: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = MagicMock()
    collector.return_value.curate = AsyncMock(return_value=(0, 0, 1))
    monkeypatch.setattr(main_module, "PriceCollector", collector)
    runner = MagicMock()
    runner.factory.CRAWLER_MAP = {CloudProvider.CIVO: MagicMock(), CloudProvider.AWS: MagicMock()}
    runner.storage.prices.coverage = AsyncMock(
        return_value=[("Kubernetes", True, False), ("Object Stores", False, False), ("Support", False, True)]
    )

    await main_module.report_price_coverage(runner, "civo", logging.getLogger("main"))

    messages = [record.getMessage() for record in caplog_info.records if record.name == "main"]
    assert "civo: 3 live products, 1 priced, 1 stated unpriced, 1 missing." in messages
    assert "civo products without price: Object Stores" in messages
    assert messages[-1] == "Price coverage: 3 live products, 1 priced, 1 stated unpriced, 1 missing."
    runner.storage.prices.coverage.assert_awaited_once_with("civo")
    collector.return_value.curate.assert_awaited_once()
