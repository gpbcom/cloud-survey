from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from models.configuration.logging.base.dict_config_model import DictConfigModel
from models.configuration.logging.base.levelled_model import LevelledModel
from models.configuration.logging.enums import LogLevel


def test_is_a_dict_config_model() -> None:
    assert issubclass(LevelledModel, DictConfigModel)


def test_default_level() -> None:
    assert LevelledModel().level is LogLevel.NOTSET


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("debug", LogLevel.DEBUG),
        ("Info", LogLevel.INFO),
        ("WARNING", LogLevel.WARNING),
        (LogLevel.ERROR, LogLevel.ERROR),
    ],
)
def test_level_is_case_insensitive(raw: JsonValue, expected: LogLevel) -> None:
    assert LevelledModel(level=raw).level is expected


@pytest.mark.parametrize("raw", ["TRACE", "", 10, None])
def test_invalid_level_is_rejected(raw: JsonValue) -> None:
    with pytest.raises(ValidationError):
        LevelledModel(level=raw)


@pytest.mark.parametrize(("raw", "expected"), [("info", "INFO"), (10, 10), (None, None)])
def test_normalize_level_directly(raw: JsonValue, expected: JsonValue) -> None:
    assert LevelledModel.normalize_level(raw) == expected
