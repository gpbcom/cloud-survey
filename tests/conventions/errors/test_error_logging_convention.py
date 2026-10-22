from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

PROJECT_ROOT = Path(__file__).parents[3]
SRC_DIR = PROJECT_ROOT / "src"
# The models only validate data: they raise without logging.
CHECKED_FILES = sorted(
    [path for path in SRC_DIR.rglob("*.py") if path.relative_to(SRC_DIR).parts[0] != "models"]
    + list((PROJECT_ROOT / "scripts").rglob("*.py"))
)
ERROR_LOG_METHODS = {"error", "exception"}


def is_error_log(statement: ast.stmt) -> bool:
    """Tell whether a statement is a `<logger>.error(...)` or `<logger>.exception(...)` call."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr in ERROR_LOG_METHODS
    )


def unlogged_raises(source: str) -> List[int]:
    """Get the lines of the `raise <exception>` statements not directly preceded by an error log.

    A bare `raise`, which re-raises the handled exception, is exempt.
    """
    lines: List[int] = []
    for node in ast.walk(ast.parse(source)):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block):
                if not isinstance(statement, ast.Raise) or statement.exc is None:
                    continue
                if index == 0 or not is_error_log(block[index - 1]):
                    lines.append(statement.lineno)
    return lines


@pytest.mark.parametrize("path", CHECKED_FILES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_raised_exceptions_are_logged_as_errors(path: Path) -> None:
    assert unlogged_raises(path.read_text(encoding="utf-8")) == [], f"{path.name}: raise without an error log"


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    logger.error('failed')\n    raise ValueError()\n",
        "def f():\n    try:\n        g()\n    except OSError:\n        self.logger.exception('failed')\n"
        "        raise ValueError() from None\n",
        "def f():\n    try:\n        g()\n    except OSError:\n        raise\n",
        "def f():\n    if x:\n        log.error('a')\n        raise A()\n"
        "    else:\n        log.error('b')\n        raise B()\n",
    ],
    ids=["error", "exception", "re-raise", "branches"],
)
def test_checker_accepts(source: str) -> None:
    assert unlogged_raises(source) == []


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        ("def f():\n    raise ValueError()\n", [2]),
        ("def f():\n    logger.warning('w')\n    raise ValueError()\n", [3]),
        ("def f():\n    logger.error('e')\n    x = 1\n    raise ValueError()\n", [4]),
        ("def f():\n    for x in y:\n        pass\n    else:\n        raise ValueError()\n", [5]),
        ("def f():\n    try:\n        g()\n    finally:\n        raise ValueError()\n", [5]),
        ("def f():\n    error('e')\n    raise ValueError()\n", [3]),
    ],
    ids=["alone", "warning", "not-adjacent", "else", "finally", "not-a-logger-call"],
)
def test_checker_rejects(source: str, lines: List[int]) -> None:
    assert unlogged_raises(source) == lines
