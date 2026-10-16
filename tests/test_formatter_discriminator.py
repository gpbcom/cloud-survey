from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue

from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.enums import FormatterKind
from models.configuration.logging.formatters.coloured_formatter_config import ColouredFormatterConfig
from models.configuration.logging.formatters.standard_formatter_config import StandardFormatterConfig
from models.configuration.logging.utils.formatter_discriminator import FormatterDiscriminator


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ({}, FormatterKind.STANDARD),
        ({"format": "x"}, FormatterKind.STANDARD),
        ({"class": "logging.Formatter", "format": "x"}, FormatterKind.STANDARD),
        ({"()": "colorlog.ColoredFormatter"}, FormatterKind.COLOURED),
        ({"factory": "colorlog.ColoredFormatter"}, FormatterKind.COLOURED),
        ({"()": "colorlog.ColoredFormatter", "class": "logging.Formatter"}, FormatterKind.COLOURED),
    ],
)
def test_kind_of_raw_configuration(value: Dict[str, JsonValue], kind: FormatterKind) -> None:
    assert FormatterDiscriminator.get_kind(value) is kind


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (StandardFormatterConfig(fmt="x"), FormatterKind.STANDARD),
        (ColouredFormatterConfig(factory="colorlog.ColoredFormatter", fmt="x"), FormatterKind.COLOURED),
    ],
)
def test_kind_of_built_configuration(value: BaseFormatterConfig, kind: FormatterKind) -> None:
    assert FormatterDiscriminator.get_kind(value) is kind


@pytest.mark.parametrize("value", [None, "colorlog.ColoredFormatter", 42, ["()"]])
def test_unexpected_values_are_standard(value: JsonValue) -> None:
    assert FormatterDiscriminator.get_kind(value) is FormatterKind.STANDARD


def test_factory_keys() -> None:
    assert frozenset({"()", "factory"}) == FormatterDiscriminator.FACTORY_KEYS
