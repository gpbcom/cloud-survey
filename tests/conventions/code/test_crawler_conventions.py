from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

import pytest
from scrapling.spiders import Spider

PROJECT_ROOT = Path(__file__).parents[3]
SRC_DIR = PROJECT_ROOT / "src"
# The packages following the method layout conventions, with the install and migration scripts.
LAYOUT_PACKAGES = ["analytics", "catalogue", "classifier", "crawler", "gui", "llm", "storage", "taxonomy"]
CRAWLER_FILES = sorted(
    [path for package in LAYOUT_PACKAGES for path in (SRC_DIR / package).rglob("*.py")]
    + list((PROJECT_ROOT / "scripts").rglob("*.py"))
)
INTERNAL_HEADER = "# Internal Helpers Methods #"
PUBLIC_HEADER = "# Publicly Exposed Methods #"

Method = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def header_line(lines: List[str], node: ast.ClassDef, header: str) -> Optional[int]:
    end = node.end_lineno or node.lineno
    found = [number for number in range(node.lineno, end + 1) if lines[number - 1].strip() == header]
    return found[0] if found else None


def called_methods(method: Method) -> List[str]:
    """Get the `self.<method>(...)` calls of a method."""
    return [
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]


def convention_violations(source: str) -> List[str]:
    """Report the classes not following the method layout conventions.

    Special methods come before the sections, so they may call the helpers declared after them.
    """
    lines = source.splitlines()
    violations: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [child for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))]
        positions: Dict[str, int] = {method.name: method.lineno for method in methods}
        internal, public = header_line(lines, node, INTERNAL_HEADER), header_line(lines, node, PUBLIC_HEADER)
        if internal is not None and public is not None and internal > public:
            violations.append(f"{node.name}: the internal helpers section must come before the public section")
        for method in methods:
            where = f"{node.name}.{method.name}"
            decorators = {ast.unparse(decorator) for decorator in method.decorator_list}
            if decorators & {"staticmethod", "classmethod"}:
                violations.append(f"{where}: no `staticmethod` / `classmethod`")
            if method.name.startswith("__") and method.name.endswith("__"):
                sections = [line for line in (internal, public) if line is not None]
                if sections and method.lineno > min(sections):
                    violations.append(f"{where}: special methods come before the sections")
            elif method.name.startswith("_"):
                if internal is None or method.lineno < internal or (public is not None and method.lineno > public):
                    violations.append(f"{where}: must be in the `Internal Helpers Methods` section")
            elif public is None or method.lineno < public:
                violations.append(f"{where}: must be in the `Publicly Exposed Methods` section")
            is_special = method.name.startswith("__") and method.name.endswith("__")
            for callee in [] if is_special else called_methods(method):
                if callee != method.name and positions.get(callee, 0) > method.lineno:
                    violations.append(f"{where}: must be declared after `{callee}`, which it calls")
        if "parse" in positions and methods[-1].name != "parse":
            violations.append(f"{node.name}.parse: must be the last method")
    return violations


@pytest.mark.parametrize("path", CRAWLER_FILES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_classes_follow_the_method_layout(path: Path) -> None:
    assert convention_violations(path.read_text(encoding="utf-8")) == []


def compliant_class() -> str:
    return """
class Crawler:
    def __init__(self): ...

    ############################
    # Internal Helpers Methods #
    ############################

    def _clean(self): ...

    def _build(self):
        return self._clean() or self._build()

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract(self):
        return self._build()

    async def parse(self):
        return self.extract()
"""


def test_checker_accepts_the_layout() -> None:
    assert convention_violations(compliant_class()) == []


def test_checker_accepts_a_public_only_class() -> None:
    source = "class Crawler:\n    ############################\n    # Publicly Exposed Methods #\n"
    source += "    ############################\n\n    def extract(self): ...\n"

    assert convention_violations(source) == []


@pytest.mark.parametrize(
    ("old", "new", "violation"),
    [
        ("    def _clean(self): ...", "    @staticmethod\n    def _clean(): ...", "no `staticmethod`"),
        (
            "    def _clean(self): ...",
            "    @classmethod\n    def _clean(cls): ...",
            "no `staticmethod` / `classmethod`",
        ),
        ("    def extract(self):", "    def _extract(self):", "must be in the `Internal Helpers Methods` section"),
        ("    def _clean(self): ...", "    def clean(self): ...", "must be in the `Publicly Exposed Methods` section"),
        ("        return self.extract()", "        return 1\n\n    def extract2(self): ...", "must be the last method"),
        (
            "    def extract(self):\n        return self._build()",
            "    def extract(self):\n        return self.parse()",
            "must be declared after `parse`",
        ),
        ("    def __init__(self): ...\n", "", None),
    ],
)
def test_checker_reports_violations(old: str, new: str, violation: Optional[str]) -> None:
    source = compliant_class().replace(old, new)

    violations = convention_violations(source)

    if violation is None:
        assert violations == []
    else:
        assert any(violation in reported for reported in violations), violations


def test_checker_reports_misplaced_sections_and_special_methods() -> None:
    source = compliant_class()
    internal = "    ############################\n    # Internal Helpers Methods #\n    ############################\n"
    public = "    ############################\n    # Publicly Exposed Methods #\n    ############################\n"
    swapped = source.replace(internal, "@@").replace(public, internal).replace("@@", public)
    late_init = source.replace("    def __init__(self): ...\n", "").replace(
        "    def _clean(self): ...", "    def _clean(self): ...\n\n    def __init__(self): ..."
    )

    assert any("must come before the public section" in violation for violation in convention_violations(swapped))
    assert any("special methods come before" in violation for violation in convention_violations(late_init))


def crawler_classes() -> List[Type[Spider]]:
    """Get the crawlers (Scrapling spiders) defined in the `crawler` package."""
    package = importlib.import_module("crawler")
    modules = [importlib.import_module(info.name) for info in pkgutil.walk_packages(package.__path__, "crawler.")]
    return [
        value
        for module in modules
        for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, Spider) and value.__module__ == module.__name__
    ]


def test_crawlers_declare_their_constructor() -> None:
    crawlers = crawler_classes()
    missing = sorted(
        f"{crawler.__module__}.{crawler.__qualname__}" for crawler in crawlers if "__init__" not in vars(crawler)
    )

    assert crawlers
    assert missing == [], f"These crawlers must declare `__init__`: {missing}"


GUI_FILES = sorted((SRC_DIR / "gui").rglob("*.py"))


@pytest.mark.parametrize("path", GUI_FILES, ids=lambda path: str(path.relative_to(SRC_DIR)))
def test_gui_modules_hold_one_class_each(path: Path) -> None:
    classes = [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef)]

    assert len(classes) <= 1, f"{path.name} holds several classes: {classes}"
