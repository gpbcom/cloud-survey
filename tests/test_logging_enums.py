from __future__ import annotations

import logging

import pytest

from models.configuration.logging.enums import FormatterKind, LogLevel


class TestLogLevel:
    @pytest.mark.parametrize("level", list(LogLevel))
    def test_levels_match_standard_logging_levels(self, level: LogLevel) -> None:
        assert logging.getLevelNamesMapping()[level.value] == getattr(logging, level.name)

    def test_members(self) -> None:
        assert [level.value for level in LogLevel] == ["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="is not a valid"):
            LogLevel("TRACE")


class TestFormatterKind:
    def test_members(self) -> None:
        assert {kind.name: kind.value for kind in FormatterKind} == {"STANDARD": "standard", "COLOURED": "coloured"}

    @pytest.mark.parametrize("kind", list(FormatterKind))
    def test_is_a_string(self, kind: FormatterKind) -> None:
        assert isinstance(kind, str)
        assert FormatterKind(kind.value) is kind

    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="is not a valid"):
            FormatterKind("json")
