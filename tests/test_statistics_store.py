from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from catalogue.exception import CatalogueFileError, CatalogueWriteError
from catalogue.statistics_store import DEFAULT_STATISTICS_DIR, StatisticsStore
from models.cloud.enums import MarketPlayer
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics


@pytest.fixture
def statistics(make_report: Callable[..., MarketReport]) -> MarketStatistics:
    return MarketStatistics(
        source="Synergy Research Group",
        crawled_at=datetime(2026, 10, 16, tzinfo=UTC),
        reports=[make_report("2026Q2", [(MarketPlayer.AMAZON, 28)])],
    )


def test_defaults() -> None:
    store = StatisticsStore()

    assert (store.output_dir, store.logger.name) == (DEFAULT_STATISTICS_DIR, "catalogue.statistics_store")
    assert store.path_for("synergy") == Path("output") / "stats" / "synergy.json"


def test_round_trip(tmp_path: Path, statistics: MarketStatistics, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="catalogue.statistics_store")
    store = StatisticsStore(tmp_path / "stats")

    path = store.save("synergy", statistics)

    assert store.load("synergy") == statistics
    assert store.load("canalys") is None
    assert f"1 Synergy Research Group market reports written to {path}." in caplog.messages


@pytest.mark.parametrize(
    ("content", "reason"), [("{", "the file is not valid JSON"), ('{"source": ""}', "invalid statistics (2 errors)")]
)
def test_unusable_files(tmp_path: Path, content: str, reason: str) -> None:
    store = StatisticsStore(tmp_path)
    store.path_for("synergy").write_text(content, encoding="utf-8")

    with pytest.raises(CatalogueFileError) as exc_info:
        store.load("synergy")

    assert exc_info.value.reason == reason


def test_unreadable_file(tmp_path: Path) -> None:
    store = StatisticsStore(tmp_path)
    store.path_for("synergy").mkdir()

    with pytest.raises(CatalogueFileError, match="cannot be read"):
        store.load("synergy")


def test_failed_save_keeps_the_previous_file(
    tmp_path: Path, statistics: MarketStatistics, caplog: pytest.LogCaptureFixture
) -> None:
    store = StatisticsStore(tmp_path)
    store.save("synergy", statistics)

    with (
        patch("catalogue.atomic_json_file.os.replace", side_effect=PermissionError(13, "Permission denied")),
        pytest.raises(CatalogueWriteError),
    ):
        store.save("synergy", statistics)

    assert store.load("synergy") == statistics
    assert not list(tmp_path.glob(".*.tmp"))
    assert any(record.levelno == logging.ERROR for record in caplog.records)
