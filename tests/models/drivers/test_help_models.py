from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.drivers.enums import DriverColumn, DriverRole, DriverWarningKind, ProviderMetric, WarningSeverity
from models.drivers.help.column_help import ColumnHelp
from models.drivers.help.driver_help import DriverHelp
from models.drivers.help.role_help import RoleHelp
from models.drivers.help.warning_help import WarningHelp
from models.drivers.results.driver_warning import DriverWarning


class TestRoleHelp:
    def test_the_lines_are_joined(self) -> None:
        role = RoleHelp.model_validate(
            {"role": "target", "title": " Target ", "symbol": "◎", "summary": "The rise.", "details": "One\n  two."}
        )

        assert (role.role, role.title, role.details) == (DriverRole.TARGET, "Target", "One two.")

    @pytest.mark.parametrize(
        ("field", "value"), [("role", "judge"), ("symbol", "abc"), ("title", " "), ("summary", "")]
    )
    def test_invalid_roles_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"role": "lag", "title": "Lag", "symbol": "↦", "summary": "s", "details": "d"}
        raw[field] = value

        with pytest.raises(ValidationError):
            RoleHelp.model_validate(raw)


class TestWarningHelp:
    def test_a_warning(self) -> None:
        warning = WarningHelp.model_validate(
            {"kind": "collinear", "severity": "caution", "title": "Collinear", "meaning": "m", "remedy": "r"}
        )

        assert (warning.kind, warning.severity) == (DriverWarningKind.COLLINEAR, WarningSeverity.CAUTION)

    @pytest.mark.parametrize(("field", "value"), [("kind", "oops"), ("severity", "fatal"), ("remedy", "")])
    def test_invalid_warnings_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {
            "kind": "constant",
            "severity": "info",
            "title": "t",
            "meaning": "m",
            "remedy": "r",
        }
        raw[field] = value

        with pytest.raises(ValidationError):
            WarningHelp.model_validate(raw)


class TestDriverHelp:
    def test_lookups(self) -> None:
        help_ = DriverHelp.model_validate(
            {
                "roles": [{"role": "control", "title": "Controls", "symbol": "▣", "summary": "s", "details": "d"}],
                "warnings": [{"kind": "unstable", "severity": "caution", "title": "t", "meaning": "m", "remedy": "r"}],
            }
        )

        control = help_.role(DriverRole.CONTROL)
        unstable = help_.warning(DriverWarningKind.UNSTABLE)
        assert control is not None
        assert control.title == "Controls"
        assert unstable is not None
        assert unstable.severity is WarningSeverity.CAUTION
        assert help_.role(DriverRole.LAG) is None
        assert help_.warning(DriverWarningKind.COLLINEAR) is None


class TestDriverWarning:
    def test_the_subjects_are_kept_once(self) -> None:
        warning = DriverWarning.model_validate(
            {"kind": "left-out", "message": " Left out. ", "subjects": ["regions", "regions", "age"]}
        )

        assert warning.message == "Left out."
        assert warning.subjects == [ProviderMetric.REGIONS, ProviderMetric.AGE]

    @pytest.mark.parametrize(("field", "value"), [("kind", "nope"), ("message", " "), ("subjects", ["nowhere"])])
    def test_invalid_warnings_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"kind": "constant", "message": "m"}
        raw[field] = value

        with pytest.raises(ValidationError):
            DriverWarning.model_validate(raw)


class TestColumnHelp:
    def test_a_column(self) -> None:
        column = ColumnHelp.model_validate(
            {"column": "rho-q", "title": "q (rho)", "summary": " The\n q. ", "reading": "r"}
        )

        assert (column.column, column.summary) == (DriverColumn.RHO_Q, "The q.")

    @pytest.mark.parametrize(("field", "value"), [("column", "zeta"), ("title", "x" * 30), ("reading", " ")])
    def test_invalid_columns_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"column": "beta", "title": "β", "summary": "s", "reading": "r"}
        raw[field] = value

        with pytest.raises(ValidationError):
            ColumnHelp.model_validate(raw)

    def test_the_lookup(self) -> None:
        help_ = DriverHelp.model_validate(
            {"columns": [{"column": "granger", "title": "G", "summary": "s", "reading": "r"}]}
        )

        granger = help_.column(DriverColumn.GRANGER)
        assert granger is not None
        assert granger.title == "G"
        assert help_.column(DriverColumn.BETA) is None
