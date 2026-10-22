from __future__ import annotations

import logging

import pytest

from models.configuration.storage.storage_settings import StorageSettings
from storage.engine.settings_reader import StorageSettingsReader


def test_the_defaults_are_used_without_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("CRAWLER_DATABASE_URL", "CRAWLER_DATABASE_POOL_SIZE", "CRAWLER_DATABASE_ECHO"):
        monkeypatch.delenv(variable, raising=False)

    assert StorageSettingsReader().read() == StorageSettings()


def test_the_environment_overrides_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAWLER_DATABASE_URL", "postgresql+asyncpg://u:p@db:6543/crawls")
    monkeypatch.setenv("CRAWLER_DATABASE_POOL_SIZE", "12")
    monkeypatch.setenv("CRAWLER_DATABASE_MAX_OVERFLOW", "3")
    monkeypatch.setenv("CRAWLER_DATABASE_BATCH_SIZE", "500")
    monkeypatch.setenv("CRAWLER_DATABASE_ECHO", "yes")

    settings = StorageSettingsReader().read()

    assert (settings.url, settings.pool_size, settings.max_overflow, settings.batch_size, settings.echo) == (
        "postgresql+asyncpg://u:p@db:6543/crawls",
        12,
        3,
        500,
        True,
    )


def test_invalid_values_fall_back_to_their_defaults(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("CRAWLER_DATABASE_URL", "mysql://u:p@db/crawls")
    monkeypatch.setenv("CRAWLER_DATABASE_POOL_SIZE", "many")
    monkeypatch.setenv("CRAWLER_DATABASE_BATCH_SIZE", "0")

    with caplog.at_level(logging.WARNING):
        settings = StorageSettingsReader().read()

    assert (settings.url, settings.pool_size, settings.batch_size) == (
        StorageSettings().url,
        StorageSettings().pool_size,
        StorageSettings().batch_size,
    )
    assert "CRAWLER_DATABASE_POOL_SIZE='many' is not a number" in caplog.text
    assert "Invalid storage settings (batch_size, url)" in caplog.text


def test_a_logged_url_hides_its_password() -> None:
    reader = StorageSettingsReader()

    assert reader.safe_url("postgresql+asyncpg://u:secret@db/x") == "postgresql+asyncpg://u:***@db/x"
    assert reader.safe_url("not a url") == "not a url"
