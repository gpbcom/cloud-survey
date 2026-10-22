from __future__ import annotations

from typing import Dict

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.base_handler_config import BaseHandlerConfig
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.handlers.stream_handler_config import StreamHandlerConfig


def test_is_a_handler_config() -> None:
    assert issubclass(StreamHandlerConfig, BaseHandlerConfig)


def test_defaults() -> None:
    handler = StreamHandlerConfig.model_validate({"class": "logging.StreamHandler"})

    assert handler.class_ == "logging.StreamHandler"
    assert handler.stream == "ext://sys.stderr"
    assert handler.level is LogLevel.NOTSET


@pytest.mark.parametrize("stream", ["ext://sys.stdout", "ext://sys.stderr"])
def test_supported_streams(stream: str) -> None:
    assert StreamHandlerConfig.model_validate({"class": "logging.StreamHandler", "stream": stream}).stream == stream


@pytest.mark.parametrize("stream", ["ext://sys.stdin", "sys.stdout", ""])
def test_invalid_stream_is_rejected(stream: str) -> None:
    with pytest.raises(ValidationError):
        StreamHandlerConfig.model_validate({"class": "logging.StreamHandler", "stream": stream})


@pytest.mark.parametrize("payload", [{}, {"class": "logging.FileHandler"}])
def test_class_must_be_stream_handler(payload: Dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        StreamHandlerConfig.model_validate(payload)


def test_exports_dict_config_keys() -> None:
    handler = StreamHandlerConfig.model_validate(
        {"class": "logging.StreamHandler", "level": "info", "formatter": "plain", "stream": "ext://sys.stdout"}
    )

    assert handler.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "class": "logging.StreamHandler",
        "level": "INFO",
        "formatter": "plain",
        "filters": [],
        "stream": "ext://sys.stdout",
    }
