from __future__ import annotations

import logging
from pathlib import Path

import pytest

from analytics.drivers.catalog.driver_help_loader import DriverHelpLoader
from analytics.drivers.exception import DriverHelpFileError
from models.drivers.enums import DriverColumn, DriverRole, DriverWarningKind


def test_every_role_and_warning_is_explained() -> None:
    help_ = DriverHelpLoader().load()

    assert [entry.role for entry in help_.roles] == list(DriverRole)
    assert {entry.kind for entry in help_.warnings} == set(DriverWarningKind)
    assert all(entry.meaning and entry.remedy for entry in help_.warnings)
    assert [entry.column for entry in help_.columns] == list(DriverColumn)


def test_a_missing_explanation_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    partial = tmp_path / "help.yaml"
    partial.write_text("roles: []\nwarnings: []\n", encoding="utf-8")

    help_ = DriverHelpLoader().load(partial)

    assert help_.roles == []
    assert any(record.levelno == logging.WARNING and "target" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("content", ["roles: [", "roles: [{role: judge}]"])
def test_a_broken_file_is_reported(tmp_path: Path, content: str) -> None:
    broken = tmp_path / "help.yaml"
    broken.write_text(content, encoding="utf-8")

    with pytest.raises(DriverHelpFileError):
        DriverHelpLoader().load(broken)
    with pytest.raises(DriverHelpFileError):
        DriverHelpLoader().load(tmp_path / "missing.yaml")
