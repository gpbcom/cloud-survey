from __future__ import annotations

from typing import List, Optional

import pytest
from pydantic import JsonValue, ValidationError

from models.classification.classification import Classification
from models.cloud.enums import SoftwareCategory
from models.taxonomy.exception import InvalidSlugError, InvalidTaxonomyTreeError
from models.taxonomy.nodes.taxonomy import Taxonomy
from models.taxonomy.nodes.taxonomy_node import TaxonomyNode
from models.taxonomy.seed.seed_label import SeedLabel

DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE


def node(slug: str, parent: Optional[str] = None, **fields: JsonValue) -> TaxonomyNode:
    return TaxonomyNode.model_validate(
        {"slug": slug, "parent_slug": parent, "name_en": slug, "name_ru": slug, "name_zh": slug, **fields}
    )


@pytest.fixture
def taxonomy() -> Taxonomy:
    return Taxonomy(
        nodes=[
            node("data", audiences=["developer-tool"]),
            node("database", "data", umbrella=True),
            node("data-warehouse", "data"),
            node("business", audiences=["end-user-software"]),
            node("crm", "business"),
            node("bi", "business", audiences=["end-user-software", "developer-tool"]),
        ]
    )


class TestNodes:
    @pytest.mark.parametrize("slug", ["Object Storage", "object_storage", "-storage", "storage-", ""])
    def test_slugs_are_kebab_case(self, slug: str) -> None:
        with pytest.raises(ValidationError):
            node(slug)

    def test_the_slug_error_names_the_slug(self) -> None:
        assert InvalidSlugError("A B").slug == "A B"

    def test_audiences_lose_their_duplicates(self) -> None:
        assert node("x", audiences=["developer-tool", "developer-tool"]).audiences == [DEV]

    def test_a_domain_has_no_parent(self) -> None:
        assert node("data").is_domain()
        assert not node("crm", "business").is_domain()


class TestTaxonomy:
    def test_lookups(self, taxonomy: Taxonomy) -> None:
        assert [domain.slug for domain in taxonomy.domains()] == ["data", "business"]
        assert [category.slug for category in taxonomy.children("business")] == ["crm", "bi"]
        assert taxonomy.is_domain("data")
        assert taxonomy.is_category("crm")
        assert not taxonomy.is_category("nowhere")
        assert taxonomy.domain_of("crm") == "business"
        assert taxonomy.domain_of("data") == "data"
        assert taxonomy.domain_of("nowhere") is None

    def test_a_category_inherits_the_audiences_of_its_domain(self, taxonomy: Taxonomy) -> None:
        assert taxonomy.audiences_of("database") == [DEV]
        assert taxonomy.audiences_of("bi") == [USER, DEV]
        assert taxonomy.audiences_of("nowhere") == []

    def test_the_umbrella_category_of_a_domain(self, taxonomy: Taxonomy) -> None:
        assert taxonomy.umbrella_of("data") == "database"
        assert taxonomy.umbrella_of("business") is None

    def test_slugs_are_ordered_and_unknown_ones_dropped(self, taxonomy: Taxonomy) -> None:
        assert taxonomy.ordered(["crm", "nowhere", "database", "crm"]) == ["database", "crm"]

    @pytest.mark.parametrize(
        ("nodes", "problem"),
        [
            ([node("a"), node("a")], "is repeated"),
            ([node("a", "nowhere")], "unknown domain"),
            ([node("a"), node("b", "a"), node("c", "b")], "not a domain"),
        ],
    )
    def test_invalid_trees(self, nodes: List[TaxonomyNode], problem: str) -> None:
        with pytest.raises(ValidationError, match=problem):
            Taxonomy(nodes=nodes)

    def test_the_tree_error_lists_its_problems(self) -> None:
        assert InvalidTaxonomyTreeError(["one", "two"]).problems == ["one", "two"]


class TestSeedLabelAndClassification:
    def test_a_seed_label_is_cleaned(self) -> None:
        label = SeedLabel.model_validate({"text": " Базы   данных ", "links": None, "same_as": " Databases "})

        assert (label.text, label.links, label.same_as) == ("Базы данных", [], "Databases")

    def test_a_classification_always_has_a_domain_and_an_audience(self) -> None:
        with pytest.raises(ValidationError):
            Classification(audiences=[DEV], categories=["crm"], domains=[])
        with pytest.raises(ValidationError):
            Classification(audiences=[], categories=["crm"], domains=["business"])
