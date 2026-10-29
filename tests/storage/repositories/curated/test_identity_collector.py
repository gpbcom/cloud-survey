from __future__ import annotations

import pytest

from analytics.companies.identities.identity_collector import IdentityCollector
from models.companies.identities.identity_candidate import IdentityCandidate
from models.curated.enums import IdentifierKind, IdentifierStatus, RecordOrigin
from storage.storage import Storage

pytestmark = pytest.mark.db


def candidate(value: str, kind: IdentifierKind, verified: bool = False) -> IdentityCandidate:
    return IdentityCandidate(
        company="ibm",
        identifier_kind=kind,
        value=value,
        label="International Business Machines",
        evidence_url="https://example.org/evidence",
        reason="a test",
        verified=verified,
    )


async def test_new_candidates_are_proposed_and_verified_ones_confirmed(storage: Storage) -> None:
    await storage.curated_seeder.seed()
    collector = IdentityCollector(storage)

    written = await collector.write(
        [
            candidate("0000099999", IdentifierKind.SEC_CIK, verified=True),
            candidate("I888000001", IdentifierKind.OPENALEX_INSTITUTION),
            candidate("0000051143", IdentifierKind.SEC_CIK, verified=True),
        ]
    )
    companies = await storage.catalogs.companies()
    ibm = next(entry for entry in companies.companies if entry.key == "ibm")
    proposed = await storage.company_identifiers.read("ibm", IdentifierKind.OPENALEX_INSTITUTION, "I888000001")

    assert written == 2
    assert "0000099999" in ibm.sec_ciks
    assert "I888000001" not in ibm.openalex.institutions
    assert proposed is not None
    assert proposed.status is IdentifierStatus.CANDIDATE
    assert proposed.origin is RecordOrigin.RESOLVER
    assert proposed.note == "International Business Machines: a test"
    assert await collector.write([candidate("I888000001", IdentifierKind.OPENALEX_INSTITUTION)]) == 0


async def test_a_rejected_identifier_is_never_proposed_again(storage: Storage) -> None:
    await storage.curated_seeder.seed()
    collector = IdentityCollector(storage)
    await collector.write([candidate("I888000001", IdentifierKind.OPENALEX_INSTITUTION)])
    proposed = await storage.company_identifiers.read("ibm", IdentifierKind.OPENALEX_INSTITUTION, "I888000001")
    assert proposed is not None
    await storage.company_identifiers.update(
        proposed.model_copy(update={"status": IdentifierStatus.REJECTED, "edited": True})
    )

    assert await collector.write([candidate("I888000001", IdentifierKind.OPENALEX_INSTITUTION)]) == 0
    kept = await storage.company_identifiers.read("ibm", IdentifierKind.OPENALEX_INSTITUTION, "I888000001")
    assert kept is not None
    assert kept.status is IdentifierStatus.REJECTED
