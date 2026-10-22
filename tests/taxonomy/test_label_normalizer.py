from __future__ import annotations

from typing import List

import pytest

from models.taxonomy.enums import Language
from taxonomy.label_normalizer import LabelNormalizer


@pytest.mark.parametrize(
    ("spellings", "key"),
    [
        (["Databases", "DataBases", "Database", "DATABASE", "Data Bases"], "database"),
        (["E-commerce", "eCommerce", "Ecommerce", "E-Commerce", "ECommerce"], "ecommerce"),
        (["Backup & Recovery", "Backup and Recovery", "Backup And Recovery", "backup and recovery"], "backuprecovery"),
        (["AI + Machine Learning", "AI and machine learning"], "aimachinelearning"),
        (["Other", "Others", "OTHER"], "other"),
        (["Technologies", "Technology"], "technology"),
        (["Business", "business"], "business"),
        (["CI/CD", "CI CD", "ci-cd"], "cicd"),
        (["Identity & Access Management", "Identity and Access Management"], "identityaccessmanagement"),
        (["  Storage ", "Storage"], "storage"),
    ],
)
def test_spellings_of_a_label_share_a_key(spellings: List[str], key: str) -> None:
    normalizer = LabelNormalizer()

    assert {normalizer.key(spelling) for spelling in spellings} == {key}


def test_latin_look_alikes_in_cyrillic_words_are_read_as_cyrillic() -> None:
    normalizer = LabelNormalizer()
    latin_c = "CУБД"  # noqa: RUF001
    cyrillic_c = "СУБД"

    assert normalizer.key(latin_c) == normalizer.key(cyrillic_c) == "субд"
    assert normalizer.key("Data-платформа") == "dataплатформа"  # noqa: RUF001


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("管理与监控", "管理监控"),
        ("容器、镜像", "容器镜像"),
        ("Хранение и резервное копирование", "хранениерезервноекопирование"),
    ],
)
def test_conjunctions_are_dropped(text: str, key: str) -> None:
    assert LabelNormalizer().key(text) == key


def test_attached_plus_and_hash_are_kept() -> None:
    normalizer = LabelNormalizer()

    assert normalizer.key("C++") == "c++"
    assert normalizer.key("C#") == "c#"
    assert normalizer.key("C") != normalizer.key("C++")


def test_a_label_of_punctuation_has_an_empty_key() -> None:
    assert LabelNormalizer().key(" - / & ") == ""


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Databases", Language.ENGLISH),
        ("Base de données", Language.ENGLISH),
        ("Базы данных", Language.RUSSIAN),
        ("Data-платформа", Language.RUSSIAN),
        ("数据库", Language.CHINESE),
        ("AI生态市场", Language.CHINESE),
    ],
)
def test_language_from_the_script(text: str, language: Language) -> None:
    assert LabelNormalizer().language(text) is language
