from __future__ import annotations

import pytest

from curated.company_names import CompanyNames


@pytest.mark.parametrize(
    ("name", "other"),
    [
        ("International Business Machines Corp", "INTERNATIONAL BUSINESS MACHINES CORP /NY/"),
        ("IBM", "IBM (United States)"),
        ("Alibaba", "Alibaba Group Holding Ltd"),
        ("AT&T", "AT and T Inc."),
    ],
)
def test_the_names_of_a_company_match(name: str, other: str) -> None:
    assert CompanyNames().match(name, other)


@pytest.mark.parametrize(
    ("name", "other"), [("Nvidia", "Nvidiana Inc"), ("Amazon", "Amazonas Energia"), ("Inc", "Corp"), ("IBM", "IBMS")]
)
def test_a_homonym_or_a_bare_legal_form_does_not_match(name: str, other: str) -> None:
    assert not CompanyNames().match(name, other)


def test_the_key_keeps_the_words_only() -> None:
    assert CompanyNames().key("The Walt Disney Company (DE)") == "walt disney"
