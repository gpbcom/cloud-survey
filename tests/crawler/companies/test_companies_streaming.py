from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Dict, List, Optional, Set, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import JsonValue

from analytics.companies.companies_run import CompaniesRun
from crawler.runner import CatalogueRunner
from curated.bundle.bundle_catalogs import BundleCatalogs
from models.companies.enums import CompanyFeed
from models.markets.crawl_scope import CrawlScope


class FakeCompaniesCrawler:
    """A crawler streaming planted facts, which can be paused."""

    def __init__(self, items: List[Dict[str, JsonValue]], stop: threading.Event, stop_after: int) -> None:
        self.items = items
        self.stop = stop
        self.stop_after = stop_after
        self.paused = False
        self.refusal: Optional[str] = None
        self.rejected: Dict[str, Set[str]] = {}

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        for index, item in enumerate(self.items):
            if self.paused:
                return
            if index == self.stop_after:
                self.stop.set()
            yield item

    def pause(self) -> None:
        self.paused = True


def runner_with(crawler: FakeCompaniesCrawler) -> CatalogueRunner:
    factory = MagicMock()
    factory.get_companies.return_value = crawler
    return CatalogueRunner(storage=MagicMock(), factory=factory)


def facts(count: int) -> List[Dict[str, JsonValue]]:
    return [{"kind": "paper", "index": index} for index in range(count)]


def bundled(runner: MagicMock) -> None:
    """Give a mocked runner the catalogues of the curated bundle."""
    catalogs = BundleCatalogs()
    runner.storage.catalogs.companies = AsyncMock(return_value=catalogs.companies())
    runner.storage.catalogs.markets = AsyncMock(return_value=catalogs.markets())
    runner.storage.catalogs.figures = AsyncMock(return_value=catalogs.figures())
    runner.storage.catalogs.chronology = AsyncMock(return_value=catalogs.chronology())


def test_the_facts_are_written_then_observed_by_small_batches() -> None:
    stop = threading.Event()
    runner = runner_with(FakeCompaniesCrawler(facts(7), stop, stop_after=99))
    sink = AsyncMock(side_effect=lambda feed, batch: len(batch))
    seen: List[Tuple[CompanyFeed, int, int]] = []

    written = asyncio.run(
        runner.stream_companies(
            CompanyFeed.OPENALEX,
            sink,
            batch_size=3,
            observer=lambda feed, batch, rows: seen.append((feed, len(batch), rows)),
        )
    )

    assert written == 7
    assert seen == [(CompanyFeed.OPENALEX, 3, 3), (CompanyFeed.OPENALEX, 3, 3), (CompanyFeed.OPENALEX, 1, 1)]


def test_a_stop_pauses_the_crawler_and_keeps_what_was_read() -> None:
    stop = threading.Event()
    crawler = FakeCompaniesCrawler(facts(10), stop, stop_after=2)
    runner = runner_with(crawler)
    sink = AsyncMock(side_effect=lambda feed, batch: len(batch))

    written = asyncio.run(runner.stream_companies(CompanyFeed.OPENALEX, sink, batch_size=2, stop=stop))

    assert crawler.paused
    assert written == 3


def test_the_default_batch_is_the_markets_batch() -> None:
    stop = threading.Event()
    runner = runner_with(FakeCompaniesCrawler(facts(5), stop, stop_after=99))
    sink = AsyncMock(side_effect=lambda feed, batch: len(batch))

    asyncio.run(runner.stream_companies(CompanyFeed.OPENALEX, sink))

    assert sink.await_count == 1


def test_a_stopped_run_skips_the_next_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MagicMock()
    bundled(runner)
    runner.stream_companies = AsyncMock(return_value=4)
    runner.storage.patents.read_windows = AsyncMock(return_value=[])
    collector = MagicMock()
    collector.finish = AsyncMock(return_value=1)
    monkeypatch.setattr("analytics.companies.companies_run.CompaniesCollector", MagicMock(return_value=collector))
    stop = threading.Event()
    observer = MagicMock()
    stop.set()

    written = asyncio.run(
        CompaniesRun(runner).run(
            [CompanyFeed.GOOGLE_PATENTS, CompanyFeed.OPENALEX], CrawlScope(companies=["ibm"]), observer, 25, stop
        )
    )

    assert written == 1
    runner.stream_companies.assert_not_awaited()


def test_a_run_hands_the_observer_and_the_batch_to_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MagicMock()
    bundled(runner)
    runner.stream_companies = AsyncMock(return_value=4)
    runner.storage.papers.unlink = AsyncMock(return_value=0)
    runner.storage.papers.confirm_researchers = AsyncMock(return_value=3)
    runner.storage.papers.sweep = AsyncMock(return_value=(0, 0))
    collector = MagicMock()
    collector.finish = AsyncMock(return_value=1)
    monkeypatch.setattr("analytics.companies.companies_run.CompaniesCollector", MagicMock(return_value=collector))
    observer = MagicMock()

    written = asyncio.run(
        CompaniesRun(runner).run([CompanyFeed.OPENALEX], CrawlScope(companies=["opera"]), observer, 25)
    )

    assert written == 5
    assert runner.storage.papers.confirm_researchers.await_args.args == (["opera"], 2, 2)
    assert runner.storage.papers.sweep.await_args.args[0] == ["opera"]
    kwargs = runner.stream_companies.await_args.kwargs
    assert kwargs["observer"] is observer
    assert kwargs["batch_size"] == 25


def test_a_stopped_papers_search_confirms_but_removes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MagicMock()
    bundled(runner)
    stop = threading.Event()

    def stopping(*args: JsonValue, **kwargs: JsonValue) -> int:
        stop.set()
        return 2

    runner.stream_companies = AsyncMock(side_effect=stopping)
    runner.storage.papers.unlink = AsyncMock(return_value=0)
    runner.storage.papers.confirm_researchers = AsyncMock(return_value=1)
    runner.storage.papers.sweep = AsyncMock(return_value=(0, 0))
    collector = MagicMock()
    collector.finish = AsyncMock(return_value=0)
    monkeypatch.setattr("analytics.companies.companies_run.CompaniesCollector", MagicMock(return_value=collector))

    asyncio.run(CompaniesRun(runner).run([CompanyFeed.OPENALEX], CrawlScope(companies=["amazon"]), stop=stop))

    runner.storage.papers.confirm_researchers.assert_awaited_once()
    runner.storage.papers.sweep.assert_not_awaited()


def test_a_refused_papers_search_unlinks_what_it_rejected_but_sweeps_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MagicMock()
    bundled(runner)

    def refuse(
        *args: JsonValue, refusals: Dict[CompanyFeed, str], rejected: Dict[str, Set[str]], **kwargs: JsonValue
    ) -> int:
        refusals[CompanyFeed.OPENALEX] = "OpenAlex refused the search"
        rejected["opera"] = {"W2000000001"}
        return 2

    runner.stream_companies = AsyncMock(side_effect=refuse)
    runner.storage.papers.unlink = AsyncMock(return_value=1)
    runner.storage.papers.confirm_researchers = AsyncMock(return_value=1)
    runner.storage.papers.sweep = AsyncMock(return_value=(0, 0))
    collector = MagicMock()
    collector.finish = AsyncMock(return_value=0)
    monkeypatch.setattr("analytics.companies.companies_run.CompaniesCollector", MagicMock(return_value=collector))
    run = CompaniesRun(runner)

    asyncio.run(run.run([CompanyFeed.OPENALEX], CrawlScope(companies=["opera"])))

    runner.storage.papers.unlink.assert_awaited_once_with({"opera": {"W2000000001"}})
    runner.storage.papers.sweep.assert_not_awaited()
    assert run.refusals == {CompanyFeed.OPENALEX: "OpenAlex refused the search"}
