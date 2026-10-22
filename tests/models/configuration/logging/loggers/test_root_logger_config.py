from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.levelled_model import LevelledModel
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.loggers.root_logger_config import RootLoggerConfig


def test_is_a_levelled_model() -> None:
    assert issubclass(RootLoggerConfig, LevelledModel)


def test_defaults_match_standard_root_logger() -> None:
    root = RootLoggerConfig()

    assert root.level is LogLevel.WARNING
    assert root.handlers == []


def test_parses_values() -> None:
    root = RootLoggerConfig.model_validate({"level": "debug", "handlers": ["console", "file"]})

    assert (root.level, root.handlers) == (LogLevel.DEBUG, ["console", "file"])


def test_has_no_propagate_setting() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RootLoggerConfig.model_validate({"propagate": False})
