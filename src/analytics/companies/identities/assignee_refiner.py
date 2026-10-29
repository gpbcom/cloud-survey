from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Set
from urllib.parse import quote

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from curated.company_names import CompanyNames
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.identities.identity_candidate import IdentityCandidate
from models.companies.stored.patents.assignee_profile import AssigneeProfile
from models.curated.enums import IdentifierKind
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage


class AssigneeRefiner:
    """Find the homonyms among the assignees of the stored patents of the companies, without network.

    Attributes:
        MIN_PUBLICATIONS (ClassVar[int]): The publications an assignee needs to be considered.
        LIMIT (ClassVar[int]): The assignee profiles read per company, the most prolific first.
        EVIDENCE_URL (ClassVar[str]): The Google Patents search of an assignee, formatted with its quoted name.
        names (CompanyNames): Compares the names.
        logger (Logger): The refiner logger.

    Notes:
        - Google Patents searches an assignee loosely: the search of `Amazon` also returns `Amazonas Energia`. An
          assignee of a company's stored patents is the company's when every word of one of its assignee searches
          is a word of its name (`IBM United Kingdom Ltd` for `IBM`), else it is proposed as a homonym to leave out
          (an exclusion pattern matching its name exactly), which a person accepts or rejects.
        - The assignees already left out by a pattern of the company are not proposed again. The profiles are
          those of the last rebuild of the patent profiles.
    """

    MIN_PUBLICATIONS: ClassVar[int] = 25
    LIMIT: ClassVar[int] = 2000
    EVIDENCE_URL: ClassVar[str] = "https://patents.google.com/?assignee={name}"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the refiner.

        Args:
            logger (Optional[Logger]): The refiner logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.names = CompanyNames(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _homonyms(
        self, searches: Sequence[str], excluded: Sequence[str], profiles: Sequence[AssigneeProfile]
    ) -> List[AssigneeProfile]:
        """Find the assignees none of a company's searches names.

        Args:
            searches (Sequence[str]): The company's assignee searches.
            excluded (Sequence[str]): The company's exclusion patterns.
            profiles (Sequence[AssigneeProfile]): The assignees of its stored patents.

        Returns:
            List[AssigneeProfile]: The assignees of enough publications named by no search nor left out already.
        """
        words = [set(self.names.key(search).split()) for search in searches]
        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in excluded]
        homonyms: List[AssigneeProfile] = []
        for profile in profiles:
            if profile.publications < self.MIN_PUBLICATIONS or any(
                pattern.search(profile.name) for pattern in patterns
            ):
                continue
            named: Set[str] = set(self.names.key(profile.name).split())
            if not any(search and search <= named for search in words):
                homonyms.append(profile)
        return homonyms

    ############################
    # Publicly Exposed Methods #
    ############################

    async def candidates(
        self, storage: Storage, companies: CompaniesCatalog, scope: Sequence[str]
    ) -> List[IdentityCandidate]:
        """Propose the homonyms among the assignees of the companies' stored patents.

        Args:
            storage (Storage): The open storage.
            companies (CompaniesCatalog): The companies and their assignee searches.
            scope (Sequence[str]): The companies refined, every one when empty.

        Returns:
            List[IdentityCandidate]: An exclusion pattern per homonym found.

        Raises:
            StorageReadError: If the assignee profiles cannot be read.
        """
        candidates: List[IdentityCandidate] = []
        for entry in companies.entries(scope):
            if entry.patents is None:
                continue
            page = await storage.patent_profiles.assignee_page(RecordQuery(companies=[entry.key], limit=self.LIMIT))
            for profile in self._homonyms(entry.patents.assignees, entry.patents.exclude, page.items):
                try:
                    candidates.append(
                        IdentityCandidate(
                            company=entry.key,
                            identifier_kind=IdentifierKind.PATENT_EXCLUDE,
                            value=f"^{re.escape(profile.name)}$",
                            label=profile.name,
                            evidence_url=self.EVIDENCE_URL.format(name=quote(profile.name)),
                            reason=f"no assignee search of the company names it ({profile.publications} publications)",
                        )
                    )
                except ValidationError as e:
                    self.logger.warning("Invalid homonym %r left out: %s", profile.name, e.errors()[0]["msg"])
        if candidates:
            self.logger.warning("%d possible homonyms among the stored assignees.", len(candidates))
        self.logger.info(
            "Assignees refined for %d companies: %d homonyms proposed.", len(companies.entries(scope)), len(candidates)
        )
        return candidates
