from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Optional, Sequence

# First Party Imports.
from analytics.companies.checks.figure_checker import FigureChecker
from models.companies.checks.document_numbers import DocumentNumbers
from models.companies.figures.reported_figures import ReportedFigures
from models.curated.enums import FigureCheck
from storage.storage import Storage


class FigureCheckCollector:
    """Record whether the documents the researched fiscal years cite state their figures.

    Attributes:
        storage (Storage): The open storage.
        checker (FigureChecker): Compares the figures with the numbers of a document.
        figures (Optional[ReportedFigures]): The researched figures, read at the first document.
        logger (Logger): The collector logger.

    Notes:
        - Only the check of a fiscal year is written (`check_status`, `check_note`, `checked_at`): its figures, its
          note, its origin and whether a person changed it are kept. A curated figure is never overwritten.
        - A fiscal year whose document changed since it was read (another source cited now) is left unchecked.
    """

    def __init__(self, storage: Storage, logger: Optional[Logger] = None) -> None:
        """Initialize the collector.

        Args:
            storage (Storage): The open storage.
            logger (Optional[Logger]): The collector logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage
        self.checker = FigureChecker(self.logger)
        self.figures: Optional[ReportedFigures] = None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def write(self, documents: Sequence[DocumentNumbers]) -> int:
        """Check and record the fiscal years citing some documents.

        Args:
            documents (Sequence[DocumentNumbers]): The numbers each document states.

        Returns:
            int: The fiscal years whose check was written.

        Raises:
            StorageReadError: If the researched figures cannot be read.
            StorageWriteError: If a check cannot be written.
        """
        if self.figures is None:
            self.figures = await self.storage.catalogs.figures()
        now, written = datetime.now(UTC), 0
        for document in documents:
            entry = self.figures.of(document.company)
            if entry is None:
                self.logger.warning("No researched figures for %s: its document is left out.", document.company)
                continue
            for fiscal_year in document.fiscal_years:
                year = next((item for item in entry.years if item.fiscal_year == fiscal_year), None)
                stored = await self.storage.reported_years.read(document.company, fiscal_year)
                if year is None or stored is None or year.source != document.source_url:
                    self.logger.warning(
                        "%s %d no longer cites %s: left unchecked.", document.company, fiscal_year, document.source_url
                    )
                    continue
                status, note = self.checker.check(year, entry.scale, document.numbers)
                checked = stored.model_copy(update={"check_status": status, "check_note": note, "checked_at": now})
                if await self.storage.reported_years.update(checked):
                    written += 1
                if status is FigureCheck.MISMATCH:
                    self.logger.warning("%s %d: %s (%s).", document.company, fiscal_year, note, document.source_url)
        self.logger.info("%d researched fiscal years checked against %d documents.", written, len(documents))
        return written
