from __future__ import annotations

import json
import logging
import runpy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

import main as main_module
from crawler.exception import CrawlerError
from models.cloud.enums import CloudProvider

MAIN_PATH = Path(main_module.__file__)


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


@pytest.fixture(autouse=True)
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in a temporary directory: the catalogues are written to its `output/` folder."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CRAWLER_SOURCE", raising=False)
    return tmp_path


def software(name: str) -> Dict[str, JsonValue]:
    return {
        "name": name,
        "description": f"{name} description",
        "url": f"https://marketplace.example.com/{name}",
        "categories": ["developer-tool"],
        "types": ["monitoring"],
    }


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


@pytest.mark.parametrize("target", [None, ""])
async def test_no_target_defined(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, target: Optional[str]
) -> None:
    if target is None:
        monkeypatch.delenv("CRAWLER_TARGET", raising=False)
    else:
        monkeypatch.setenv("CRAWLER_TARGET", target)

    await main_module.main()

    assert "No target defined." in caplog_info.messages
    factory.get.assert_not_called()


async def test_writes_the_target_catalogue(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    caplog.set_level(logging.DEBUG, logger="main")
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    factory.get.return_value = FakeCrawler([product("Instances"), product("Object Storage")])

    await main_module.main()

    factory.get.assert_called_once_with("scaleway")
    data = json.loads((workdir / "output" / "scaleway.json").read_text(encoding="utf-8"))
    assert data["provider"] == "scaleway"
    assert [item["name"] for item in data["products"]] == ["Instances", "Object Storage"]
    assert [(record.levelname, record.getMessage()) for record in caplog.records if record.name == "main"] == [
        ("INFO", "Starting the crawler."),
        ("DEBUG", "Target read from CRAWLER_TARGET: scaleway (source catalogue)"),
        ("INFO", f"The scaleway catalogue has been written to {Path('output') / 'scaleway.json'}."),
    ]


async def test_writes_every_catalogue(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    factory.get.side_effect = lambda target: FakeCrawler([product(f"{CloudProvider(target).name} Compute")])

    await main_module.main()

    assert sorted(path.name for path in (workdir / "output").glob("*.json")) == sorted(
        f"{provider.value}.json" for provider in CloudProvider
    )
    assert last_message(caplog_info).getMessage() == "28 catalogues written to output."


async def test_no_catalogue_written_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    factory.get.side_effect = lambda target: FakeCrawler([])

    await main_module.main()

    record = last_message(caplog_info)
    assert (record.levelno, record.getMessage()) == (
        logging.WARNING,
        "No catalogue written (see the crawl errors above).",
    )
    assert not (workdir / "output").exists() or not list((workdir / "output").iterdir())


async def test_empty_crawl_is_a_warning_and_keeps_the_previous_file(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    previous = workdir / "output" / "scaleway.json"
    previous.parent.mkdir()
    previous.write_text("previous catalogue", encoding="utf-8")
    factory.get.return_value = FakeCrawler([])

    await main_module.main()

    record = last_message(caplog_info)
    assert (record.levelno, record.getMessage()) == (
        logging.WARNING,
        "No product fetched from target: scaleway (see the crawl errors above).",
    )
    assert previous.read_text(encoding="utf-8") == "previous catalogue"


async def test_unknown_target_is_logged(monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "unknown-cloud")

    await main_module.main()

    record = last_message(caplog_info)
    assert (record.levelno, record.getMessage()) == (
        logging.ERROR,
        "The following target is unavailable: unknown-cloud",
    )


async def test_crawler_error_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    factory.get.return_value = FakeCrawler([product("Instances")], error=CrawlerError("blocked"))

    await main_module.main()

    record = last_message(caplog_info)
    assert (record.levelno, record.getMessage()) == (logging.ERROR, "The following target is unavailable: scaleway")
    assert record.exc_info is None


async def test_write_error_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    (workdir / "output").write_text("a file, not a folder", encoding="utf-8")
    factory.get.return_value = FakeCrawler([product("Instances")])

    await main_module.main()

    record = last_message(caplog_info)
    assert (record.levelno, record.getMessage()) == (logging.ERROR, "The following target is unavailable: scaleway")


async def test_unexpected_error_is_logged_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    factory.get.return_value = FakeCrawler([product("Instances")], error=RuntimeError("browser crashed"))

    await main_module.main()

    record = last_message(caplog_info)
    assert record.levelno == logging.ERROR
    assert record.getMessage() == "The crawl of the target scaleway failed unexpectedly."
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], RuntimeError)


def test_script_entrypoint_sets_up_logging_and_runs_main(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("CRAWLER_TARGET", raising=False)
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


async def test_unknown_source_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_SOURCE", "Pricing")

    await main_module.main()

    assert last_message(caplog_info).getMessage() == (
        "Unknown crawl source 'pricing': "
        "CRAWLER_SOURCE must be one of catalogue, marketplace, both, reclassify, statistics."
    )
    assert last_message(caplog_info).levelno == logging.ERROR
    factory.get.assert_not_called()


async def test_blank_source_is_the_catalogue(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "scaleway")
    monkeypatch.setenv("CRAWLER_SOURCE", " ")
    factory.get.return_value = FakeCrawler([product("Instances")])

    await main_module.main()

    assert (workdir / "output" / "scaleway.json").is_file()
    factory.get_marketplace.assert_not_called()


async def test_writes_the_target_marketplace(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    factory.get_marketplace.return_value = FakeCrawler([software("grafana"), software("prometheus")])

    await main_module.main()

    path = workdir / "output" / "marketplaces" / "civo.json"
    assert [item["name"] for item in json.loads(path.read_text(encoding="utf-8"))["software"]] == [
        "grafana",
        "prometheus",
    ]
    assert (
        last_message(caplog_info).getMessage()
        == f"The civo marketplace has been written to {Path('output') / 'marketplaces' / 'civo.json'}."
    )
    factory.get.assert_not_called()


async def test_writes_every_marketplace(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    factory.marketplace_providers.return_value = [CloudProvider.CIVO, CloudProvider.STACKIT]
    factory.get_marketplace.side_effect = lambda provider, classifier: FakeCrawler([software("grafana")])

    await main_module.main()

    assert sorted(path.name for path in (workdir / "output" / "marketplaces").glob("*.json")) == [
        "civo.json",
        "stackit.json",
    ]
    assert last_message(caplog_info).getMessage() == f"2 marketplaces written to {Path('output') / 'marketplaces'}."


async def test_no_marketplace_written_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "all")
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    factory.marketplace_providers.return_value = [CloudProvider.CIVO]
    factory.get_marketplace.return_value = FakeCrawler([])

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "No marketplace written (see the crawl errors above)."
    assert last_message(caplog_info).levelno == logging.WARNING


@pytest.mark.parametrize(
    ("crawler", "message", "level"),
    [
        (FakeCrawler([]), "No software fetched from the marketplace of: civo (see the crawl errors above).", "WARNING"),
        (
            FakeCrawler([], CrawlerError("blocked")),
            "The marketplace of the following target is unavailable: civo",
            "ERROR",
        ),
        (
            FakeCrawler([], RuntimeError("boom")),
            "The marketplace crawl of the target civo failed unexpectedly.",
            "ERROR",
        ),
    ],
)
async def test_marketplace_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    crawler: FakeCrawler,
    message: str,
    level: str,
) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_SOURCE", "marketplace")
    factory.get_marketplace.return_value = crawler

    await main_module.main()

    assert (last_message(caplog_info).levelname, last_message(caplog_info).getMessage()) == (level, message)


async def test_both_sources(monkeypatch: pytest.MonkeyPatch, factory: MagicMock, workdir: Path) -> None:
    monkeypatch.setenv("CRAWLER_TARGET", "civo")
    monkeypatch.setenv("CRAWLER_SOURCE", "BOTH")
    factory.get.return_value = FakeCrawler([product("Kubernetes")])
    factory.get_marketplace.return_value = FakeCrawler([software("grafana")])

    await main_module.main()

    assert (workdir / "output" / "civo.json").is_file()
    assert (workdir / "output" / "marketplaces" / "civo.json").is_file()


async def test_reclassify_needs_no_target(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock
) -> None:
    monkeypatch.delenv("CRAWLER_TARGET", raising=False)
    monkeypatch.setenv("CRAWLER_SOURCE", "reclassify")

    await main_module.main()

    assert last_message(caplog_info).getMessage() == "0 marketplace files classified again."
    factory.get_marketplace.assert_not_called()


@pytest.mark.parametrize(
    ("crawler", "message", "level"),
    [
        (FakeCrawler([]), "No market statistics fetched (see the crawl errors above).", "WARNING"),
        (FakeCrawler([], CrawlerError("blocked")), "The market statistics are unavailable.", "ERROR"),
        (FakeCrawler([], RuntimeError("boom")), "The market statistics crawl failed unexpectedly.", "ERROR"),
    ],
)
async def test_statistics_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog_info: pytest.LogCaptureFixture,
    factory: MagicMock,
    crawler: FakeCrawler,
    message: str,
    level: str,
) -> None:
    monkeypatch.delenv("CRAWLER_TARGET", raising=False)
    monkeypatch.setenv("CRAWLER_SOURCE", "statistics")
    factory.get_statistics.return_value = crawler

    await main_module.main()

    assert (last_message(caplog_info).levelname, last_message(caplog_info).getMessage()) == (level, message)


async def test_writes_the_statistics(
    monkeypatch: pytest.MonkeyPatch, caplog_info: pytest.LogCaptureFixture, factory: MagicMock, workdir: Path
) -> None:
    monkeypatch.setenv("CRAWLER_SOURCE", "statistics")
    crawler = FakeCrawler(
        [
            {
                "period": "2026Q2",
                "region": "worldwide",
                "segment": "cloud-infrastructure-services",
                "source_url": "https://www.srgresearch.com/articles/q2",
                "title": "Q2",
                "published": "2026-07-30",
            }
        ]
    )
    crawler.source = "Synergy Research Group"  # type: ignore[attr-defined]
    factory.get_statistics.return_value = crawler

    await main_module.main()

    assert (workdir / "output" / "stats" / "synergy.json").is_file()
    assert last_message(caplog_info).getMessage() == (
        f"The market statistics have been written to {Path('output') / 'stats' / 'synergy.json'}."
    )
