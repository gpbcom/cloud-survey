from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.companies.checks.document_numbers import DocumentNumbers

VALID: Dict[str, JsonValue] = {
    "company": "ibm",
    "fiscal_years": [1981, 1980, 1980],
    "source_url": "https://www.sec.gov/Archives/x.txt",
    "numbers": [3.0, 1, 3.0],
}


def test_the_years_and_numbers_are_sorted_without_duplicates() -> None:
    document = DocumentNumbers.model_validate(VALID)

    assert document.fiscal_years == [1980, 1981]
    assert document.numbers == [1.0, 3.0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company", "IBM"),
        ("fiscal_years", []),
        ("fiscal_years", [1800]),
        ("fiscal_years", "1980"),
        ("source_url", "ftp://x"),
        ("numbers", [-1.0]),
        ("numbers", [True]),
    ],
)
def test_an_invalid_document_is_refused(field: str, value: JsonValue) -> None:
    with pytest.raises(ValidationError):
        DocumentNumbers.model_validate({**VALID, field: value})
