from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Set, Tuple

# First Party Imports.
from models.companies.identities.identity_candidate import IdentityCandidate
from models.curated.companies.company_identifier import CompanyIdentifier
from models.curated.enums import CuratedFile, IdentifierKind, IdentifierStatus, RecordOrigin
from storage.storage import Storage


class IdentityCollector:
    """Write the identifiers the resolvers found as proposed identifiers of the companies catalogue.

    Attributes:
        storage (Storage): The open storage.
        logger (Logger): The collector logger.

    Notes:
        - A candidate already stored for its company and kind, in any status (confirmed, proposed, rejected, changed
          by a person), is left as it is: a resolver never changes a stored identifier.
        - A new candidate is written as proposed (`candidate`, origin `resolver`), ranked after the identifiers of
          its kind, with what the source names it and why in its note. A verified candidate (unambiguous and
          checked, e.g. a SEC filer stating the company's listed ticker) is confirmed at once.
        - The candidates are written through the catalogue editor: the companies catalogue is checked before
          anything is written, and the next crawl reads the confirmed ones.
    """

    def __init__(self, storage: Storage, logger: Optional[Logger] = None) -> None:
        """Initialize the collector.

        Args:
            storage (Storage): The open storage.
            logger (Optional[Logger]): The collector logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage

    ############################
    # Publicly Exposed Methods #
    ############################

    async def write(self, candidates: Sequence[IdentityCandidate]) -> int:
        """Write the new candidates.

        Args:
            candidates (Sequence[IdentityCandidate]): The identifiers the resolvers found.

        Returns:
            int: The identifiers written.

        Raises:
            StorageReadError: If the companies catalogue cannot be read.
            CuratedCatalogError: If the catalogue would not be valid with them.
            StorageWriteError: If the database was never seeded, or the identifiers cannot be written.
        """
        if not candidates:
            return 0
        part = await self.storage.catalog_editor.part(CuratedFile.COMPANIES)
        known: Set[Tuple[str, IdentifierKind, str]] = {(row.company, row.kind, row.value) for row in part.identifiers}
        ranks: Dict[Tuple[str, IdentifierKind], int] = {}
        for row in part.identifiers:
            ranks[(row.company, row.kind)] = max(ranks.get((row.company, row.kind), -1), row.position)
        profiles = {profile.company for profile in part.profiles}
        added: List[CompanyIdentifier] = []
        now = datetime.now(UTC)
        for candidate in candidates:
            key = (candidate.company, candidate.identifier_kind, candidate.value)
            if key in known or candidate.company not in profiles:
                self.logger.debug(
                    "The %s %s of %s is known: left as it is.",
                    candidate.identifier_kind.value,
                    candidate.value,
                    candidate.company,
                )
                continue
            known.add(key)
            rank = ranks.get((candidate.company, candidate.identifier_kind), -1) + 1
            ranks[(candidate.company, candidate.identifier_kind)] = rank
            added.append(
                CompanyIdentifier(
                    company=candidate.company,
                    kind=candidate.identifier_kind,
                    value=candidate.value,
                    position=rank,
                    status=IdentifierStatus.CONFIRMED if candidate.verified else IdentifierStatus.CANDIDATE,
                    origin=RecordOrigin.RESOLVER,
                    evidence_url=candidate.evidence_url,
                    note=f"{candidate.label}: {candidate.reason}",
                    checked_at=now,
                )
            )
        if not added:
            self.logger.info("No new identifier among %d candidates.", len(candidates))
            return 0
        written = await self.storage.catalog_editor.save(
            CuratedFile.COMPANIES, part.model_copy(update={"identifiers": [*part.identifiers, *added]})
        )
        confirmed = sum(1 for row in added if row.status is IdentifierStatus.CONFIRMED)
        if confirmed:
            self.logger.warning("%d verified identifiers confirmed at once by the resolvers.", confirmed)
        self.logger.info(
            "%d identifiers proposed (%d confirmed) of %d candidates.", written, confirmed, len(candidates)
        )
        return written
