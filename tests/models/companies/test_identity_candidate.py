from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.companies.identities.identity_candidate import IdentityCandidate
from models.curated.enums import IdentifierKind

VALID: Dict[str, JsonValue] = {
    "company": "nvidia",
    "identifier_kind": "sec-cik",
    "value": "0001045810",
    "label": "NVIDIA  CORP",
    "evidence_url": "https://www.sec.gov/edgar/browse/?CIK=1045810",
    "reason": "its ticker NVDA is a listing of the company",
}


def test_a_candidate_is_read() -> None:
    candidate = IdentityCandidate.model_validate(VALID)

    assert candidate.identifier_kind is IdentifierKind.SEC_CIK
    assert candidate.label == "NVIDIA CORP"
    assert not candidate.verified


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company", "NVIDIA"),
        ("identifier_kind", "ticker"),
        ("value", ""),
        ("label", " "),
        ("evidence_url", "http://www.sec.gov/"),
        ("reason", 3),
    ],
)
def test_an_invalid_candidate_is_refused(field: str, value: JsonValue) -> None:
    with pytest.raises(ValidationError):
        IdentityCandidate.model_validate({**VALID, field: value})
