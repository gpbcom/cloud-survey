from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum


class RecordKind(StrEnum):
    """Enums representing a dataset of stored research records browsed in the Patents & Papers tab.

    Attributes:
        PATENTS (str): The patent publications found by the assignee searches.
        PAPERS (str): The research papers of the companies' institutions.
        RESEARCHERS (str): The profiles of the companies' researchers.
        INVENTORS (str): The inventor profiles derived from the patents.
        ASSIGNEES (str): The assignee profiles derived from the patents.
        WINDOWS (str): The patents search windows.
    """

    PATENTS = "patents"
    PAPERS = "papers"
    RESEARCHERS = "researchers"
    INVENTORS = "inventors"
    ASSIGNEES = "assignees"
    WINDOWS = "windows"


class RecordSort(StrEnum):
    """Enums representing a column the stored research records are sorted by.

    Attributes:
        COMPANY (str): The company.
        PUBLICATION (str): The publication number.
        TITLE (str): The title.
        NAME (str): The name (researcher, inventor, assignee).
        ASSIGNEE (str): The assignee.
        PRIORITY (str): The priority date.
        PUBLISHED (str): The publication date (or year).
        GRANTED (str): The grant date.
        CITATIONS (str): The citations received.
        VENUE (str): Where the paper appeared.
        WORKS (str): The works of a researcher.
        H_INDEX (str): The h-index of a researcher.
        PUBLICATIONS (str): The publications of an inventor or an assignee.
        FIRST (str): The first priority (or year).
        LAST (str): The last priority (or year).
        AFTER (str): The start of a search window.
        STATUS (str): The state of a search window.
        EXPECTED (str): The publications Google counts in a window.
        FETCHED (str): The publications read in a window.
        SEARCHED (str): When a window was searched.
    """

    COMPANY = "company"
    PUBLICATION = "publication"
    TITLE = "title"
    NAME = "name"
    ASSIGNEE = "assignee"
    PRIORITY = "priority"
    PUBLISHED = "published"
    GRANTED = "granted"
    CITATIONS = "citations"
    VENUE = "venue"
    WORKS = "works"
    H_INDEX = "h-index"
    PUBLICATIONS = "publications"
    FIRST = "first"
    LAST = "last"
    AFTER = "after"
    STATUS = "status"
    EXPECTED = "expected"
    FETCHED = "fetched"
    SEARCHED = "searched"
