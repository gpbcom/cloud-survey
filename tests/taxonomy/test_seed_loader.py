from __future__ import annotations

import logging
from pathlib import Path

import pytest

from classifier.software_classifier import SoftwareClassifier
from conf import LABEL_SEED_PATH, TAXONOMY_SEED_PATH
from models.classification.classification_rules import ClassificationRules
from models.cloud.enums import DeliveryMethod
from taxonomy.exception import TaxonomySeedFileError, UnknownTaxonomySlugError
from taxonomy.seed_loader import TaxonomySeedLoader


class TestProjectTaxonomy:
    def test_the_project_taxonomy_is_rich_and_valid(self) -> None:
        taxonomy = TaxonomySeedLoader().load_taxonomy()

        assert TAXONOMY_SEED_PATH.is_file()
        assert len(taxonomy.domains()) >= 25
        assert len([node for node in taxonomy.nodes if not node.is_domain()]) >= 180
        assert all(taxonomy.children(domain.slug) for domain in taxonomy.domains())

    def test_every_node_is_named_in_three_languages_and_described(self) -> None:
        taxonomy = TaxonomySeedLoader().load_taxonomy()

        assert [
            node.slug for node in taxonomy.nodes if not (node.name_ru and node.name_zh and node.description_en)
        ] == []

    def test_other_is_the_hidden_last_resort(self) -> None:
        taxonomy = TaxonomySeedLoader().load_taxonomy()
        other = taxonomy.node("other")

        assert other is not None
        assert other.hidden
        assert taxonomy.domain_of("other") == "unclassified"

    def test_the_rules_only_name_known_nodes(self) -> None:
        loader = TaxonomySeedLoader()

        loader.check(loader.load_taxonomy(), SoftwareClassifier().rules, loader.load_labels())


class TestLoading:
    @pytest.mark.parametrize(
        ("content", "reason"),
        [
            (None, "cannot be read"),
            ("domains: [", "not valid YAML"),
            ("domains: []", "content is invalid"),
        ],
    )
    def test_unusable_taxonomy_files(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str, reason: str
    ) -> None:
        path = tmp_path / "taxonomy.yaml"
        if content is not None:
            path.write_text(content, encoding="utf-8")

        with pytest.raises(TaxonomySeedFileError, match=reason) as exc_info:
            TaxonomySeedLoader().load_taxonomy(path)

        assert exc_info.value.path == path
        assert any(record.levelno == logging.ERROR for record in caplog.records)

    def test_a_repeated_slug_is_not_a_valid_tree(self, tmp_path: Path) -> None:
        path = tmp_path / "taxonomy.yaml"
        category = "{slug: crm, en: CRM, ru: CRM, zh: CRM, description: CRM.}"
        domain = "{slug: %s, en: D, ru: D, zh: D, description: D., categories: [%s]}"
        path.write_text(f"domains: [{domain % ('one', category)}, {domain % ('two', category)}]", encoding="utf-8")

        with pytest.raises(TaxonomySeedFileError, match="valid tree"):
            TaxonomySeedLoader().load_taxonomy(path)

    def test_a_missing_label_seed_is_empty(self, tmp_path: Path) -> None:
        assert TaxonomySeedLoader().load_labels(tmp_path / "none.yaml").labels == []
        assert LABEL_SEED_PATH.name == "label-seed.yaml"

    def test_a_label_seed_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "labels.yaml"
        path.write_text(
            "labels: [{text: ' Базы  данных ', en: Databases, links: [database, database]}]", encoding="utf-8"
        )

        (label,) = TaxonomySeedLoader().load_labels(path).labels

        assert (label.text, label.en, label.links, label.noise) == ("Базы данных", "Databases", ["database"], False)


class TestCheck:
    def test_unknown_slugs_are_reported(self, caplog: pytest.LogCaptureFixture) -> None:
        loader = TaxonomySeedLoader()
        rules = ClassificationRules.model_validate(
            {
                "delivery_audiences": {method.value: ["end-user-software"] for method in DeliveryMethod},
                "keyword_rules": [{"pattern": "x", "categories": ["nowhere"]}],
                "delivery_categories": {"saas": ["neither"]},
            }
        )

        with pytest.raises(UnknownTaxonomySlugError) as exc_info:
            loader.check(loader.load_taxonomy(), rules)

        assert any("'nowhere'" in problem for problem in exc_info.value.problems)
        assert any("'neither'" in problem for problem in exc_info.value.problems)
        assert any(record.levelno == logging.ERROR for record in caplog.records)
