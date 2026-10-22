from __future__ import annotations

from typing import Dict, Type

import pytest
from pydantic import JsonValue, ValidationError

from models.configuration.logging.config.logging_config import LoggingConfig
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.exception import (
    InvalidSecondaryColoursNameError,
    LoggingConfigurationError,
    UnknownColourError,
    UnknownFormatterReferenceError,
    UnknownHandlerReferenceError,
)
from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig


class TestLoggingConfigurationError:
    def test_is_a_value_error(self) -> None:
        assert issubclass(LoggingConfigurationError, ValueError)

    def test_keeps_its_message(self) -> None:
        error = LoggingConfigurationError("Something went wrong.")

        assert error.message == "Something went wrong."
        assert str(error) == "Something went wrong."

    @pytest.mark.parametrize(
        "error_cls",
        [
            UnknownFormatterReferenceError,
            UnknownHandlerReferenceError,
            InvalidSecondaryColoursNameError,
            UnknownColourError,
        ],
    )
    def test_every_error_inherits_from_it(self, error_cls: Type[LoggingConfigurationError]) -> None:
        assert issubclass(error_cls, LoggingConfigurationError)


def test_unknown_formatter_reference_error() -> None:
    error = UnknownFormatterReferenceError("console", "missing")

    assert (error.handler, error.formatter) == ("console", "missing")
    assert str(error) == "Handler 'console' references an unknown formatter: 'missing'."


def test_unknown_handler_reference_error() -> None:
    error = UnknownHandlerReferenceError("root", ["syslog", "mail"])

    assert (error.logger, error.handlers) == ("root", ["syslog", "mail"])
    assert str(error) == "Logger 'root' references unknown handler(s): syslog, mail."


def test_invalid_secondary_colours_name_error() -> None:
    error = InvalidSecondaryColoursNameError("message-colour")

    assert error.name == "message-colour"
    assert str(error) == "Secondary log colours name 'message-colour' must be a valid identifier."


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ("", "Unknown colour(s) for level ERROR: mauve, sparkly."),
        ("`message` ", "Unknown `message` colour(s) for level ERROR: mauve, sparkly."),
    ],
)
def test_unknown_colour_error(scope: str, message: str) -> None:
    error = UnknownColourError(scope, LogLevel.ERROR, ["mauve", "sparkly"])

    assert (error.scope, error.level, error.colours) == (scope, LogLevel.ERROR, ["mauve", "sparkly"])
    assert str(error) == message


class TestRaisedByTheModels:
    def test_unknown_formatter_reference(
        self, logging_config_payload: Dict[str, JsonValue], console_handler_payload: Dict[str, JsonValue]
    ) -> None:
        console_handler_payload["formatter"] = "missing"

        with pytest.raises(ValidationError) as exc_info:
            LoggingConfig.model_validate(logging_config_payload)

        error = exc_info.value.errors()[0]["ctx"]["error"]
        assert isinstance(error, UnknownFormatterReferenceError)
        assert (error.handler, error.formatter) == ("console", "missing")

    def test_unknown_handler_reference(
        self, logging_config_payload: Dict[str, JsonValue], root_logger_payload: Dict[str, JsonValue]
    ) -> None:
        root_logger_payload["handlers"] = ["console", "ghost"]

        with pytest.raises(ValidationError) as exc_info:
            LoggingConfig.model_validate(logging_config_payload)

        error = exc_info.value.errors()[0]["ctx"]["error"]
        assert isinstance(error, UnknownHandlerReferenceError)
        assert (error.logger, error.handlers) == ("root", ["ghost"])

    @pytest.mark.parametrize(
        ("override", "error_cls"),
        [
            ({"log_colors": {"ERROR": "mauve"}}, UnknownColourError),
            ({"secondary_log_colors": {"message": {"ERROR": "mauve"}}}, UnknownColourError),
            ({"secondary_log_colors": {"message-colour": {"ERROR": "red"}}}, InvalidSecondaryColoursNameError),
        ],
    )
    def test_coloured_formatter_errors(
        self, override: Dict[str, JsonValue], error_cls: Type[LoggingConfigurationError]
    ) -> None:
        payload: Dict[str, JsonValue] = {"()": "colorlog.ColoredFormatter", "format": "%(message)s", **override}

        with pytest.raises(ValidationError) as exc_info:
            ColouredFormatterConfig.model_validate(payload)

        assert isinstance(exc_info.value.errors()[0]["ctx"]["error"], error_cls)
