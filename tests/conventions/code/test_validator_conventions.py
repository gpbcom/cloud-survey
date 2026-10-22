from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

SRC_DIR = Path(__file__).parents[3] / "src"
SOURCE_FILES = sorted(SRC_DIR.rglob("*.py"))


def decorator_name(decorator: ast.expr) -> str:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target).rsplit(".", 1)[-1]


def validators_with_classmethod(source: str) -> List[str]:
    """Get the `field_validator` methods also decorated with `classmethod` (pydantic already makes them so)."""
    return [
        f"line {node.lineno}: {node.name}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and {"field_validator", "classmethod"} <= {decorator_name(decorator) for decorator in node.decorator_list}
    ]


def validators_not_in_before_mode(source: str) -> List[str]:
    """Get the `field_validator` decorators without `mode="before"`."""
    return [
        f"line {decorator.lineno}: {node.name}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if decorator_name(decorator) == "field_validator"
        and not (
            isinstance(decorator, ast.Call)
            and any(
                keyword.arg == "mode" and isinstance(keyword.value, ast.Constant) and keyword.value.value == "before"
                for keyword in decorator.keywords
            )
        )
    ]


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: str(path.relative_to(SRC_DIR)))
def test_field_validators_run_in_before_mode(path: Path) -> None:
    assert validators_not_in_before_mode(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("@field_validator('name', mode='before')\ndef check(cls, value): ...", []),
        ("@pydantic.field_validator('a', 'b', mode='before')\ndef check(cls, value): ...", []),
        ("@model_validator(mode='after')\ndef check(self): ...", []),
        ("@field_validator('name')\ndef check(cls, value): ...", ["line 1: check"]),
        ("@field_validator('name', mode='after')\ndef check(cls, value): ...", ["line 1: check"]),
        ("@field_validator('name', mode='wrap')\ndef check(cls, value, handler): ...", ["line 1: check"]),
        ("@field_validator\ndef check(cls, value): ...", ["line 1: check"]),
    ],
)
def test_before_mode_checker(source: str, expected: List[str]) -> None:
    assert validators_not_in_before_mode(source) == expected


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: str(path.relative_to(SRC_DIR)))
def test_field_validators_are_not_decorated_with_classmethod(path: Path) -> None:
    assert validators_with_classmethod(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("@field_validator('name')\ndef check(cls, value): ...", []),
        ("@classmethod\ndef build(cls): ...", []),
        ("@field_validator('name')\n@classmethod\ndef check(cls, value): ...", ["line 3: check"]),
        (
            "@pydantic.field_validator('a', 'b', mode='before')\n@classmethod\ndef check(cls, value): ...",
            ["line 3: check"],
        ),
    ],
)
def test_checker(source: str, expected: List[str]) -> None:
    assert validators_with_classmethod(source) == expected
