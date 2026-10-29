from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Dict, List

import pytest

SRC_DIR = Path(__file__).parents[3] / "src"
REPOSITORY_FILES = sorted((SRC_DIR / "storage" / "repositories").rglob("*_repository.py"))
CRUDL = ("create", "read", "update", "delete", "list")


def operations_of(path: Path) -> Dict[str, Dict[str, bool]]:
    """Tell, for each repository class a module defines (named `...Repository`), which CRUDL operations are
    coroutines."""
    name = ".".join(path.relative_to(SRC_DIR).with_suffix("").parts)
    module = importlib.import_module(name)
    return {
        member_name: {operation: inspect.iscoroutinefunction(getattr(member, operation, None)) for operation in CRUDL}
        for member_name, member in inspect.getmembers(module, inspect.isclass)
        if member.__module__ == name and member_name.endswith("Repository")
    }


def missing_operations(operations: Dict[str, bool]) -> List[str]:
    """Get the CRUDL operations a repository lacks, or does not declare as coroutines."""
    return [operation for operation in CRUDL if not operations.get(operation, False)]


def test_every_repository_module_is_checked() -> None:
    assert len(REPOSITORY_FILES) >= 20


@pytest.mark.parametrize("path", REPOSITORY_FILES, ids=lambda path: str(path.relative_to(SRC_DIR)))
def test_repositories_offer_the_crudl_operations(path: Path) -> None:
    repositories = operations_of(path)

    assert repositories, f"{path.name} defines no repository class"
    for name, operations in repositories.items():
        assert missing_operations(operations) == [], f"{name} lacks CRUDL operations"


def test_the_checker_reports_a_missing_operation() -> None:
    class PartialRepository:
        async def create(self) -> None: ...

        async def read(self) -> None: ...

        def update(self) -> None: ...

    operations = {
        operation: inspect.iscoroutinefunction(getattr(PartialRepository, operation, None)) for operation in CRUDL
    }

    assert missing_operations(operations) == ["update", "delete", "list"]
