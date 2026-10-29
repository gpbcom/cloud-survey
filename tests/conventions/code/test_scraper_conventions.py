from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import List, Set

import pytest
from scrapling.spiders import Spider

SRC_DIR = Path(__file__).parents[3] / "src"
CRAWLER_FILES = sorted(path for path in (SRC_DIR / "crawler").rglob("*.py") if path.name != "__init__.py")


def scrapers_of(path: Path) -> List[type]:
    """Get the concrete scrapers a module defines: its `Spider` subclasses not named `Base...`."""
    name = ".".join(path.relative_to(SRC_DIR).with_suffix("").parts)
    module = importlib.import_module(name)
    return [
        member
        for member_name, member in inspect.getmembers(module, inspect.isclass)
        if member.__module__ == name and issubclass(member, Spider) and not member_name.startswith("Base")
    ]


def added_public_methods(scraper: type) -> List[str]:
    """Get the public methods a scraper defines that none of the classes it inherits from defines."""
    inherited: Set[str] = set()
    for base in scraper.__mro__[1:]:
        inherited.update(vars(base))
    return sorted(
        name
        for name, member in vars(scraper).items()
        if not name.startswith("_") and callable(member) and name not in inherited
    )


@pytest.mark.parametrize("path", CRAWLER_FILES, ids=lambda path: str(path.relative_to(SRC_DIR)))
def test_scrapers_expose_no_more_methods_than_their_base(path: Path) -> None:
    for scraper in scrapers_of(path):
        assert added_public_methods(scraper) == [], f"{scraper.__name__} adds public methods to its base"


def test_a_scraper_adding_a_public_method_is_reported() -> None:
    class BaseProbe(Spider):
        name = "probe-base"

    class Probe(BaseProbe):
        name = "probe"

        def extra(self) -> None:
            return None

        def _helper(self) -> None:
            return None

    assert added_public_methods(Probe) == ["extra"]
    assert added_public_methods(BaseProbe) == []
