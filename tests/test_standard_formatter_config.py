from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.formatters.standard_formatter_config import StandardFormatterConfig


def test_defaults() -> None:
    formatter = StandardFormatterConfig.model_validate({"format": "%(message)s"})

    assert formatter.class_ == "logging.Formatter"
    assert formatter.fmt == "%(message)s"
    assert formatter.datefmt is None
    assert formatter.style == "%"


def test_parses_dict_config_keys() -> None:
    formatter = StandardFormatterConfig.model_validate(
        {"class": "package.CustomFormatter", "format": "{message}", "datefmt": "%Y", "style": "{"}
    )

    assert (formatter.class_, formatter.fmt, formatter.datefmt, formatter.style) == (
        "package.CustomFormatter",
        "{message}",
        "%Y",
        "{",
    )


def test_is_a_base_formatter_config() -> None:
    assert issubclass(StandardFormatterConfig, BaseFormatterConfig)


def test_format_is_required() -> None:
    with pytest.raises(ValidationError, match="format"):
        StandardFormatterConfig.model_validate({})


def test_empty_format_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StandardFormatterConfig.model_validate({"format": ""})


def test_exports_dict_config_keys() -> None:
    formatter = StandardFormatterConfig(fmt="%(message)s", datefmt="%Y")

    assert formatter.model_dump(by_alias=True, exclude_none=True) == {
        "class": "logging.Formatter",
        "format": "%(message)s",
        "datefmt": "%Y",
        "style": "%",
    }
