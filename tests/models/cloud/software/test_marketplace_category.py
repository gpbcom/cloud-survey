from __future__ import annotations

from typing import Callable, List

import pytest
from pydantic import ValidationError

from models.cloud.enums import SoftwareCategory
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


def test_a_category_cleans_its_path_and_identifier() -> None:
    category = MarketplaceCategory.model_validate({"path": ["  AI  Agents ", "", "AI Agents", "Chat"], "id": 42})

    assert (category.path, category.id) == (["AI Agents", "Chat"], "42")
    assert category.label() == "AI Agents > Chat"
    assert MarketplaceCategory(path=["A"], id="  ").id is None


@pytest.mark.parametrize("path", [[], ["", " "], ["a", "b", "c", "d", "e", "f", "g"]])
def test_a_category_has_one_to_six_levels(path: List[str]) -> None:
    with pytest.raises(ValidationError):
        MarketplaceCategory(path=path)


def test_a_category_is_above_its_children_only() -> None:
    parent, child = MarketplaceCategory(path=["A"]), MarketplaceCategory(path=["A", "B"])

    assert parent.is_above(child)
    assert not child.is_above(parent)
    assert not parent.is_above(parent)
    assert not MarketplaceCategory(path=["B"]).is_above(child)


def test_a_software_keeps_its_most_precise_distinct_paths(make_software: Callable[..., MarketplaceSoftware]) -> None:
    software = make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])

    paths = MarketplaceSoftware.model_validate(
        {
            **software.model_dump(),
            "marketplace_category_paths": [
                {"path": ["Data"]},
                {"path": ["Data", "Databases"], "id": "db"},
                MarketplaceCategory(path=["Data", "Databases"], id="duplicate"),
                {"path": ["Dev"]},
            ],
        }
    ).marketplace_category_paths

    assert paths == [MarketplaceCategory(path=["Data", "Databases"], id="db"), MarketplaceCategory(path=["Dev"])]
    assert (
        MarketplaceSoftware.model_validate(
            {**software.model_dump(), "marketplace_category_paths": []}
        ).marketplace_category_paths
        is None
    )


def test_the_category_paths_do_not_change_the_fingerprint(make_software: Callable[..., MarketplaceSoftware]) -> None:
    software = make_software("Postgres", ["database"], [SoftwareCategory.DEVELOPER_TOOL])
    with_paths = software.model_copy(update={"marketplace_category_paths": [MarketplaceCategory(path=["Data"])]})

    assert with_paths.fingerprint() == software.fingerprint()
    assert software.fingerprint() == (
        '{"name":"Postgres","description":"Postgres description","publisher":"ACME",'
        '"url":"https://marketplace.example.com/postgres","delivery":"saas","marketplace_categories":["database"]}'
    )
