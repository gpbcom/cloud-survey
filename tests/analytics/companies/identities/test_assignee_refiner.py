from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from analytics.companies.identities.assignee_refiner import AssigneeRefiner
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.stored.patents.assignee_profile import AssigneeProfile
from models.curated.enums import IdentifierKind
from models.storage.records.record_page import RecordPage


def storage_with(*profiles: AssigneeProfile) -> MagicMock:
    storage = MagicMock()
    page = RecordPage[AssigneeProfile](items=list(profiles), offset=0, limit=2000, total=len(profiles))
    storage.patent_profiles.assignee_page = AsyncMock(return_value=page)
    return storage


async def test_the_assignees_no_search_names_are_proposed_as_homonyms(companies_catalog: CompaniesCatalog) -> None:
    entry = companies_catalog.entry("ibm")
    assert entry is not None
    assert entry.patents is not None
    storage = storage_with(
        AssigneeProfile(company="ibm", name=entry.patents.assignees[0].upper(), publications=90_000),
        AssigneeProfile(company="ibm", name="Ibmetrix Labs", publications=40),
        AssigneeProfile(company="ibm", name="Small Homonym Co", publications=3),
    )

    candidates = await AssigneeRefiner().candidates(storage, companies_catalog, ["ibm"])

    assert [candidate.label for candidate in candidates] == ["Ibmetrix Labs"]
    (candidate,) = candidates
    assert candidate.identifier_kind is IdentifierKind.PATENT_EXCLUDE
    assert candidate.value == "^Ibmetrix\\ Labs$"
    assert not candidate.verified


async def test_a_homonym_left_out_already_is_not_proposed_again(companies_catalog: CompaniesCatalog) -> None:
    entry = companies_catalog.entry("ibm")
    assert entry is not None
    assert entry.patents is not None
    excluded = entry.patents.model_copy(update={"exclude": ["^Ibmetrix"]})
    entries = [
        item.model_copy(update={"patents": excluded}) if item.key == "ibm" else item
        for item in companies_catalog.companies
    ]
    catalog = companies_catalog.model_copy(update={"companies": entries})

    candidates = await AssigneeRefiner().candidates(
        storage_with(AssigneeProfile(company="ibm", name="Ibmetrix Labs", publications=40)), catalog, ["ibm"]
    )

    assert candidates == []
