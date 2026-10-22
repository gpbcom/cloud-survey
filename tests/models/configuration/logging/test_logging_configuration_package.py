from __future__ import annotations

import importlib
import inspect
import pkgutil
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import List

import pytest

import models.configuration.logging as package
from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.base.base_handler_config import BaseHandlerConfig
from models.configuration.logging.base.dict_config_model import DictConfigModel

PACKAGE_DIR = Path(package.__file__).parent
# `enums.py` and `exception.py` group several classes each: the one class per module rules do not apply.
GROUPING_MODULES = {"enums", "exception"}
ROOT_MODULES = ["__init__.py", "enums.py", "exception.py"]
SUB_PACKAGES = {"base", "config", "formatters", "handlers", "loggers", "utils"}
MODULES = [
    importlib.import_module(info.name)
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}.")
    if not info.ispkg
]
MODULE_IDS = [module.__name__.removeprefix(f"{package.__name__}.") for module in MODULES]
ENTITY_MODULES = [
    module for module in MODULES if module.__name__.removeprefix(f"{package.__name__}.") not in GROUPING_MODULES
]
ENTITY_MODULE_IDS = [module.__name__.removeprefix(f"{package.__name__}.") for module in ENTITY_MODULES]


def classes_defined_in(module: ModuleType) -> List[type]:
    return [cls for _, cls in inspect.getmembers(module, inspect.isclass) if cls.__module__ == module.__name__]


CLASSES = [cls for module in ENTITY_MODULES for cls in classes_defined_in(module)]


def sub_package_of(module: ModuleType) -> str:
    return module.__name__.removeprefix(f"{package.__name__}.").split(".")[0]


def test_python_files_only_live_in_sub_packages() -> None:
    assert sorted(path.name for path in PACKAGE_DIR.glob("*.py")) == ROOT_MODULES
    assert {path.name for path in PACKAGE_DIR.iterdir() if path.is_dir() and path.name != "__pycache__"} == SUB_PACKAGES


@pytest.mark.parametrize("sub_package", sorted(SUB_PACKAGES))
def test_sub_packages_are_python_packages(sub_package: str) -> None:
    assert (PACKAGE_DIR / sub_package / "__init__.py").is_file()


@pytest.mark.parametrize(
    "init_file", sorted(PACKAGE_DIR.rglob("__init__.py")), ids=lambda path: str(path.relative_to(PACKAGE_DIR))
)
def test_init_files_are_empty(init_file: Path) -> None:
    assert init_file.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize(
    ("sub_package", "base"),
    [("formatters", BaseFormatterConfig), ("handlers", BaseHandlerConfig)],
)
def test_entities_are_sorted_by_type(sub_package: str, base: type) -> None:
    for cls in CLASSES:
        is_concrete_entity = issubclass(cls, base) and cls is not base
        assert (sub_package_of(importlib.import_module(cls.__module__)) == sub_package) == is_concrete_entity, cls


def test_base_classes_live_in_base_sub_package() -> None:
    for cls in CLASSES:
        is_base_class = any(other is not cls and issubclass(other, cls) for other in CLASSES)
        assert (sub_package_of(importlib.import_module(cls.__module__)) == "base") == is_base_class, cls


def test_base_sub_package_holds_every_base_model() -> None:
    base_classes = {
        cls.__name__ for cls in CLASSES if sub_package_of(importlib.import_module(cls.__module__)) == "base"
    }

    assert base_classes == {"DictConfigModel", "LevelledModel", "BaseFormatterConfig", "BaseHandlerConfig"}
    assert all(issubclass(cls, DictConfigModel) for cls in CLASSES if cls.__name__ in base_classes)


@pytest.mark.parametrize("module", ENTITY_MODULES, ids=ENTITY_MODULE_IDS)
def test_each_module_defines_at_most_one_class(module: ModuleType) -> None:
    assert len(classes_defined_in(module)) <= 1


@pytest.mark.parametrize("module", MODULES, ids=MODULE_IDS)
def test_no_class_name_starts_with_underscore(module: ModuleType) -> None:
    assert not [cls.__name__ for cls in classes_defined_in(module) if cls.__name__.startswith("_")]


@pytest.mark.parametrize("module", ENTITY_MODULES, ids=ENTITY_MODULE_IDS)
def test_module_is_named_after_its_class(module: ModuleType) -> None:
    for cls in classes_defined_in(module):
        snake_case = "".join(f"_{char.lower()}" if char.isupper() else char for char in cls.__name__).lstrip("_")
        assert module.__name__.rsplit(".", 1)[-1] == snake_case


@pytest.mark.parametrize("module", MODULES, ids=MODULE_IDS)
def test_no_raw_functions(module: ModuleType) -> None:
    functions = [
        name for name, obj in inspect.getmembers(module, inspect.isfunction) if obj.__module__ == module.__name__
    ]

    assert not functions


def test_enums_module_only_holds_enums() -> None:
    enums = importlib.import_module(f"{package.__name__}.enums")

    classes = classes_defined_in(enums)
    assert classes
    assert all(issubclass(cls, StrEnum) for cls in classes)
