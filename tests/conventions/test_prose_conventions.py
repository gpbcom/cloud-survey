from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path
from typing import List

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
PYTHON_FILES = sorted(path for folder in ("src", "scripts", "tests") for path in (PROJECT_ROOT / folder).rglob("*.py"))
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def semicolons(source: str) -> List[str]:
    """Report the semicolons of the comments, docstrings and logging messages: sentences end with a full stop."""
    found: List[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and ";" in token.string:
            found.append(f"line {token.start[0]}: comment")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring and ";" in docstring:
                found.append(f"line {node.body[0].lineno}: docstring")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS:
            for argument in node.args[:2]:
                for constant in ast.walk(argument):
                    if isinstance(constant, ast.Constant) and isinstance(constant.value, str) and ";" in constant.value:
                        found.append(f"line {constant.lineno}: log message")
    return found


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_no_semicolons_in_prose(path: Path) -> None:
    assert semicolons(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("# A comment; with a semicolon.\n", ["line 1: comment"]),
        ('def f():\n    """Do it; then stop."""\n', ["line 2: docstring"]),
        ('"""Module; docstring."""\n', ["line 1: docstring"]),
        ("class A:\n    'Class; docstring.'\n", ["line 2: docstring"]),
        ('logger.info("Crawled; written.")\n', ["line 1: log message"]),
        ('self.logger.warning(f"{a}; {b}")\n', ["line 1: log message"]),
        ('logger.log(10, "Level; message.")\n', ["line 1: log message"]),
        ('STYLE = "color: red; border: none;"\n', []),
        ('print("a; b")\n', []),
        ("# A comment. With a full stop.\n", []),
    ],
)
def test_checker(source: str, expected: List[str]) -> None:
    assert semicolons(source) == expected
