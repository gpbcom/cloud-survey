from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import BaseModel

# First Party Imports.
from gui.paging.records.record_layout import RecordLayout
from models.companies.stored.papers.stored_paper import StoredPaper
from models.companies.stored.papers.stored_researcher import StoredResearcher
from models.companies.stored.patents.assignee_profile import AssigneeProfile
from models.companies.stored.patents.inventor_profile import InventorProfile
from models.companies.stored.patents.stored_patent import StoredPatent
from models.companies.stored.patents.stored_window import StoredWindow
from models.storage.records.enums import RecordKind, RecordSort
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage


class RecordLayouts:
    """The columns of each dataset of the Stored data of the Patents & Papers tab, and how its records are read.

    Attributes:
        PATENT_PAGE (ClassVar[str]): The Google Patents page of a publication.
        PATENT_SEARCH (ClassVar[str]): The Google Patents search page.
        HEADERS (ClassVar[Dict[RecordKind, List[Tuple[str, str]]]]): The title and the tooltip of each column.
        SORTS (ClassVar[Dict[RecordKind, Dict[int, RecordSort]]]): The order of each sortable column.
        DEFAULTS (ClassVar[Dict[RecordKind, int]]): The column sorted by at first (descending).
        NUMERIC (ClassVar[Dict[RecordKind, List[int]]]): The columns aligned right.
        WIDE (ClassVar[Dict[RecordKind, List[int]]]): The columns of long texts (titles, names), shown wider.
        logger (Logger): The layouts logger.

    Notes:
        The cells and the links are written by one method for every dataset, matching the record's model: a
        record of another model has empty cells and no link.
    """

    PATENT_PAGE: ClassVar[str] = "https://patents.google.com/patent/{number}/en"
    PATENT_SEARCH: ClassVar[str] = "https://patents.google.com/?"
    HEADERS: ClassVar[Dict[RecordKind, List[Tuple[str, str]]]] = {
        RecordKind.PATENTS: [
            ("Publication", "The publication number (office, number, kind code)"),
            ("Title", "The title of the publication"),
            ("Assignee", "The first assignee named by the search"),
            ("Priority", "The date of the first filing of the invention"),
            ("Published", "The date the publication was published"),
            ("Granted", "The date the patent was granted (empty for an application)"),
            ("Companies", "The companies whose assignee search found it"),
            ("Page", "Whether its page was read (citations, family, classes, inventors)"),
        ],
        RecordKind.PAPERS: [
            ("Title", "The title of the paper"),
            ("Published", "The day the paper was published"),
            ("Venue", "The journal, conference or repository it appeared in"),
            ("Type", "The kind of work (article, preprint, review…)"),
            ("Citations", "The citations OpenAlex counts for it"),
            ("FWCI", "The field-weighted citation impact: 1 is the world average of its field and year"),
            ("Open access", "Whether it can be read freely"),
            ("Companies", "The companies whose institutions it is affiliated with"),
            ("DOI", "Its digital object identifier"),
        ],
        RecordKind.RESEARCHERS: [
            ("Name", "The researcher's name"),
            ("Company", "The company they wrote for"),
            ("Institution", "Where OpenAlex saw them last"),
            ("Works", "The works OpenAlex counts for them"),
            ("Citations", "The citations their works received"),
            ("h-index", "The largest h such that h of their works are cited at least h times"),
            ("ORCID", "Their ORCID identifier"),
        ],
        RecordKind.INVENTORS: [
            ("Name", "The inventor's name as printed (two spellings make two profiles)"),
            ("Publications", "The stored publications naming them"),
            ("Families", "The patent families of those publications"),
            ("First priority", "Their earliest priority date"),
            ("Last priority", "Their latest priority date"),
            ("Co-inventors", "The other inventors named with them"),
            ("Citations", "The citations their publications received (pages read only)"),
            ("Companies", "The companies whose publications name them"),
            ("Main classes", "Their most frequent main CPC classes"),
        ],
        RecordKind.ASSIGNEES: [
            ("Company", "The company searched"),
            ("Assignee", "The assignee name printed on the publications"),
            ("Publications", "The stored publications of that name"),
            ("First year", "The earliest priority year"),
            ("Last year", "The latest priority year"),
            ("Offices", "The patent offices it published in"),
            ("Main classes", "Its most frequent main CPC classes"),
            ("Main inventors", "Its most frequent inventors"),
        ],
        RecordKind.WINDOWS: [
            ("Company", "The company searched"),
            ("Assignee searched", "The assignee name the search asked for"),
            ("From", "The first priority date of the window"),
            ("To", "The day after its last priority date"),
            ("Office", "The patent office searched (empty for every office)"),
            (
                "Status",
                "complete: every publication read; split: searched as halves; incomplete: read in part; "
                "pending: counted, not read yet",
            ),
            ("Read", "The publications read"),
            ("Expected", "The publications Google Patents counts in the window"),
            ("Searched", "When the window was searched last"),
        ],
    }
    SORTS: ClassVar[Dict[RecordKind, Dict[int, RecordSort]]] = {
        RecordKind.PATENTS: {
            0: RecordSort.PUBLICATION,
            1: RecordSort.TITLE,
            2: RecordSort.ASSIGNEE,
            3: RecordSort.PRIORITY,
            4: RecordSort.PUBLISHED,
            5: RecordSort.GRANTED,
        },
        RecordKind.PAPERS: {0: RecordSort.TITLE, 1: RecordSort.PUBLISHED, 2: RecordSort.VENUE, 4: RecordSort.CITATIONS},
        RecordKind.RESEARCHERS: {
            0: RecordSort.NAME,
            1: RecordSort.COMPANY,
            3: RecordSort.WORKS,
            4: RecordSort.CITATIONS,
            5: RecordSort.H_INDEX,
        },
        RecordKind.INVENTORS: {
            0: RecordSort.NAME,
            1: RecordSort.PUBLICATIONS,
            3: RecordSort.FIRST,
            4: RecordSort.LAST,
            6: RecordSort.CITATIONS,
        },
        RecordKind.ASSIGNEES: {
            0: RecordSort.COMPANY,
            1: RecordSort.NAME,
            2: RecordSort.PUBLICATIONS,
            3: RecordSort.FIRST,
            4: RecordSort.LAST,
        },
        RecordKind.WINDOWS: {
            0: RecordSort.COMPANY,
            2: RecordSort.AFTER,
            5: RecordSort.STATUS,
            6: RecordSort.FETCHED,
            7: RecordSort.EXPECTED,
            8: RecordSort.SEARCHED,
        },
    }
    DEFAULTS: ClassVar[Dict[RecordKind, int]] = {
        RecordKind.PATENTS: 3,
        RecordKind.PAPERS: 1,
        RecordKind.RESEARCHERS: 4,
        RecordKind.INVENTORS: 1,
        RecordKind.ASSIGNEES: 2,
        RecordKind.WINDOWS: 2,
    }
    NUMERIC: ClassVar[Dict[RecordKind, List[int]]] = {
        RecordKind.PATENTS: [],
        RecordKind.PAPERS: [4, 5],
        RecordKind.RESEARCHERS: [3, 4, 5],
        RecordKind.INVENTORS: [1, 2, 5, 6],
        RecordKind.ASSIGNEES: [2, 3, 4],
        RecordKind.WINDOWS: [6, 7],
    }
    WIDE: ClassVar[Dict[RecordKind, List[int]]] = {
        RecordKind.PATENTS: [1, 2],
        RecordKind.PAPERS: [0, 2],
        RecordKind.RESEARCHERS: [0, 2],
        RecordKind.INVENTORS: [0],
        RecordKind.ASSIGNEES: [1],
        RecordKind.WINDOWS: [1],
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the layouts.

        Args:
            logger (Optional[Logger]): The layouts logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, value: Optional[Union[str, int, float, date, datetime]]) -> str:
        """Write a value as a cell.

        Args:
            value (Optional[Union[str, int, float, date, datetime]]): The value.

        Returns:
            str: Its text, empty for no value.
        """
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    async def _read(
        self, kind: RecordKind, storage: Storage, query: RecordQuery
    ) -> Tuple[List[BaseModel], Optional[int]]:
        """Read a page of a dataset (storage thread).

        Args:
            kind (RecordKind): The dataset.
            storage (Storage): The open storage.
            query (RecordQuery): The companies, the text, the order and the bounds of the page.

        Returns:
            Tuple[List[BaseModel], Optional[int]]: The records, then their count when it was asked.
        """
        records: List[BaseModel] = []
        match kind:
            case RecordKind.PATENTS:
                patents = await storage.patents.list(query)
                records.extend(patents.items)
                total = patents.total
            case RecordKind.PAPERS:
                papers = await storage.papers.list(query)
                records.extend(papers.items)
                total = papers.total
            case RecordKind.RESEARCHERS:
                researchers = await storage.papers.researcher_page(query)
                records.extend(researchers.items)
                total = researchers.total
            case RecordKind.INVENTORS:
                inventors = await storage.patent_profiles.list(query)
                records.extend(inventors.items)
                total = inventors.total
            case RecordKind.ASSIGNEES:
                assignees = await storage.patent_profiles.assignee_page(query)
                records.extend(assignees.items)
                total = assignees.total
            case RecordKind.WINDOWS:
                windows = await storage.patents.window_page(query)
                records.extend(windows.items)
                total = windows.total
        return records, total

    ############################
    # Publicly Exposed Methods #
    ############################

    def cells(self, record: BaseModel) -> List[str]:
        """Write the text of each column of a record.

        Args:
            record (BaseModel): The record.

        Returns:
            List[str]: The cells, in the columns' order of its dataset.
        """
        text = self._text
        match record:
            case StoredPatent():
                return [
                    record.publication_number,
                    text(record.title),
                    text(record.assignee),
                    text(record.priority_date),
                    text(record.publication_date),
                    text(record.grant_date),
                    ", ".join(record.companies),
                    "read" if record.page_read else "",
                ]
            case StoredPaper():
                return [
                    text(record.title),
                    text(record.publication_date or record.publication_year),
                    text(record.venue),
                    text(record.type),
                    text(record.cited_by_count),
                    text(record.fwci),
                    "yes" if record.is_oa else "",
                    ", ".join(record.companies),
                    text(record.doi),
                ]
            case StoredResearcher():
                return [
                    record.name,
                    record.company,
                    text(record.institution),
                    text(record.works_count),
                    text(record.cited_by_count),
                    text(record.h_index),
                    text(record.orcid),
                ]
            case InventorProfile():
                return [
                    record.name,
                    text(record.publications),
                    text(record.families),
                    text(record.first_priority),
                    text(record.last_priority),
                    text(record.co_inventors),
                    text(record.citations_received),
                    ", ".join(record.companies),
                    text(record.top_cpc),
                ]
            case AssigneeProfile():
                return [
                    record.company,
                    record.name,
                    text(record.publications),
                    text(record.first_year),
                    text(record.last_year),
                    record.countries,
                    text(record.top_cpc),
                    text(record.top_inventors),
                ]
            case StoredWindow():
                return [
                    record.company,
                    record.query,
                    text(record.after),
                    text(record.before),
                    text(record.country),
                    record.status.value,
                    text(record.fetched),
                    text(record.expected),
                    text(record.searched_at),
                ]
            case _:
                return []

    def link(self, record: BaseModel) -> Optional[str]:
        """Get the page a record is opened at.

        Args:
            record (BaseModel): The record.

        Returns:
            Optional[str]: Its Google Patents, DOI or OpenAlex page, `None` for another model.
        """
        match record:
            case StoredPatent():
                return self.PATENT_PAGE.format(number=record.publication_number)
            case StoredPaper() | StoredResearcher():
                return record.link()
            case InventorProfile():
                return self.PATENT_SEARCH + urlencode({"inventor": record.name})
            case AssigneeProfile():
                return self.PATENT_SEARCH + urlencode({"assignee": record.name})
            case StoredWindow():
                bounds = {
                    "assignee": record.query,
                    "after": f"priority:{record.after.strftime('%Y%m%d')}",
                    "before": f"priority:{record.before.strftime('%Y%m%d')}",
                }
                if record.country:
                    bounds["country"] = record.country
                return self.PATENT_SEARCH + urlencode(bounds)
            case _:
                return None

    def layout(self, kind: RecordKind) -> RecordLayout:
        """Get the layout of a dataset.

        Args:
            kind (RecordKind): The dataset.

        Returns:
            RecordLayout: Its columns, orders and reader.
        """
        self.logger.debug("Layout of the stored %s built.", kind.value)
        return RecordLayout(
            headers=self.HEADERS[kind],
            sorts=self.SORTS[kind],
            default=self.DEFAULTS[kind],
            numeric=set(self.NUMERIC[kind]),
            wide=set(self.WIDE[kind]),
            reader=lambda storage, query: self._read(kind, storage, query),
            cells=self.cells,
            link=self.link,
            logger=self.logger,
        )
