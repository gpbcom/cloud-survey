from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.configuration.logging.base.base_handler_config import BaseHandlerConfig
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig

CLASS = "logging.handlers.RotatingFileHandler"


@pytest.fixture
def payload(tmp_path: Path) -> Dict[str, JsonValue]:
    return {"class": CLASS, "filename": str(tmp_path / "app.log"), "maxBytes": 1024, "backupCount": 2}


def test_is_a_handler_config() -> None:
    assert issubclass(RotatingFileHandlerConfig, BaseHandlerConfig)


def test_parses_dict_config_keys(payload: Dict[str, JsonValue], tmp_path: Path) -> None:
    handler = RotatingFileHandlerConfig.model_validate(payload)

    assert handler.class_ == CLASS
    assert handler.filename == tmp_path / "app.log"
    assert (handler.max_bytes, handler.backup_count) == (1024, 2)


def test_defaults(tmp_path: Path) -> None:
    handler = RotatingFileHandlerConfig.model_validate({"class": CLASS, "filename": "app.log"})

    assert handler.filename == Path("app.log")
    assert (handler.mode, handler.max_bytes, handler.backup_count) == ("a", 0, 0)
    assert (handler.encoding, handler.delay) == ("utf-8", False)


def test_can_be_built_with_field_names(tmp_path: Path) -> None:
    handler = RotatingFileHandlerConfig(class_=CLASS, filename=tmp_path / "app.log", max_bytes=10, backup_count=1)

    assert (handler.max_bytes, handler.backup_count) == (10, 1)


def test_filename_is_required() -> None:
    with pytest.raises(ValidationError, match="filename"):
        RotatingFileHandlerConfig.model_validate({"class": CLASS})


@pytest.mark.parametrize("field", ["maxBytes", "backupCount"])
def test_negative_rotation_settings_are_rejected(payload: Dict[str, JsonValue], field: str) -> None:
    payload[field] = -1

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        RotatingFileHandlerConfig.model_validate(payload)


@pytest.mark.parametrize("mode", ["a", "w"])
def test_supported_modes(payload: Dict[str, JsonValue], mode: str) -> None:
    payload["mode"] = mode

    assert RotatingFileHandlerConfig.model_validate(payload).mode == mode


def test_invalid_mode_is_rejected(payload: Dict[str, JsonValue]) -> None:
    payload["mode"] = "r"

    with pytest.raises(ValidationError):
        RotatingFileHandlerConfig.model_validate(payload)


def test_class_must_be_rotating_file_handler(payload: Dict[str, JsonValue]) -> None:
    payload["class"] = "logging.handlers.TimedRotatingFileHandler"

    with pytest.raises(ValidationError):
        RotatingFileHandlerConfig.model_validate(payload)


def test_snake_case_keys_are_not_exported(payload: Dict[str, JsonValue], tmp_path: Path) -> None:
    exported = RotatingFileHandlerConfig.model_validate(payload).model_dump(mode="json", by_alias=True)

    assert exported == {
        "class": CLASS,
        "level": "NOTSET",
        "formatter": None,
        "filters": [],
        "filename": str(tmp_path / "app.log"),
        "mode": "a",
        "maxBytes": 1024,
        "backupCount": 2,
        "encoding": "utf-8",
        "delay": False,
    }
