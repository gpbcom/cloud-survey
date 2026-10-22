from __future__ import annotations

from typing import Dict, Union

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from models.configuration.logging.handlers.handler_config import HandlerConfig
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig
from models.configuration.logging.handlers.stream_handler_config import StreamHandlerConfig

ADAPTER: TypeAdapter[Union[StreamHandlerConfig, RotatingFileHandlerConfig]] = TypeAdapter(HandlerConfig)


@pytest.mark.parametrize(
    ("payload", "expected_cls"),
    [
        ({"class": "logging.StreamHandler"}, StreamHandlerConfig),
        ({"class": "logging.handlers.RotatingFileHandler", "filename": "app.log"}, RotatingFileHandlerConfig),
    ],
)
def test_handler_is_selected_from_class_key(payload: Dict[str, JsonValue], expected_cls: type) -> None:
    assert type(ADAPTER.validate_python(payload)) is expected_cls


def test_unknown_class_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        ADAPTER.validate_python({"class": "logging.handlers.SysLogHandler"})


def test_missing_class_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Unable to extract tag"):
        ADAPTER.validate_python({"level": "INFO"})


def test_errors_are_reported_against_the_selected_handler() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ADAPTER.validate_python({"class": "logging.handlers.RotatingFileHandler"})

    (error,) = exc_info.value.errors()
    assert error["loc"] == ("logging.handlers.RotatingFileHandler", "filename")
