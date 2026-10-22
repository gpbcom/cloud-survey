from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Optional

import colorlog
import pytest
import yaml
from pydantic import ValidationError

from conf import LOGGER_CONFIG_PATH
from logger import load_logging_config, setup_logging
from logger.exception import LoggingConfigFileError
from models.configuration.logging.config.logging_config import LoggingConfig
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig

CONFIG_TEMPLATE = """
version: 1
formatters:
  plain:
    format: "%(levelname)s - %(name)s - %(message)s"
  coloured:
    "()": colorlog.ColoredFormatter
    format: "%(log_color)s%(levelname)s - %(message)s"
handlers:
  console:
    class: logging.StreamHandler
    formatter: coloured
    stream: ext://sys.stdout
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: plain
    filename: {filename}
    maxBytes: 200
    backupCount: 1
root:
  level: debug
  handlers: [console, file]
"""


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "dir" / "app.log"


@pytest.fixture
def config_path(tmp_path: Path, log_file: Path) -> Path:
    path = tmp_path / "logger.yaml"
    path.write_text(CONFIG_TEMPLATE.format(filename=log_file), encoding="utf-8")
    return path


def test_default_config_path_points_to_shipped_file() -> None:
    assert LOGGER_CONFIG_PATH.name == "logger.yaml"
    assert LOGGER_CONFIG_PATH.parent.name == "conf"
    assert LOGGER_CONFIG_PATH.is_file()


def test_load_default_configuration() -> None:
    config = load_logging_config()

    assert isinstance(config, LoggingConfig)
    assert set(config.handlers) == {"console", "file"}


def test_load_custom_configuration(config_path: Path, log_file: Path) -> None:
    config = load_logging_config(config_path)

    file = config.handlers["file"]
    assert isinstance(file, RotatingFileHandlerConfig)
    assert file.filename == log_file


def test_load_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(LoggingConfigFileError, match="the file cannot be read") as exc_info:
        load_logging_config(path)

    assert exc_info.value.path == path
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_load_directory(tmp_path: Path) -> None:
    with pytest.raises(LoggingConfigFileError, match="the file cannot be read") as exc_info:
        load_logging_config(tmp_path)

    assert isinstance(exc_info.value.__cause__, IsADirectoryError)


def test_load_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "logger.yaml"
    path.write_text("version: [1\n", encoding="utf-8")

    with pytest.raises(LoggingConfigFileError, match="the file is not valid YAML") as exc_info:
        load_logging_config(path)

    assert isinstance(exc_info.value.__cause__, yaml.YAMLError)


def test_load_invalid_configuration(tmp_path: Path) -> None:
    path = tmp_path / "logger.yaml"
    path.write_text("version: 1\nroot:\n  handlers: [ghost]\n", encoding="utf-8")

    with pytest.raises(LoggingConfigFileError, match=r"(?s)the configuration is invalid.*unknown handler") as exc_info:
        load_logging_config(path)

    assert exc_info.value.path == path
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_load_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "logger.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(LoggingConfigFileError, match="the configuration is invalid") as exc_info:
        load_logging_config(path)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_setup_logging_propagates_loading_errors(tmp_path: Path) -> None:
    with pytest.raises(LoggingConfigFileError):
        setup_logging(tmp_path / "missing.yaml")


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_configures_root_logger(config_path: Path, log_file: Path) -> None:
    config = setup_logging(config_path)

    root = logging.getLogger()
    assert isinstance(config, LoggingConfig)
    assert root.level == logging.DEBUG
    console, file = root.handlers
    assert isinstance(console, logging.StreamHandler)
    assert isinstance(console.formatter, colorlog.ColoredFormatter)
    assert isinstance(file, logging.handlers.RotatingFileHandler)
    assert Path(file.baseFilename) == log_file


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_creates_log_directory_and_writes(
    config_path: Path, log_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert not log_file.parent.exists()

    setup_logging(config_path)
    capsys.readouterr()  # Drop the setup log.
    logging.getLogger("crawler").warning("Rate limited")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.read_text(encoding="utf-8").splitlines()[-1] == "WARNING - crawler - Rate limited"
    assert capsys.readouterr().out == "\033[33mWARNING - Rate limited\033[0m\n"


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_rotates_file(config_path: Path, log_file: Path) -> None:
    setup_logging(config_path)
    logger = logging.getLogger("crawler")
    logger.setLevel(logging.INFO)
    logging.getLogger().handlers[0].setLevel(logging.CRITICAL)  # Keep the console quiet.

    for index in range(20):
        logger.info("message number %d", index)

    assert log_file.with_name("app.log.1").is_file()
    assert not log_file.with_name("app.log.2").exists()


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_does_not_disable_existing_loggers(config_path: Path) -> None:
    existing = logging.getLogger("already.created")

    setup_logging(config_path)

    assert existing.disabled is False


@pytest.mark.usefixtures("isolated_logging")
@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, "WARNING - Rate limited\n"),
        ({"FORCE_COLOR": "1"}, "\033[33mWARNING - Rate limited\033[0m\n"),
    ],
)
def test_setup_logging_disables_colours_when_stream_is_not_a_terminal(
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    env: Dict[str, str],
    expected: str,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            '"()": colorlog.ColoredFormatter', '"()": colorlog.ColoredFormatter\n    stream: ext://sys.stdout'
        ),
        encoding="utf-8",
    )

    setup_logging(config_path)
    capsys.readouterr()  # Drop the setup log.
    logging.getLogger("crawler").warning("Rate limited")

    assert capsys.readouterr().out == expected


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_honours_no_color(
    config_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")

    setup_logging(config_path)
    capsys.readouterr()  # Drop the setup log.
    logging.getLogger("crawler").error("Blocked")

    assert capsys.readouterr().out == "ERROR - Blocked\n"


@pytest.mark.usefixtures("isolated_logging")
def test_setup_logging_logs_the_applied_configuration(config_path: Path, log_file: Path) -> None:
    setup_logging(config_path)
    for handler in logging.getLogger().handlers:
        handler.flush()

    # The test configuration rotates the file every 200 bytes: read the rotated file too.
    files = [log_file.with_name("app.log.1"), log_file]
    lines = [line for path in files if path.exists() for line in path.read_text(encoding="utf-8").splitlines()]

    assert f"INFO - logger - Logging configured from {config_path} (handlers: console, file)." in lines
    assert f"DEBUG - logger - The file handler writes to {log_file}." in lines


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "cannot be read"), ("version: [1\n", "is not valid YAML"), ("version: 2\n", "is invalid (1 errors)")],
)
def test_loading_errors_are_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: Optional[str], message: str
) -> None:
    path = tmp_path / "logger.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.DEBUG, logger="logger"), pytest.raises(LoggingConfigFileError):
        load_logging_config(path)

    assert caplog.records[0].getMessage() == f"Loading the logging configuration {path}."
    assert caplog.records[-1].levelno == logging.ERROR
    assert message in caplog.records[-1].getMessage()
