from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.base_handler_config import BaseHandlerConfig
from models.configuration.logging.base.levelled_model import LevelledModel
from models.configuration.logging.enums import LogLevel


def test_is_a_levelled_model() -> None:
    assert issubclass(BaseHandlerConfig, LevelledModel)


def test_defaults() -> None:
    handler = BaseHandlerConfig()

    assert handler.level is LogLevel.NOTSET
    assert handler.formatter is None
    assert handler.filters == []


def test_filters_are_not_shared_between_instances() -> None:
    assert BaseHandlerConfig().filters is not BaseHandlerConfig().filters


def test_parses_values() -> None:
    handler = BaseHandlerConfig.model_validate({"level": "error", "formatter": "plain", "filters": ["secrets"]})

    assert (handler.level, handler.formatter, handler.filters) == (LogLevel.ERROR, "plain", ["secrets"])


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BaseHandlerConfig.model_validate({"class": "logging.StreamHandler"})
