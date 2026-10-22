from __future__ import annotations

import logging
import logging.config
import re
import sys
from typing import Dict, Optional

import colorlog
import pytest
from pydantic import JsonValue, ValidationError

from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.enums import LogLevel
from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig

FACTORY = "colorlog.ColoredFormatter"


@pytest.fixture
def payload() -> Dict[str, JsonValue]:
    return {"()": FACTORY, "format": "%(log_color)s%(levelname)s - %(message)s"}


def test_is_a_base_formatter_config() -> None:
    assert issubclass(ColouredFormatterConfig, BaseFormatterConfig)


def test_defaults(payload: Dict[str, JsonValue]) -> None:
    formatter = ColouredFormatterConfig.model_validate(payload)

    assert formatter.factory == FACTORY
    assert formatter.fmt == "%(log_color)s%(levelname)s - %(message)s"
    assert formatter.log_colors == {
        LogLevel.DEBUG: "white",
        LogLevel.INFO: "green",
        LogLevel.WARNING: "yellow",
        LogLevel.ERROR: "red",
        LogLevel.CRITICAL: "bold_red,bg_white",
    }
    assert formatter.secondary_log_colors == {}
    assert formatter.reset is True
    assert formatter.stream is None


def test_default_log_colors_are_not_shared(payload: Dict[str, JsonValue]) -> None:
    first = ColouredFormatterConfig.model_validate(payload)
    second = ColouredFormatterConfig.model_validate(payload)

    assert first.log_colors is not second.log_colors
    assert first.secondary_log_colors is not second.secondary_log_colors


def test_can_be_built_with_field_names() -> None:
    formatter = ColouredFormatterConfig(factory=FACTORY, fmt="%(message)s", reset=False)

    assert (formatter.fmt, formatter.reset) == ("%(message)s", False)


@pytest.mark.parametrize("payload_override", [{"()": "logging.Formatter"}, {"()": None}])
def test_factory_must_be_colorlog(payload: Dict[str, JsonValue], payload_override: Dict[str, JsonValue]) -> None:
    payload.update(payload_override)

    with pytest.raises(ValidationError):
        ColouredFormatterConfig.model_validate(payload)


def test_factory_is_required(payload: Dict[str, JsonValue]) -> None:
    del payload["()"]

    with pytest.raises(ValidationError, match="\\(\\)"):
        ColouredFormatterConfig.model_validate(payload)


@pytest.mark.parametrize("fmt", [None, ""])
def test_format_is_required(payload: Dict[str, JsonValue], fmt: Optional[str]) -> None:
    payload["format"] = fmt

    with pytest.raises(ValidationError):
        ColouredFormatterConfig.model_validate(payload)


@pytest.mark.parametrize("stream", ["ext://sys.stdout", "ext://sys.stderr"])
def test_supported_streams(payload: Dict[str, JsonValue], stream: str) -> None:
    payload["stream"] = stream

    assert ColouredFormatterConfig.model_validate(payload).stream == stream


def test_invalid_stream_is_rejected(payload: Dict[str, JsonValue]) -> None:
    payload["stream"] = "ext://sys.stdin"

    with pytest.raises(ValidationError):
        ColouredFormatterConfig.model_validate(payload)


class TestLogColors:
    def test_custom_colours(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = {"INFO": "bold_blue", "ERROR": "red,bg_white"}

        formatter = ColouredFormatterConfig.model_validate(payload)

        assert formatter.log_colors == {LogLevel.INFO: "bold_blue", LogLevel.ERROR: "red,bg_white"}

    def test_levels_are_case_insensitive(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = {"warning": "yellow", LogLevel.DEBUG: "white"}

        formatter = ColouredFormatterConfig.model_validate(payload)

        assert formatter.log_colors == {LogLevel.WARNING: "yellow", LogLevel.DEBUG: "white"}

    def test_empty_colour_means_no_colour(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = {"INFO": ""}

        assert ColouredFormatterConfig.model_validate(payload).log_colors == {LogLevel.INFO: ""}

    def test_unknown_level_is_rejected(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = {"TRACE": "white"}

        with pytest.raises(ValidationError):
            ColouredFormatterConfig.model_validate(payload)

    def test_unknown_colour_is_rejected(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = {"ERROR": "bold_red,bg_rainbow,sparkly"}

        with pytest.raises(ValidationError, match="Unknown colour\\(s\\) for level ERROR: bg_rainbow, sparkly"):
            ColouredFormatterConfig.model_validate(payload)

    def test_not_a_mapping_is_rejected(self, payload: Dict[str, JsonValue]) -> None:
        payload["log_colors"] = ["red"]

        with pytest.raises(ValidationError):
            ColouredFormatterConfig.model_validate(payload)

    @pytest.mark.parametrize(("raw", "expected"), [({"info": "red"}, {"INFO": "red"}), ("red", "red"), (None, None)])
    def test_normalize_levels_directly(self, raw: JsonValue, expected: JsonValue) -> None:
        assert ColouredFormatterConfig.normalize_levels(raw) == expected


class TestSecondaryLogColors:
    def test_custom_colours(self, payload: Dict[str, JsonValue]) -> None:
        payload["secondary_log_colors"] = {"message": {"WARNING": "yellow", "CRITICAL": "bold_red"}, "name": {}}

        formatter = ColouredFormatterConfig.model_validate(payload)

        assert formatter.secondary_log_colors == {
            "message": {LogLevel.WARNING: "yellow", LogLevel.CRITICAL: "bold_red"},
            "name": {},
        }

    def test_levels_are_case_insensitive(self, payload: Dict[str, JsonValue]) -> None:
        payload["secondary_log_colors"] = {"message": {"error": "red", LogLevel.DEBUG: "white"}}

        formatter = ColouredFormatterConfig.model_validate(payload)

        assert formatter.secondary_log_colors == {"message": {LogLevel.ERROR: "red", LogLevel.DEBUG: "white"}}

    def test_unknown_colour_is_rejected(self, payload: Dict[str, JsonValue]) -> None:
        payload["secondary_log_colors"] = {"message": {"ERROR": "red,sparkly"}}

        with pytest.raises(ValidationError, match="Unknown `message` colour\\(s\\) for level ERROR: sparkly"):
            ColouredFormatterConfig.model_validate(payload)

    def test_unknown_level_is_rejected(self, payload: Dict[str, JsonValue]) -> None:
        payload["secondary_log_colors"] = {"message": {"TRACE": "white"}}

        with pytest.raises(ValidationError):
            ColouredFormatterConfig.model_validate(payload)

    @pytest.mark.parametrize("name", ["", "message-colour", "1st", "message colour"])
    def test_name_must_be_a_placeholder_identifier(self, payload: Dict[str, JsonValue], name: str) -> None:
        payload["secondary_log_colors"] = {name: {"ERROR": "red"}}

        with pytest.raises(ValidationError, match="must be a valid identifier"):
            ColouredFormatterConfig.model_validate(payload)

    @pytest.mark.parametrize("value", [["red"], {"message": "red"}, {"message": ["red"]}])
    def test_not_a_mapping_of_mappings_is_rejected(self, payload: Dict[str, JsonValue], value: JsonValue) -> None:
        payload["secondary_log_colors"] = value

        with pytest.raises(ValidationError):
            ColouredFormatterConfig.model_validate(payload)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ({"message": {"info": "red"}}, {"message": {"INFO": "red"}}),
            ({"message": "red"}, {"message": "red"}),
            ("red", "red"),
            (None, None),
        ],
    )
    def test_validate_secondary_log_colors_directly(self, raw: JsonValue, expected: JsonValue) -> None:
        assert ColouredFormatterConfig.validate_secondary_log_colors(raw) == expected


class TestCheckColours:
    def test_returns_the_checked_mapping(self) -> None:
        colours: Dict[str, JsonValue] = {"INFO": "green", "ERROR": "bold_red,bg_white", "DEBUG": ""}

        assert ColouredFormatterConfig.check_colours(colours, scope="") is colours

    def test_error_names_the_scope(self) -> None:
        with pytest.raises(ValueError, match=f"^{re.escape('Unknown `name` colour(s) for level INFO: mauve.')}$"):
            ColouredFormatterConfig.check_colours({"INFO": "mauve"}, scope="`name` ")

    def test_leaves_non_string_colours_to_pydantic(self) -> None:
        colours: Dict[str, JsonValue] = {"INFO": 5, "ERROR": ["red"], "DEBUG": None}

        assert ColouredFormatterConfig.check_colours(colours, scope="") is colours


class TestRawInputs:
    """Validators run before pydantic's own validation: unexpected raw types must end up as validation errors."""

    @pytest.mark.parametrize("colours", [5, None, ["red"]])
    def test_non_string_log_colours(self, payload: Dict[str, JsonValue], colours: JsonValue) -> None:
        payload["log_colors"] = {"ERROR": colours}

        with pytest.raises(ValidationError) as exc_info:
            ColouredFormatterConfig.model_validate(payload)

        assert exc_info.value.errors()[0]["type"] == "string_type"

    @pytest.mark.parametrize("value", ["red", 5, None])
    def test_non_mapping_log_colours(self, payload: Dict[str, JsonValue], value: JsonValue) -> None:
        payload["log_colors"] = value

        with pytest.raises(ValidationError) as exc_info:
            ColouredFormatterConfig.model_validate(payload)

        assert exc_info.value.errors()[0]["type"] == "dict_type"

    @pytest.mark.parametrize("value", ["red", 5, None, {"message": 5}])
    def test_non_mapping_secondary_log_colours(self, payload: Dict[str, JsonValue], value: JsonValue) -> None:
        payload["secondary_log_colors"] = value

        with pytest.raises(ValidationError) as exc_info:
            ColouredFormatterConfig.model_validate(payload)

        assert exc_info.value.errors()[0]["type"] == "dict_type"


class TestExport:
    def test_exports_dict_config_factory_keys(self, payload: Dict[str, JsonValue]) -> None:
        payload["stream"] = "ext://sys.stdout"
        payload["secondary_log_colors"] = {"message": {"error": "red"}}

        exported = ColouredFormatterConfig.model_validate(payload).model_dump(mode="json", by_alias=True)

        assert exported == {
            "()": FACTORY,
            "fmt": "%(log_color)s%(levelname)s - %(message)s",
            "datefmt": None,
            "style": "%",
            "log_colors": {
                "DEBUG": "white",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red,bg_white",
            },
            "secondary_log_colors": {"message": {"ERROR": "red"}},
            "reset": True,
            "stream": "ext://sys.stdout",
        }

    def test_export_round_trips(self, payload: Dict[str, JsonValue]) -> None:
        formatter = ColouredFormatterConfig.model_validate(payload)

        assert ColouredFormatterConfig.model_validate(formatter.model_dump(mode="json", by_alias=True)) == formatter

    @pytest.mark.usefixtures("isolated_logging")
    def test_export_builds_a_colorlog_formatter(self, payload: Dict[str, JsonValue]) -> None:
        payload.update(
            datefmt="%H",
            stream="ext://sys.stderr",
            log_colors={"INFO": "blue"},
            secondary_log_colors={"message": {"ERROR": "red"}},
            reset=False,
        )
        exported = ColouredFormatterConfig.model_validate(payload).model_dump(mode="json", by_alias=True)

        logging.config.dictConfig(
            {
                "version": 1,
                "formatters": {"coloured": exported},
                "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "coloured"}},
                "loggers": {"coloured-test": {"handlers": ["console"]}},
            }
        )

        (handler,) = logging.getLogger("coloured-test").handlers
        formatter = handler.formatter
        assert isinstance(formatter, colorlog.ColoredFormatter)
        assert formatter.datefmt == "%H"
        assert formatter.log_colors == {"INFO": "blue"}
        assert formatter.secondary_log_colors == {"message": {"ERROR": "red"}}
        assert formatter.reset is False
        assert formatter.stream is sys.stderr
