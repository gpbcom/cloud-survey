from __future__ import annotations

import logging
import logging.config
import logging.handlers
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

import colorlog
import pytest
import yaml
from pydantic import JsonValue, ValidationError

from conf import LOGGER_CONFIG_PATH
from models.configuration.logging.base.dict_config_model import DictConfigModel
from models.configuration.logging.config.logging_config import LoggingConfig
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig
from models.configuration.logging.formatters.standard_formatter_config import StandardFormatterConfig
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig
from models.configuration.logging.handlers.stream_handler_config import StreamHandlerConfig
from models.configuration.logging.loggers.root_logger_config import RootLoggerConfig


class TestShippedConfiguration:
    """The `src/conf/logger.yaml` file shipped with the application."""

    @pytest.fixture
    def config(self) -> LoggingConfig:
        return LoggingConfig.model_validate(yaml.safe_load(LOGGER_CONFIG_PATH.read_text(encoding="utf-8")))

    def test_root_logs_everything_to_console_and_file(self, config: LoggingConfig) -> None:
        assert config.root.level is LogLevel.DEBUG
        assert config.root.handlers == ["console", "file"]

    def test_console_handler_is_colourized(self, config: LoggingConfig) -> None:
        console = config.handlers["console"]

        assert isinstance(console, StreamHandlerConfig)
        assert console.stream == "ext://sys.stdout"
        assert console.formatter is not None
        formatter = config.formatters[console.formatter]
        assert isinstance(formatter, ColouredFormatterConfig)
        assert "%(log_color)s%(levelname)s%(reset)s" in formatter.fmt
        assert "%(message_log_color)s%(message)s" in formatter.fmt
        assert formatter.stream == console.stream
        assert set(formatter.log_colors) == set(LogLevel) - {LogLevel.NOTSET}
        assert set(formatter.secondary_log_colors) == {"message"}

    def test_file_handler_is_rotating_and_not_colourized(self, config: LoggingConfig) -> None:
        file = config.handlers["file"]

        assert isinstance(file, RotatingFileHandlerConfig)
        assert file.max_bytes > 0
        assert file.backup_count > 0
        assert file.formatter is not None
        formatter = config.formatters[file.formatter]
        assert isinstance(formatter, StandardFormatterConfig)
        assert formatter.class_ == "logging.Formatter"
        assert "log_color" not in formatter.fmt

    @pytest.mark.parametrize("formatter", ["detailed", "coloured"])
    def test_formats_use_dash_separator_and_maximum_information(self, config: LoggingConfig, formatter: str) -> None:
        colour_placeholders = r"%\((\w+_)?log_color\)s|%\(reset\)s|%\(cyan\)s"
        fields = re.sub(colour_placeholders, "", config.formatters[formatter].fmt).split(" - ")

        assert fields[-1] == "%(message)s"
        for attribute in ("asctime", "levelname", "name", "process", "thread", "taskName", "lineno", "funcName"):
            assert any(f"%({attribute})" in field for field in fields), attribute

    def test_third_party_loggers_are_quieted(self, config: LoggingConfig) -> None:
        assert all(logger.level is LogLevel.WARNING for logger in config.loggers.values())


def test_is_a_dict_config_model() -> None:
    assert issubclass(LoggingConfig, DictConfigModel)


def test_parses_dict_config_keys(logging_config_payload: Dict[str, JsonValue], tmp_path: Path) -> None:
    config = LoggingConfig.model_validate(logging_config_payload)

    file = config.handlers["file"]
    assert isinstance(file, RotatingFileHandlerConfig)
    assert file.filename == tmp_path / "app.log"
    assert isinstance(config.handlers["console"], StreamHandlerConfig)
    assert config.formatters["plain"].fmt == "%(levelname)s - %(message)s"
    assert config.loggers["app"].level is LogLevel.INFO
    assert config.root.level is LogLevel.DEBUG


def test_defaults() -> None:
    config = LoggingConfig()

    assert config.version == 1
    assert config.disable_existing_loggers is False
    assert (config.formatters, config.handlers, config.loggers) == ({}, {}, {})
    assert config.root == RootLoggerConfig(level=LogLevel.WARNING, handlers=[])


def test_can_be_built_with_field_names(tmp_path: Path) -> None:
    config = LoggingConfig(
        formatters={"plain": StandardFormatterConfig(fmt="%(message)s")},
        handlers={
            "file": RotatingFileHandlerConfig(
                class_="logging.handlers.RotatingFileHandler", filename=tmp_path / "app.log", formatter="plain"
            )
        },
        root=RootLoggerConfig(handlers=["file"]),
    )

    assert set(config.handlers) == {"file"}


def test_invalid_nested_handler_is_rejected(
    logging_config_payload: Dict[str, JsonValue], console_handler_payload: Dict[str, JsonValue]
) -> None:
    console_handler_payload["class"] = "logging.handlers.SysLogHandler"

    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        LoggingConfig.model_validate(logging_config_payload)


def test_unknown_keys_are_rejected(logging_config_payload: Dict[str, JsonValue]) -> None:
    logging_config_payload["incremental"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LoggingConfig.model_validate(logging_config_payload)


def test_unsupported_version_is_rejected(logging_config_payload: Dict[str, JsonValue]) -> None:
    logging_config_payload["version"] = 2

    with pytest.raises(ValidationError):
        LoggingConfig.model_validate(logging_config_payload)


class TestReferences:
    def test_unknown_formatter_reference_is_rejected(
        self, logging_config_payload: Dict[str, JsonValue], console_handler_payload: Dict[str, JsonValue]
    ) -> None:
        console_handler_payload["formatter"] = "missing"

        with pytest.raises(ValidationError, match="Handler 'console' references an unknown formatter: 'missing'"):
            LoggingConfig.model_validate(logging_config_payload)

    def test_handler_without_formatter_is_allowed(
        self, logging_config_payload: Dict[str, JsonValue], console_handler_payload: Dict[str, JsonValue]
    ) -> None:
        del console_handler_payload["formatter"]

        assert LoggingConfig.model_validate(logging_config_payload).handlers["console"].formatter is None

    @pytest.mark.parametrize("logger", ["app", "root"])
    def test_unknown_handler_reference_is_rejected(
        self,
        logging_config_payload: Dict[str, JsonValue],
        app_logger_payload: Dict[str, JsonValue],
        root_logger_payload: Dict[str, JsonValue],
        logger: str,
    ) -> None:
        section = root_logger_payload if logger == "root" else app_logger_payload
        section["handlers"] = ["console", "syslog", "mail"]

        with pytest.raises(ValidationError, match=f"Logger '{logger}' references unknown handler\\(s\\): syslog, mail"):
            LoggingConfig.model_validate(logging_config_payload)


class TestToDictConfig:
    def test_exports_dict_config_key_names(self, logging_config_payload: Dict[str, JsonValue], tmp_path: Path) -> None:
        exported = LoggingConfig.model_validate(logging_config_payload).to_dict_config()

        assert exported == {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {"class": "logging.Formatter", "format": "%(levelname)s - %(message)s", "style": "%"}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "NOTSET",
                    "formatter": "plain",
                    "filters": [],
                    "stream": "ext://sys.stdout",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "NOTSET",
                    "formatter": "plain",
                    "filters": [],
                    "filename": str(tmp_path / "app.log"),
                    "mode": "a",
                    "maxBytes": 1024,
                    "backupCount": 2,
                    "encoding": "utf-8",
                    "delay": False,
                },
            },
            "loggers": {"app": {"level": "INFO", "handlers": ["file"], "propagate": False}},
            "root": {"level": "DEBUG", "handlers": ["console"]},
        }

    def test_export_round_trips(self, logging_config_payload: Dict[str, JsonValue]) -> None:
        config = LoggingConfig.model_validate(logging_config_payload)

        assert LoggingConfig.model_validate(config.to_dict_config()) == config

    @pytest.mark.usefixtures("isolated_logging")
    def test_export_is_accepted_by_dict_config(
        self, logging_config_payload: Dict[str, JsonValue], tmp_path: Path
    ) -> None:
        logging.config.dictConfig(LoggingConfig.model_validate(logging_config_payload).to_dict_config())

        app_logger = logging.getLogger("app")
        (file_handler,) = app_logger.handlers
        assert isinstance(file_handler, logging.handlers.RotatingFileHandler)
        assert (file_handler.maxBytes, file_handler.backupCount) == (1024, 2)
        assert app_logger.level == logging.INFO
        assert app_logger.propagate is False

        app_logger.info("written")
        file_handler.flush()
        assert (tmp_path / "app.log").read_text(encoding="utf-8") == "INFO - written\n"

    @pytest.mark.usefixtures("isolated_logging")
    def test_shipped_export_is_accepted_by_dict_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "logs").mkdir()
        config = LoggingConfig.model_validate(yaml.safe_load(LOGGER_CONFIG_PATH.read_text(encoding="utf-8")))

        logging.config.dictConfig(config.to_dict_config())

        console, file = logging.getLogger().handlers
        assert isinstance(console.formatter, colorlog.ColoredFormatter)
        assert isinstance(file, logging.handlers.RotatingFileHandler)
        assert type(file.formatter) is logging.Formatter


class TestShippedConsoleRendering:
    """Render records through the shipped console formatter, built by `dictConfig` as at runtime."""

    TIMESTAMP = "2026-10-14T14:32:00.000"
    CONTEXT = "MainProcess:1234 - MainThread:5678 - Task-1"
    RESET = "\033[0m"
    CYAN = "\033[36m"

    @pytest.fixture
    def formatters(self, isolated_logging: None) -> Dict[str, logging.Formatter]:
        config = LoggingConfig.model_validate(yaml.safe_load(LOGGER_CONFIG_PATH.read_text(encoding="utf-8")))
        logging.config.dictConfig(
            {
                "version": 1,
                "formatters": {
                    name: config.formatters[name].model_dump(mode="json", by_alias=True)
                    for name in ("coloured", "detailed")
                },
                "handlers": {
                    name: {"class": "logging.StreamHandler", "formatter": name} for name in ("coloured", "detailed")
                },
                "loggers": {"rendering-test": {"handlers": ["coloured", "detailed"]}},
            }
        )
        built: Dict[str, logging.Formatter] = {}
        for handler in logging.getLogger("rendering-test").handlers:
            assert handler.formatter is not None
            built[handler.name or ""] = handler.formatter
        return built

    @staticmethod
    def make_record(level: int, message: str) -> logging.LogRecord:
        record = logging.LogRecord(
            "crawler.factory", level, "/app/src/crawler/factory.py", 56, message, None, None, "get"
        )
        record.created = time.mktime(datetime(2026, 10, 14, 14, 32).timetuple())
        record.msecs = 0
        record.processName, record.process = "MainProcess", 1234
        record.threadName, record.thread = "MainThread", 5678
        record.taskName = "Task-1"
        return record

    @pytest.mark.parametrize(
        ("level", "level_colour", "message_colour"),
        [
            (logging.DEBUG, "\033[37m", ""),
            (logging.INFO, "\033[32m", ""),
            (logging.WARNING, "\033[33m", "\033[33m"),
            (logging.ERROR, "\033[31m", "\033[31m"),
            (logging.CRITICAL, "\033[1;31m\033[47m", "\033[1;31m"),
        ],
    )
    def test_colourization(
        self,
        formatters: Dict[str, logging.Formatter],
        monkeypatch: pytest.MonkeyPatch,
        level: int,
        level_colour: str,
        message_colour: str,
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")

        line = formatters["coloured"].format(self.make_record(level, "Fetching page"))

        level_name = logging.getLevelName(level)
        assert line == (
            f"{self.TIMESTAMP} - {level_colour}{level_name}{self.RESET}"
            f" - {self.CYAN}crawler.factory{self.RESET} - {self.CONTEXT}"
            f" - {self.CYAN}factory.py:56{self.RESET} - get - {message_colour}Fetching page{self.RESET}"
        )

    @pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL])
    def test_colourization_does_not_change_the_format(
        self, formatters: Dict[str, logging.Formatter], monkeypatch: pytest.MonkeyPatch, level: int
    ) -> None:
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.setenv("NO_COLOR", "1")
        record = self.make_record(level, "Listed 3 open pull requests")

        line = formatters["coloured"].format(record)

        assert line == formatters["detailed"].format(record)
        assert line == (
            f"{self.TIMESTAMP} - {logging.getLevelName(level)} - crawler.factory - {self.CONTEXT}"
            " - factory.py:56 - get - Listed 3 open pull requests"
        )
