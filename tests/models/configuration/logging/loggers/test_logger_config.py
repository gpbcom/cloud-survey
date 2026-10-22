from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.levelled_model import LevelledModel
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.loggers.logger_config import LoggerConfig


def test_is_a_levelled_model() -> None:
    assert issubclass(LoggerConfig, LevelledModel)


def test_defaults() -> None:
    assert LoggerConfig() == LoggerConfig(level=LogLevel.NOTSET, handlers=[], propagate=True)


def test_parses_values() -> None:
    logger = LoggerConfig.model_validate({"level": "warning", "handlers": ["file"], "propagate": False})

    assert (logger.level, logger.handlers, logger.propagate) == (LogLevel.WARNING, ["file"], False)


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LoggerConfig.model_validate({"qualname": "app"})


def test_exports_dict_config_keys() -> None:
    assert LoggerConfig(handlers=["file"]).model_dump(mode="json", by_alias=True) == {
        "level": "NOTSET",
        "handlers": ["file"],
        "propagate": True,
    }
