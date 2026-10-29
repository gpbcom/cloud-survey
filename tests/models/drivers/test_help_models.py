from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.drivers.enums import (
    DriverColumn,
    DriverRole,
    DriverWarningKind,
    MetricSource,
    MetricValueColumn,
    ProviderMetric,
    WarningSeverity,
)
from models.drivers.exception import InvalidHelpTextError, UnknownHelpChoiceError
from models.drivers.help.choice_help import ChoiceHelp
from models.drivers.help.column_help import ColumnHelp
from models.drivers.help.driver_help import DriverHelp
from models.drivers.help.role_help import RoleHelp
from models.drivers.help.value_column_help import ValueColumnHelp
from models.drivers.help.warning_help import WarningHelp
from models.drivers.metrics.metric_coverage import MetricCoverage
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


class TestValueColumnHelp:
    def test_a_column(self) -> None:
        column = ValueColumnHelp.model_validate({"column": "fetched", "title": " Fetched ", "summary": " The\n day. "})

        assert (column.column, column.title, column.summary) == (MetricValueColumn.FETCHED, "Fetched", "The day.")

    @pytest.mark.parametrize(
        ("field", "value"), [("column", "colour"), ("title", "x" * 30), ("title", " "), ("summary", 3)]
    )
    def test_invalid_columns_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {"column": "url", "title": "Read from", "summary": "The page."}
        raw[field] = value

        with pytest.raises(ValidationError):
            ValueColumnHelp.model_validate(raw)

    def test_an_empty_text_is_reported(self) -> None:
        with pytest.raises(ValidationError) as caught:
            ValueColumnHelp.model_validate({"column": "url", "title": "Read from", "summary": "  "})

        assert isinstance(caught.value.errors()[0]["ctx"]["error"], InvalidHelpTextError)

    def test_the_lookup(self) -> None:
        help_ = DriverHelp.model_validate({"value_columns": [{"column": "source", "title": "S", "summary": "s"}]})

        source = help_.value_column(MetricValueColumn.SOURCE)
        assert source is not None
        assert source.title == "S"
        assert help_.value_column(MetricValueColumn.URL) is None


class TestChoiceHelp:
    def test_a_scale_and_a_scope_are_explained(self) -> None:
        scale = ChoiceHelp.model_validate({"choice": " count ", "summary": "log(1 + x)\n  for counts."})
        scope = ChoiceHelp.model_validate({"choice": "panel", "summary": "Yearly changes."})

        assert (scale.choice, scale.summary) == ("count", "log(1 + x) for counts.")
        assert DriverHelp(choices=[scale, scope]).choice("panel") == scope
        assert DriverHelp().choice("panel") is None

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [("choice", "weekly", UnknownHelpChoiceError), ("summary", " ", InvalidHelpTextError)],
    )
    def test_invalid_choices_are_refused(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        raw: Dict[str, JsonValue] = {"choice": "share", "summary": "As it is."}
        raw[field] = value

        with pytest.raises(ValidationError) as caught:
            ChoiceHelp.model_validate(raw)

        assert isinstance(caught.value.errors()[0]["ctx"]["error"], error)


class TestMetricCoverage:
    def test_a_coverage(self) -> None:
        coverage = MetricCoverage.model_validate(
            {
                "metric": "usage-search",
                "providers": 6,
                "first": "2009q1",
                "last": "2026Q3",
                "observations": 420,
                "sources": ["statcounter"],
            }
        )

        assert (coverage.metric, coverage.first, coverage.sources) == (
            ProviderMetric.USAGE_SEARCH,
            "2009Q1",
            [MetricSource.STATCOUNTER],
        )

    @pytest.mark.parametrize(("field", "value"), [("first", "2009-01"), ("last", 2026), ("providers", -1)])
    def test_invalid_coverages_are_refused(self, field: str, value: JsonValue) -> None:
        raw: Dict[str, JsonValue] = {
            "metric": "usage-search",
            "providers": 6,
            "first": "2009Q1",
            "last": "2026Q3",
            "observations": 420,
        }
        raw[field] = value

        with pytest.raises(ValidationError):
            MetricCoverage.model_validate(raw)
