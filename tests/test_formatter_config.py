from __future__ import annotations

from typing import Dict, Union

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig
from models.configuration.logging.formatters.formatter_config import FormatterConfig
from models.configuration.logging.formatters.standard_formatter_config import StandardFormatterConfig

ADAPTER: TypeAdapter[Union[StandardFormatterConfig, ColouredFormatterConfig]] = TypeAdapter(FormatterConfig)


@pytest.mark.parametrize(
    ("payload", "expected_cls"),
    [
        ({"format": "%(message)s"}, StandardFormatterConfig),
        ({"class": "logging.Formatter", "format": "%(message)s"}, StandardFormatterConfig),
        ({"()": "colorlog.ColoredFormatter", "format": "%(message)s"}, ColouredFormatterConfig),
        ({"factory": "colorlog.ColoredFormatter", "fmt": "%(message)s"}, ColouredFormatterConfig),
    ],
)
def test_formatter_is_selected_from_keys(payload: Dict[str, JsonValue], expected_cls: type) -> None:
    assert type(ADAPTER.validate_python(payload)) is expected_cls


@pytest.mark.parametrize(
    "formatter",
    [StandardFormatterConfig(fmt="%(message)s"), ColouredFormatterConfig(factory="colorlog.ColoredFormatter", fmt="x")],
)
def test_built_formatters_are_accepted(formatter: Union[StandardFormatterConfig, ColouredFormatterConfig]) -> None:
    assert ADAPTER.validate_python(formatter) is formatter


def test_errors_are_reported_against_the_selected_formatter() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ADAPTER.validate_python({"()": "logging.Formatter", "format": "x"})

    (error,) = exc_info.value.errors()
    assert error["loc"] == ("coloured", "()")


def test_factory_keys_are_not_mixed_with_class_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ADAPTER.validate_python({"()": "colorlog.ColoredFormatter", "class": "logging.Formatter", "format": "x"})
