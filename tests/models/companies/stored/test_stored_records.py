from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from models.companies.enums import PatentWindowStatus
from models.companies.stored.papers.stored_paper import StoredPaper
from models.companies.stored.papers.stored_researcher import StoredResearcher
from models.companies.stored.patents.inventor_profile import InventorProfile
from models.companies.stored.patents.stored_patent import StoredPatent
from models.companies.stored.patents.stored_window import StoredWindow


class TestStoredPatent:
    def test_the_aggregated_companies_are_split_sorted_each_once(self) -> None:
        patent = StoredPatent(publication_number="US11000000B2", companies="nvidia,amd,nvidia")

        assert patent.companies == ["amd", "nvidia"]
        assert StoredPatent(publication_number="US11000000B2", companies=None).companies == []

    def test_a_publication_is_required(self) -> None:
        with pytest.raises(ValidationError):
            StoredPatent(publication_number="")


class TestStoredPaper:
    def test_the_link_is_the_doi_page_else_openalex(self) -> None:
        assert StoredPaper(openalex_id="W2000000001", doi="10.1/x").link() == "https://doi.org/10.1/x"
        assert StoredPaper(openalex_id="W2000000001", doi="https://doi.org/10.1/x").link() == "https://doi.org/10.1/x"
        assert StoredPaper(openalex_id="W2000000001").link() == "https://openalex.org/W2000000001"

    def test_the_citations_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            StoredPaper(openalex_id="W2000000001", cited_by_count=-1)


class TestProfiles:
    def test_an_inventor_keeps_the_order_of_their_companies(self) -> None:
        profile = InventorProfile(name_key="ada lovelace", name="Ada Lovelace", companies="ibm, amd")

        assert profile.companies == ["ibm", "amd"]

    def test_a_researcher_links_to_openalex(self) -> None:
        person = StoredResearcher(author_id="A5001", company="ibm", name="Ada")

        assert person.link() == "https://openalex.org/A5001"

    def test_a_window_needs_a_known_status(self) -> None:
        window = StoredWindow(
            company="ibm", query="IBM", after=date(2019, 1, 1), before=date(2019, 2, 1), status="pending"
        )

        assert window.status is PatentWindowStatus.PENDING
        with pytest.raises(ValidationError):
            StoredWindow(company="ibm", query="IBM", after=date(2019, 1, 1), before=date(2019, 2, 1), status="lost")
