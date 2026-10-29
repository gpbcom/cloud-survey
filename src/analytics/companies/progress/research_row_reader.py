from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from pydantic import JsonValue, ValidationError

# First Party Imports.
from models.companies.enums import CompanyFactKind, CompanyFeed
from models.companies.papers.paper_record import PaperRecord
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.papers.researcher_record import ResearcherRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.patents.patent_record import PatentRecord
from models.companies.patents.patent_window import PatentWindow
from models.companies.progress.research_row import ResearchRow


class ResearchRowReader:
    """Turn the facts of a patents or papers crawl into the rows the Patents & Papers tab streams.

    Attributes:
        KIND_KEY (ClassVar[str]): The item key naming the kind of fact.
        logger (Logger): The reader logger.

    Notes:
        - The statement facts are left out: the tab follows the patents and the papers only.
        - A fact that does not validate is left out (it was not written either).
    """

    KIND_KEY: ClassVar[str] = "kind"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            logger (Optional[Logger]): The reader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _row(self, feed: CompanyFeed, kind: CompanyFactKind, raw: Dict[str, JsonValue]) -> Optional[ResearchRow]:
        """Turn one fact into a row.

        Args:
            feed (CompanyFeed): The source.
            kind (CompanyFactKind): What the fact is.
            raw (Dict[str, JsonValue]): The fact, without its kind key.

        Returns:
            Optional[ResearchRow]: The row, `None` for a statement fact.

        Raises:
            ValidationError: If the fact does not validate.
        """
        match kind:
            case CompanyFactKind.PATENT:
                patent = PatentRecord.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    company=patent.company,
                    identifier=patent.publication_number,
                    title=patent.title or "",
                    day=patent.priority_date or patent.publication_date,
                    detail=patent.assignee or "",
                    url=patent.source_url,
                )
            case CompanyFactKind.PATENT_DETAIL:
                detail = PatentDetail.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    identifier=detail.publication_number,
                    title=detail.title or "",
                    day=detail.priority_date or detail.publication_date,
                    detail=f"{len(detail.citations)} citations, {len(detail.cpc)} classes",
                    url=detail.source_url,
                )
            case CompanyFactKind.PATENT_WINDOW:
                window = PatentWindow.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    company=window.company,
                    identifier=f"{window.after.isoformat()} to {window.before.isoformat()}",
                    title=window.query,
                    day=window.after,
                    detail=f"{window.status.value}: {window.fetched} of {window.expected} read",
                )
            case CompanyFactKind.PAPER:
                paper = PaperRecord.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    company=paper.company,
                    identifier=paper.doi or paper.openalex_id,
                    title=paper.title or "",
                    day=paper.publication_date,
                    detail=f"{paper.cited_by_count} citations" + (f", {paper.venue}" if paper.venue else ""),
                    url=paper.source_url,
                )
            case CompanyFactKind.RESEARCHER:
                person = ResearcherRecord.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    company=person.company,
                    identifier=person.author_id,
                    title=person.name,
                    detail=f"{person.works_count} works, h-index {'-' if person.h_index is None else person.h_index}",
                    url=person.source_url,
                )
            case CompanyFactKind.PAPER_COUNT:
                count = PaperYearCount.model_validate(raw)
                return ResearchRow(
                    feed=feed,
                    kind=kind,
                    company=count.company,
                    identifier=str(count.year),
                    title=f"{count.papers} papers",
                    url=count.source_url,
                )
            case _:
                return None

    ############################
    # Publicly Exposed Methods #
    ############################

    def read(self, feed: CompanyFeed, items: Sequence[Dict[str, JsonValue]]) -> List[ResearchRow]:
        """Turn a batch of facts into rows.

        Args:
            feed (CompanyFeed): The source of the batch.
            items (Sequence[Dict[str, JsonValue]]): The facts, each naming its kind.

        Returns:
            List[ResearchRow]: The rows of the patents and papers facts, in their order.
        """
        rows: List[ResearchRow] = []
        for item in items:
            raw_kind = item.get(self.KIND_KEY)
            if not isinstance(raw_kind, str) or raw_kind not in {kind.value for kind in CompanyFactKind}:
                self.logger.warning("A %s fact without a known kind is not shown (%r).", feed.value, raw_kind)
                continue
            fact = {key: value for key, value in item.items() if key != self.KIND_KEY}
            try:
                row = self._row(feed, CompanyFactKind(raw_kind), fact)
            except ValidationError as e:
                self.logger.debug("A %s fact is not shown: %d validation errors.", raw_kind, e.error_count())
                continue
            if row is not None:
                rows.append(row)
        self.logger.debug("%d of %d %s facts turned into rows.", len(rows), len(items), feed.value)
        return rows
