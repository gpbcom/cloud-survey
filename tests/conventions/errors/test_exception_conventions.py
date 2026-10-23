from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Type

import pytest

PROJECT_ROOT = Path(__file__).parents[3]
SRC_DIR = PROJECT_ROOT / "src"
SOURCE_FILES = sorted(SRC_DIR.rglob("*.py"))
SCRIPT_FILES = sorted(path for path in (PROJECT_ROOT / "scripts").glob("*.py"))
PACKAGES = [
    "analytics",
    "catalogue",
    "classifier",
    "conf",
    "crawler",
    "gui",
    "llm",
    "logger",
    "models",
    "storage",
    "taxonomy",
    "scripts",
]


def import_all_modules() -> List[ModuleType]:
    modules = [importlib.import_module("main")]
    for name in PACKAGES:
        package = importlib.import_module(name)
        modules.append(package)
        prefix = f"{name}."
        modules += [importlib.import_module(info.name) for info in pkgutil.walk_packages(package.__path__, prefix)]
    return modules


MODULES = import_all_modules()
EXCEPTION_MODULES = [module for module in MODULES if module.__name__.rsplit(".", 1)[-1] == "exception"]


def exceptions_defined_in(module: ModuleType) -> List[Type[BaseException]]:
    return [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__module__ == module.__name__ and issubclass(cls, BaseException)
    ]


def package_of(path: Path) -> str:
    root = PROJECT_ROOT if path.is_relative_to(PROJECT_ROOT / "scripts") else SRC_DIR
    parts = list(path.relative_to(root).with_suffix("").parts)
    return ".".join(parts[:-1])


class RaiseChecker(ast.NodeVisitor):
    """Report the `raise` statements not using an exception of the package (or a parent package) `exception.py`."""

    def __init__(self, package: str, is_exception_module: bool) -> None:
        self.package = package
        self.is_exception_module = is_exception_module
        self.imported_from: Dict[str, str] = {}
        self.violations: List[str] = []

    def check(self, source: str) -> List[str]:
        self.visit(ast.parse(source))
        return self.violations

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.imported_from[alias.asname or alias.name] = node.module or ""

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is None:
            return  # Bare re-raise.
        target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if not isinstance(target, ast.Name):
            self.violations.append(f"line {node.lineno}: raise an exception imported by name")
            return
        module = self.imported_from.get(target.id)
        if module is None:
            if not self.is_exception_module:
                self.violations.append(f"line {node.lineno}: `{target.id}` is not imported from an `exception` module")
            return
        exception_package = module.removesuffix(".exception")
        is_in_scope = self.package == exception_package or self.package.startswith(f"{exception_package}.")
        if not module.endswith(".exception") or not is_in_scope:
            self.violations.append(
                f"line {node.lineno}: `{target.id}` must come from the `exception.py` of `{self.package}` "
                f"or of a parent package, not from `{module}`"
            )


@pytest.mark.parametrize("module", MODULES, ids=lambda module: module.__name__)
def test_exceptions_are_only_defined_in_exception_modules(module: ModuleType) -> None:
    if module in EXCEPTION_MODULES:
        return
    assert exceptions_defined_in(module) == []


@pytest.mark.parametrize("module", EXCEPTION_MODULES, ids=lambda module: module.__name__)
def test_exception_module_has_a_single_root_error(module: ModuleType) -> None:
    errors = exceptions_defined_in(module)
    roots = [error for error in errors if not any(base in errors for base in error.__mro__[1:])]

    assert len(roots) == 1, roots
    (root,) = roots
    assert issubclass(root, Exception)
    assert all(issubclass(error, root) for error in errors)
    assert all(error.__name__.endswith("Error") for error in errors)


def test_every_package_raising_errors_has_an_exception_module() -> None:
    names = {module.__name__ for module in EXCEPTION_MODULES}

    assert names == {
        "analytics.drivers.exception",
        "analytics.history.exception",
        "classifier.exception",
        "crawler.exception",
        "llm.exception",
        "logger.exception",
        "models.classification.exception",
        "models.cloud.exception",
        "models.stats.exception",
        "models.configuration.llm.exception",
        "models.configuration.logging.exception",
        "models.correspondence.exception",
        "models.drivers.exception",
        "models.history.exception",
        "models.markets.exception",
        "models.storage.filters.exception",
        "models.taxonomy.exception",
        "scripts.exception",
        "storage.exception",
        "taxonomy.exception",
    }


@pytest.mark.parametrize("path", SOURCE_FILES + SCRIPT_FILES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_raised_exceptions_come_from_the_package_exception_module(path: Path) -> None:
    checker = RaiseChecker(package_of(path), is_exception_module=path.name == "exception.py")

    assert checker.check(path.read_text(encoding="utf-8")) == []


class TestRaiseChecker:
    @pytest.mark.parametrize(
        ("package", "source"),
        [
            ("crawler", "from crawler.exception import CrawlerError\nraise CrawlerError('x')"),
            ("crawler.cloud", "from crawler.exception import CrawlerError\nraise CrawlerError('x')"),
            ("models.cloud", "from models.cloud.exception import EmptyCurrencyError\nraise EmptyCurrencyError"),
            ("crawler", "try:\n    pass\nexcept ValueError:\n    raise"),
        ],
    )
    def test_allowed(self, package: str, source: str) -> None:
        assert RaiseChecker(package, is_exception_module=False).check(source) == []

    @pytest.mark.parametrize(
        ("package", "source", "violation"),
        [
            ("crawler", "raise ValueError('x')", "not imported from an `exception` module"),
            ("crawler", "raise NotImplementedError", "not imported from an `exception` module"),
            (
                "crawler",
                "from logger.exception import LoggerError\nraise LoggerError('x')",
                "not from `logger.exception`",
            ),
            ("crawler", "from crawler.errors import Oops\nraise Oops()", "not from `crawler.errors`"),
            ("crawler", "import crawler.exception\nraise crawler.exception.CrawlerError('x')", "imported by name"),
            (
                "models",
                "from models.cloud.exception import CloudModelError\nraise CloudModelError('x')",
                "not from `models.cloud.exception`",
            ),
        ],
    )
    def test_rejected(self, package: str, source: str, violation: str) -> None:
        violations = RaiseChecker(package, is_exception_module=False).check(source)

        assert len(violations) == 1
        assert violation in violations[0]
