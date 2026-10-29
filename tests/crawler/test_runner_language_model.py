from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from crawler.factory import CrawlerFactory
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider
from models.cloud.launch.launch_catalog import LaunchCatalog
from models.configuration.llm.llm_settings import LLMSettings
from storage.storage import Storage

pytestmark = pytest.mark.db

KEY_VARIABLE = "TEST_LLM_KEY"


class FakeCrawler:
    """Stand-in for a marketplace crawler, streaming one listing with a pending Russian label."""

    def use_launches(self, catalog: LaunchCatalog) -> None:
        self.launches = catalog

    async def stream(self) -> AsyncIterator[Dict[str, JsonValue]]:
        item: Dict[str, JsonValue] = {
            "name": "Qsim",
            "description": "Zz",
            "url": "https://marketplace.example.com/qsim",
            "marketplace_categories": ["Площадки для турниров"],
            "categories": ["developer-tool"],
        }
        yield item


def runner(storage: Storage, settings: LLMSettings) -> CatalogueRunner:
    factory = MagicMock(spec=CrawlerFactory)
    factory.get_marketplace.return_value = FakeCrawler()
    return CatalogueRunner(storage=storage, factory=factory, save_interval=0, llm_settings=settings)


async def test_no_model_is_called_without_a_key(storage: Storage) -> None:
    summary = await runner(storage, LLMSettings()).run_marketplace(CloudProvider.SELECTEL)

    assert summary.found == 1
    assert await storage.llm_usage.spent("USD") == Decimal(0)


async def test_a_spent_budget_never_fails_the_crawl(
    storage: Storage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(KEY_VARIABLE, "secret")
    raw: Dict[str, JsonValue] = {
        "llm": {"provider": "anthropic", "model_name": "claude-haiku-5-5", "api_key": KEY_VARIABLE},
        "llm_budget": {"ceiling": 0},
    }

    with caplog.at_level(logging.WARNING):
        summary = await runner(storage, LLMSettings.model_validate(raw)).run_marketplace(CloudProvider.SELECTEL)

    assert summary.found == 1
    assert "language model tasks after the selectel crawl stopped" in caplog.text


async def test_translate_without_a_model_does_nothing(
    storage: Storage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "llm.yaml"
    empty.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CRAWLER_LLM_CONFIG", str(empty))

    assert await runner(storage, LLMSettings()).translate() == (0, 0)
