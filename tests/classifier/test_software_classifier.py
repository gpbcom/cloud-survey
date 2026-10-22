from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

import pytest
from pydantic import JsonValue, ValidationError

from classifier.exception import ClassificationRulesFileError
from classifier.software_classifier import SoftwareClassifier
from conf import CLASSIFICATION_RULES_PATH
from models.classification.audience_hint import AudienceHint
from models.classification.category_rule import CategoryRule
from models.classification.classification_rules import ClassificationRules
from models.classification.exception import IncompleteRulesError, InvalidRulePatternError, InvalidRuleSlugError
from models.cloud.enums import DeliveryMethod, SoftwareCategory
from taxonomy.exception import UnknownTaxonomySlugError

DEV = SoftwareCategory.DEVELOPER_TOOL
USER = SoftwareCategory.END_USER_SOFTWARE
RuleModel = Union[Type[CategoryRule], Type[AudienceHint]]


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


def minimal_rules(**changes: JsonValue) -> Dict[str, JsonValue]:
    rules: Dict[str, JsonValue] = {
        "delivery_audiences": {method.value: ["end-user-software"] for method in DeliveryMethod},
    }
    rules.update(changes)
    return rules


class TestRules:
    def test_the_project_rules_are_valid(self, classifier: SoftwareClassifier) -> None:
        rules = classifier.rules

        assert set(rules.delivery_audiences) == set(DeliveryMethod)
        assert rules.category_rules
        assert rules.keyword_rules
        assert rules.noise_labels

    def test_every_category_but_other_has_keyword_or_label_rules(self, classifier: SoftwareClassifier) -> None:
        rules = classifier.rules
        ruled = {
            slug
            for rule in [*rules.keyword_rules, *rules.category_rules, *rules.name_rules]
            for slug in rule.categories
        }
        categories = [node.slug for node in classifier.taxonomy.nodes if not node.is_domain() and not node.hidden]

        assert [slug for slug in categories if slug not in ruled] == []

    @pytest.mark.parametrize("model", [CategoryRule, AudienceHint])
    def test_invalid_patterns_are_rejected(self, model: RuleModel) -> None:
        with pytest.raises(ValidationError, match="not a valid regular expression"):
            model.model_validate(
                {"pattern": "(unclosed", "categories": ["crm"], "audiences": ["developer-tool"]}.copy()
            )

    def test_rule_slugs_must_be_kebab_case(self) -> None:
        with pytest.raises(ValidationError, match="not a kebab-case taxonomy slug"):
            CategoryRule.model_validate({"pattern": "crm", "categories": ["Customer Relationship"]})

    def test_rule_slugs_lose_their_duplicates(self) -> None:
        assert CategoryRule.model_validate({"pattern": "crm", "categories": ["crm", "crm"]}).categories == ["crm"]

    def test_delivery_audiences_must_cover_every_method(self) -> None:
        rules = minimal_rules()
        mapping = rules["delivery_audiences"]
        assert isinstance(mapping, dict)
        mapping.pop(next(iter(mapping)))

        with pytest.raises(ValidationError, match="The `delivery_audiences` rules have no entry"):
            ClassificationRules.model_validate(rules)

    def test_unknown_slugs_are_rejected_when_the_classifier_is_built(self) -> None:
        rules = ClassificationRules.model_validate(
            minimal_rules(keyword_rules=[{"pattern": "crm", "categories": ["not-a-category"]}])
        )

        with pytest.raises(UnknownTaxonomySlugError, match="not-a-category"):
            SoftwareClassifier(rules=rules)

    def test_noise_patterns_are_validated(self) -> None:
        with pytest.raises(ValidationError, match="not a valid regular expression"):
            ClassificationRules.model_validate(minimal_rules(noise_labels=["(other"]))
        assert ClassificationRules.model_validate(minimal_rules(noise_labels=None)).noise_labels == []

    def test_errors_carry_their_details(self) -> None:
        pattern = InvalidRulePatternError("(", "missing )")
        incomplete = IncompleteRulesError("delivery_audiences", ["saas"])
        slug = InvalidRuleSlugError("Bad Slug")

        assert (pattern.pattern, pattern.reason, incomplete.field, incomplete.missing, slug.slug) == (
            "(",
            "missing )",
            "delivery_audiences",
            ["saas"],
            "Bad Slug",
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
        [(None, "cannot be read"), ("a: [", "not valid YAML"), ("delivery_audiences: {}", "rules are invalid")],
    )
    def test_unusable_files(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, content: Optional[str], reason: str
    ) -> None:
        path = tmp_path / "rules.yaml"
        if content is not None:
            path.write_text(content, encoding="utf-8")

        with pytest.raises(ClassificationRulesFileError, match=reason) as exc_info:
            SoftwareClassifier(path=path)

        assert exc_info.value.path == path
        assert any(record.levelno == logging.ERROR for record in caplog.records)


@pytest.mark.parametrize(
    ("name", "description", "labels", "categories"),
    [
        ("Greenhouse", "Hiring", ["Human Resources", "Talent Acquisition"], ["ats"]),
        ("Acme", "People platform", ["Human Resources", "Talent Acquisition"], ["hris", "ats"]),
        ("WooCommerce", "Sell online", ["CMS"], ["ecommerce"]),
        ("Qualys Cloud Agent", "Security assessment", ["Security"], ["vulnerability-management"]),
        ("Matomo", "Web analytics", ["CRM"], ["business-intelligence"]),
        ("MLflow", "Experiments", ["Machine Learning"], ["ai-ml"]),
        ("电商ERP", "订单管理", [], ["erp", "ecommerce"]),
        ("Hotel suite", "Rooms", ["Hospitality Cloud"], ["hospitality"]),
        ("Acme Mail", "Webmail", ["E-mail"], ["email"]),
        ("Acme", "Online courses", ["E-Learning"], ["e-learning"]),
        ("Salesforce", "Platform", ["Sales/crm"], ["crm"]),
        ("Odoo", "Open source ERP and CRM", [], ["erp"]),
        ("Acme", "Recruitment made simple", [], ["ats"]),
        ("Acme", "A tool", ["customer-relationship-management"], ["crm"]),
        ("WordPress", "Blogging platform", [], ["cms"]),
        ("Grafana", "Dashboards", ["Monitoring"], ["monitoring"]),
        ("PostgreSQL 16", "Open source", [], ["relational-database"]),
        ("GitLab CE", "DevSecOps platform", [], ["source-control"]),
        ("Ubuntu Server 24.04 LTS", "Linux", [], ["linux-distributions"]),
        ("钉钉", "智能协同办公平台", ["企业应用"], ["collaboration"]),
        ("用友", "企业资源管理", ["企业资源计划"], ["erp"]),
        ("某某", "测试", ["招聘"], ["ats"]),
        ("Astra Linux Special Edition", "Сертифицированная ОС", [], ["secure-domestic-os"]),  # noqa: RUF001
        ("Сервис", "Управляемая система управления базами данных", [], ["database"]),
        ("Сервис", "Резервное копирование виртуальных машин", ["Резервное копирование"], ["backup"]),
        ("Сервис", "Защита от DDoS-атак", ["Безопасность"], ["ddos-protection"]),
        ("Сервис", "Модели машинного обучения и нейросети", [], ["ai-ml"]),
        ("1С:Предприятие", "Учёт", [], ["erp"]),  # noqa: RUF001
        ("Amazon EC2", "Virtual servers in the cloud", ["Compute"], ["virtual-machines"]),
        ("Kubernetes Kapsule", "", ["Контейнеры"], ["kubernetes"]),
        ("ClickHouse", "Column-oriented database", ["Databases"], ["data-warehouse"]),
        ("Cloud CDN", "Deliver content close to users", ["Networking"], ["cdn"]),
        ("Mystery", "Nothing to see", [], ["other"]),
    ],
)
def test_categories(
    classifier: SoftwareClassifier, name: str, description: str, labels: List[str], categories: List[str]
) -> None:
    assert classifier.classify(name, description, labels).categories == categories


def test_labels_and_name_keywords_are_combined(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("CRM connector", "Sync", ["Storage"]).categories == ["storage", "crm"]


@pytest.mark.parametrize(
    ("name", "categories"),
    [
        ("Cloudtrio Grafana on Ubuntu 25.04", ["monitoring"]),
        ("Jenkins - Debian 12", ["ci-cd"]),
        ("WordPress with Windows Server 2022", ["cms"]),
        ("Ubuntu 24.04 LTS", ["linux-distributions"]),
        ("Grafana Virtual Machine", ["monitoring"]),
        ("Grafana on VMware Dev Tier", ["monitoring"]),
    ],
)
def test_packaging_suffix_is_ignored(classifier: SoftwareClassifier, name: str, categories: List[str]) -> None:
    assert classifier.classify(name, "Pre-configured image", []).categories == categories


def test_rules_without_packaging_suffix() -> None:
    rules = ClassificationRules.model_validate(
        minimal_rules(packaging_suffix=None, keyword_rules=[{"pattern": "ubuntu", "categories": ["crm"]}])
    )

    assert SoftwareClassifier(rules=rules).classify("Grafana on Ubuntu", "", []).categories == ["crm"]


def test_invalid_packaging_suffix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a valid regular expression"):
        ClassificationRules.model_validate(minimal_rules(packaging_suffix="(on"))


def test_labels_confirmed_by_the_keywords_are_kept(classifier: SoftwareClassifier) -> None:
    labels = ["Machine Learning", "DevOps", "Internet of Things", "Security"]

    assert classifier.classify("Acme Guard", "Threat detection for factories", labels).categories == ["security"]


def test_over_ticked_labels_nothing_confirms_give_way_to_the_keywords(classifier: SoftwareClassifier) -> None:
    labels = ["Business Applications", "Internet of Things", "Machine Learning", "Professional Services"]

    assert classifier.classify("Acme", "Data governance and data catalog", labels).categories == ["data-governance"]


def test_compliance_standards_are_not_a_security_operations_center(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Acme", "Compliance for SOC 2 and ISO 27001", []).categories == ["legal-compliance"]
    assert classifier.classify("Acme", "A 24/7 SOC watching your logs", []).categories == ["siem-soc"]


def test_an_umbrella_category_is_refined_by_the_description(classifier: SoftwareClassifier) -> None:
    result = classifier.classify("Acme Guard", "Firewall for factories", ["Security"])

    assert result.categories == ["network-security"]
    assert result.domains == ["security-services"]


def test_labels_come_before_the_description(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Acme", "Backup of your files", ["Object storage"]).categories == ["object-storage"]


def test_well_known_products_come_first(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Odoo Community", "Collaboration suite", ["Collaboration"]).categories == ["erp"]


def test_name_comes_before_the_description(classifier: SoftwareClassifier) -> None:
    assert classifier.classify("Acme CRM", "Backup of your contacts", []).categories == ["crm"]


class TestDomainsAndNoise:
    def test_a_label_telling_only_a_domain_files_the_item_in_it(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify("Acme", "", ["Data Platform"])

        assert (result.categories, result.domains) == ([], ["data-analytics"])

    def test_the_description_refines_a_domain_only_label(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify("Acme", "A cloud data warehouse", ["Data Platform"])

        assert result.categories == ["data-warehouse"]

    def test_the_description_outside_the_label_domains_is_the_last_keyword_resort(
        self, classifier: SoftwareClassifier
    ) -> None:
        result = classifier.classify(
            "Acme", "A cybersecurity platform securing remote access", ["Business applications"]
        )

        assert (result.categories, result.domains) == (["security"], ["security-services", "business-applications"])

    def test_noise_labels_are_ignored(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify("Acme", "", ["Продукты", "Other", "Powered by Exoscale"], DeliveryMethod.SAAS)

        assert result.categories == ["other"]
        assert classifier.is_noise("Услуги")
        assert not classifier.is_noise("Security")
        assert classifier.label_categories("Other") == []

    @pytest.mark.parametrize(
        ("label", "nodes"),
        [
            ("Databases", ["database"]),
            ("Базы данных", ["database"]),
            ("数据库", ["database"]),
            ("Compute", ["compute"]),
            ("Business Applications", ["business-applications"]),
            ("Backup & Recovery", ["backup"]),
        ],
    )
    def test_label_categories(self, classifier: SoftwareClassifier, label: str, nodes: List[str]) -> None:
        assert classifier.label_categories(label) == nodes

    def test_stored_label_links_replace_the_label_rules(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify("Acme", "", ["Whatever"], DeliveryMethod.SAAS, label_nodes=[["crm", "compute"]])

        assert (result.categories, result.domains) == (["crm"], ["compute", "sales-marketing"])


@pytest.mark.parametrize(
    ("delivery", "categories"),
    [
        (DeliveryMethod.VIRTUAL_MACHINE, ["machine-images"]),
        (DeliveryMethod.KUBERNETES, ["kubernetes"]),
        (DeliveryMethod.AI_MODEL, ["ai-models"]),
        (DeliveryMethod.ONE_CLICK_APP, ["one-click-apps"]),
        (DeliveryMethod.SAAS, ["other"]),
    ],
)
def test_the_delivery_method_classifies_the_unknown_software(
    classifier: SoftwareClassifier, delivery: DeliveryMethod, categories: List[str]
) -> None:
    assert classifier.classify("Mystery", "", [], delivery).categories == categories


@pytest.mark.parametrize(
    ("name", "labels", "delivery", "expected"),
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
def test_audiences(
    classifier: SoftwareClassifier,
    name: str,
    labels: List[str],
    delivery: DeliveryMethod,
    expected: List[SoftwareCategory],
) -> None:
    assert classifier.classify(name, "", labels, delivery).audiences == expected


def test_results_are_ordered_and_unique(classifier: SoftwareClassifier) -> None:
    result = classifier.classify("A", "", ["Security", "CRM", "Security", "crm"])

    assert result.categories == ["security", "crm"]
    assert result.domains == ["security-services", "sales-marketing"]
    assert result.audiences == [DEV, USER]


def test_the_domains_follow_the_categories(classifier: SoftwareClassifier) -> None:
    result = classifier.classify("PostgreSQL", "", [])

    assert (result.categories, result.domains) == (["relational-database"], ["databases"])


def test_a_domain_only_label_files_the_item_under_its_domain(classifier: SoftwareClassifier) -> None:
    result = classifier.classify("Acme", "", ["人工智能"])

    assert (result.categories, result.domains) == ([], ["ai-machine-learning"])
    result = classifier.classify("Acme", "", ["API服务", "人工智能"])
    assert (result.categories, result.domains) == (
        ["api-management"],
        ["application-integration", "ai-machine-learning"],
    )


def test_custom_rules() -> None:
    rules = ClassificationRules.model_validate(
        minimal_rules(
            keyword_rules=[{"pattern": "\\bcrm\\b", "categories": ["crm"]}],
            audience_hints=[{"pattern": "devs", "audiences": ["developer-tool"]}],
        )
    )
    classifier = SoftwareClassifier(rules=rules)

    acme_crm = classifier.classify("Acme CRM", "", ["For devs"])
    assert (acme_crm.audiences, acme_crm.categories) == ([DEV, USER], ["crm"])
    acme = classifier.classify("Acme", "", [], DeliveryMethod.API)
    assert (acme.audiences, acme.categories) == ([USER], ["other"])


class TestProducts:
    def test_a_product_gets_its_categories_and_audiences(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify_product("Elastic Compute Service", "Virtual machines", ["Compute"])

        assert (result.categories, result.audiences) == (["virtual-machines"], [DEV])

    def test_a_product_of_a_known_category_gets_its_audiences(self, classifier: SoftwareClassifier) -> None:
        assert classifier.classify_product("Acme CRM", "Customer relationship management", []).audiences == [USER]

    def test_an_audience_hint_is_kept(self, classifier: SoftwareClassifier) -> None:
        assert classifier.classify_product("Workspace", "", ["Business applications"]).audiences == [USER]

    def test_a_product_gets_no_delivery_fallback(self, classifier: SoftwareClassifier) -> None:
        result = classifier.classify_product("Mystery", "", [])

        assert (result.categories, result.audiences) == (["other"], [DEV])

    def test_the_product_audiences_are_validated(self) -> None:
        rules = ClassificationRules.model_validate(
            minimal_rules(product_audiences=["end-user-software", "developer-tool", "end-user-software"])
        )

        assert rules.product_audiences == [USER, DEV]
        assert ClassificationRules.model_validate(minimal_rules(product_audiences=None)).product_audiences == []
        with pytest.raises(ValidationError):
            ClassificationRules.model_validate(minimal_rules(product_audiences=["managers"]))

    def test_without_product_audiences_the_other_delivery_audiences_apply(self) -> None:
        classifier = SoftwareClassifier(rules=ClassificationRules.model_validate(minimal_rules()))

        assert classifier.classify_product("Acme", "", []).audiences == [USER]
