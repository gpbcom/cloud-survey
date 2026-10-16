from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import pytest
from pydantic import JsonValue, ValidationError

from classifier.exception import ClassificationRulesFileError
from classifier.software_classifier import SoftwareClassifier
from conf import CLASSIFICATION_RULES_PATH
from models.classification.category_hint import CategoryHint
from models.classification.classification_rules import ClassificationRules
from models.classification.exception import IncompleteRulesError, InvalidRulePatternError
from models.classification.type_rule import TypeRule
from models.cloud.enums import DeliveryMethod, SoftwareCategory, SoftwareType

DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


def minimal_rules(**changes: JsonValue) -> Dict[str, JsonValue]:
    rules: Dict[str, JsonValue] = {
        "type_categories": {kind.value: [] for kind in SoftwareType},
        "delivery_categories": {method.value: ["end-user-software"] for method in DeliveryMethod},
    }
    rules.update(changes)
    return rules


class TestRules:
    def test_the_project_rules_are_valid(self) -> None:
        rules = SoftwareClassifier().rules

        assert set(rules.type_categories) == set(SoftwareType)
        assert set(rules.delivery_categories) == set(DeliveryMethod)
        assert rules.category_rules
        assert rules.keyword_rules

    def test_every_type_but_other_has_a_category_and_rules(self) -> None:
        rules = SoftwareClassifier().rules
        ruled = {kind for rule in rules.keyword_rules for kind in rule.types}

        for kind in SoftwareType:
            if kind is not SoftwareType.OTHER:
                assert rules.type_categories[kind], kind
                assert kind in ruled, kind

    @pytest.mark.parametrize("model", [TypeRule, CategoryHint])
    def test_invalid_patterns_are_rejected(self, model: type[TypeRule]) -> None:
        with pytest.raises(ValidationError, match="not a valid regular expression"):
            model.model_validate({"pattern": "(unclosed", "types": ["crm"], "categories": ["developer-tool"]})

    @pytest.mark.parametrize("model", [TypeRule, CategoryHint])
    def test_patterns_must_be_text(self, model: type[TypeRule]) -> None:
        with pytest.raises(ValidationError, match="string"):
            model.model_validate({"pattern": 5, "types": ["crm"], "categories": ["developer-tool"]})

    @pytest.mark.parametrize("field", ["type_categories", "delivery_categories"])
    def test_mappings_must_cover_their_enum(self, field: str) -> None:
        rules = minimal_rules()
        mapping = rules[field]
        assert isinstance(mapping, dict)
        mapping.pop(next(iter(mapping)))

        with pytest.raises(ValidationError, match=f"The `{field}` rules have no entry"):
            ClassificationRules.model_validate(rules)

    def test_errors_carry_their_details(self) -> None:
        pattern = InvalidRulePatternError("(", "missing )")
        incomplete = IncompleteRulesError("type_categories", ["crm"])

        assert (pattern.pattern, pattern.reason, incomplete.field, incomplete.missing) == (
            "(",
            "missing )",
            "type_categories",
            ["crm"],
        )


class TestLoading:
    def test_default_rules_file(self) -> None:
        assert CLASSIFICATION_RULES_PATH.name == "classification.yaml"
        assert CLASSIFICATION_RULES_PATH.is_file()

    def test_given_rules_are_used(self) -> None:
        rules = ClassificationRules.model_validate(minimal_rules())

        assert SoftwareClassifier(rules=rules).rules is rules

    @pytest.mark.parametrize(
        ("content", "reason"),
        [(None, "cannot be read"), ("a: [", "not valid YAML"), ("type_categories: {}", "rules are invalid")],
    )
    def test_unusable_files(self, tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str, reason: str) -> None:
        path = tmp_path / "rules.yaml"
        if content is not None:
            path.write_text(content, encoding="utf-8")

        with pytest.raises(ClassificationRulesFileError, match=reason) as exc_info:
            SoftwareClassifier(path=path)

        assert exc_info.value.path == path
        assert any(record.levelno == logging.ERROR for record in caplog.records)


@pytest.mark.parametrize(
    ("name", "description", "categories", "types"),
    [
        ("Greenhouse", "Hiring", ["Human Resources", "Talent Acquisition"], [SoftwareType.ATS]),
        ("Acme", "People platform", ["Human Resources", "Talent Acquisition"], [SoftwareType.ATS, SoftwareType.HRIS]),
        ("WooCommerce", "Sell online", ["CMS"], [SoftwareType.ECOMMERCE]),
        ("Qualys Cloud Agent", "Security assessment", ["Security"], [SoftwareType.SECURITY]),
        ("Matomo", "Web analytics", ["CRM"], [SoftwareType.BUSINESS_INTELLIGENCE]),
        ("MLflow", "Experiments", ["Machine Learning"], [SoftwareType.AI_ML]),
        ("电商ERP", "订单管理", [], [SoftwareType.ERP, SoftwareType.ECOMMERCE]),
        ("Hotel suite", "Rooms", ["Hospitality Cloud"], [SoftwareType.OTHER]),
        ("Acme Mail", "Webmail", ["E-mail"], [SoftwareType.COMMUNICATION]),
        ("Acme", "Online courses", ["E-Learning"], [SoftwareType.E_LEARNING]),
        ("Salesforce", "Platform", ["Sales/crm"], [SoftwareType.CRM]),
        ("Odoo", "Open source ERP and CRM", [], [SoftwareType.ERP]),
        ("Acme", "Recruitment made simple", [], [SoftwareType.ATS]),
        ("Acme", "A tool", ["customer-relationship-management"], [SoftwareType.CRM]),
        ("WordPress", "Blogging platform", [], [SoftwareType.CMS]),
        ("Grafana", "Dashboards", ["Monitoring"], [SoftwareType.MONITORING]),
        ("PostgreSQL 16", "Open source", [], [SoftwareType.DATABASE]),
        ("GitLab CE", "DevSecOps platform", [], [SoftwareType.DEVOPS]),
        ("Ubuntu Server 24.04 LTS", "Linux", [], [SoftwareType.OPERATING_SYSTEM]),
        ("钉钉", "智能协同办公平台", ["企业应用"], [SoftwareType.COLLABORATION]),
        ("用友", "企业资源管理", ["企业资源计划"], [SoftwareType.ERP]),
        ("某某", "测试", ["招聘"], [SoftwareType.ATS]),
        ("Mystery", "Nothing to see", [], [SoftwareType.OTHER]),
    ],
)
def test_types(
    classifier: SoftwareClassifier, name: str, description: str, categories: List[str], types: List[SoftwareType]
) -> None:
    assert classifier.classify(name, description, categories)[1] == types


def test_categories_and_name_keywords_are_combined(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("CRM connector", "Sync", ["Storage"])[1] == [SoftwareType.CRM, SoftwareType.STORAGE]


@pytest.mark.parametrize(
    ("name", "types"),
    [
        ("Cloudtrio Grafana on Ubuntu 25.04", [SoftwareType.MONITORING]),
        ("Jenkins - Debian 12", [SoftwareType.DEVOPS]),
        ("WordPress with Windows Server 2022", [SoftwareType.CMS]),
        ("Ubuntu 24.04 LTS", [SoftwareType.OPERATING_SYSTEM]),
    ],
)
def test_packaging_suffix_is_ignored(classifier: SoftwareClassifier, name: str, types: List[SoftwareType]) -> None:
    assert classifier.classify(name, "Pre-configured image", [])[1] == types


def test_rules_without_packaging_suffix() -> None:
    rules = ClassificationRules.model_validate(
        minimal_rules(packaging_suffix=None, keyword_rules=[{"pattern": "ubuntu", "types": ["crm"]}])
    )

    assert SoftwareClassifier(rules=rules).classify("Grafana on Ubuntu", "", [])[1] == [SoftwareType.CRM]


def test_invalid_packaging_suffix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a valid regular expression"):
        ClassificationRules.model_validate(minimal_rules(packaging_suffix="(on"))


def test_categories_confirmed_by_the_keywords_are_kept(classifier: SoftwareClassifier) -> None:
    categories = ["Machine Learning", "DevOps", "Internet of Things", "Security"]

    assert classifier.classify("Acme Guard", "Threat detection for factories", categories)[1] == [SoftwareType.SECURITY]


def test_categories_come_before_the_description(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Acme", "Backup of your files", ["Storage"])[1] == [SoftwareType.STORAGE]


def test_well_known_products_come_first(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Odoo Community", "Collaboration suite", ["Collaboration"])[1] == [SoftwareType.ERP]


def test_name_comes_before_the_description(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Acme CRM", "Backup of your contacts", [])[1] == [SoftwareType.CRM]


@pytest.mark.parametrize(
    ("name", "categories", "delivery", "expected"),
    [
        ("Acme CRM", [], DeliveryMethod.CONTAINER, [USER]),
        ("Redis", [], DeliveryMethod.SAAS, [DEV]),
        ("Acme ML Studio", [], DeliveryMethod.SAAS, [DEV, USER]),
        ("Mystery", [], DeliveryMethod.CONTAINER, [DEV]),
        ("Mystery", [], DeliveryMethod.SAAS, [USER]),
        ("Mystery", ["Developer Tools"], DeliveryMethod.SAAS, [DEV]),
        ("Acme CRM", ["CRM", "Developer tools"], DeliveryMethod.SAAS, [DEV, USER]),
    ],
)
def test_categories(
    classifier: SoftwareClassifier,
    name: str,
    categories: List[str],
    delivery: DeliveryMethod,
    expected: List[SoftwareCategory],
) -> None:
    assert classifier.classify(name, "", categories, delivery)[0] == expected


def test_results_are_ordered_and_unique(classifier: SoftwareClassifier) -> None:
    categories, types = classifier.classify("A", "", ["Security", "CRM", "Security", "crm"])

    assert types == [SoftwareType.CRM, SoftwareType.SECURITY]
    assert categories == [DEV, USER]


def test_custom_rules() -> None:
    rules = ClassificationRules.model_validate(
        minimal_rules(
            type_categories={**{kind.value: [] for kind in SoftwareType}, "crm": ["end-user-software"]},
            keyword_rules=[{"pattern": "\\bcrm\\b", "types": ["crm"]}],
            category_hints=[{"pattern": "devs", "categories": ["developer-tool"]}],
        )
    )
    classifier = SoftwareClassifier(rules=rules)

    assert classifier.classify("Acme CRM", "", ["For devs"]) == ([DEV, USER], [SoftwareType.CRM])
    assert classifier.classify("Acme", "", [], DeliveryMethod.API) == ([USER], [SoftwareType.OTHER])
