from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class SubmissionsField(StrEnum):
    """Enums representing the fields of an SEC EDGAR `submissions` document (a filer's filings, by columns).

    Attributes:
        FILINGS (str): The filings of the main document: the recent ones, and the pages of the older ones.
        RECENT (str): The recent filings, as columns of the same length.
        FILES (str): The pages of the older filings (a filer with more than about a thousand filings).
        NAME (str): The name of the filer (main document), or the document name of a page of older filings.
        FILING_FROM (str): The first filing day of a page of older filings.
        ACCESSION (str): The accession numbers of the filings.
        FORM (str): The forms of the filings.
        FILING_DATE (str): The filing days.
    """

    FILINGS = "filings"
    RECENT = "recent"
    FILES = "files"
    NAME = "name"
    FILING_FROM = "filingFrom"
    ACCESSION = "accessionNumber"
    FORM = "form"
    FILING_DATE = "filingDate"


@unique
class ScheduleStep(StrEnum):
    """Enums representing what a request of the financial data schedules crawl reads (its `step` meta).

    Attributes:
        SUBMISSIONS (str): The filings of a filer (its main `submissions` document).
        SUBMISSIONS_PAGE (str): A page of the older filings of a filer.
        FILING (str): The full text of a filing (its documents, the schedules among them).
    """

    SUBMISSIONS = "submissions"
    SUBMISSIONS_PAGE = "submissions-page"
    FILING = "filing"


@unique
class ScheduleHeader(StrEnum):
    """Enums representing the header fields of a filing's full text and the meta tags of a data schedule.

    Attributes:
        FILED (str): The filing day of the full text, `YYYYMMDD`.
        FORM (str): The form of the full text.
        DOCUMENT_TYPE (str): The tag opening a document of the full text with its type, e.g. `EX-27`.
        SCHEDULE_TYPE (str): The prefix of the type of a data schedule document.
        ARTICLE (str): The article of Regulation S-X the schedule follows.
        MULTIPLIER (str): The multiplier of the schedule's amounts.
        CURRENCY (str): The currency of the schedule's amounts.
        PERIOD_TYPE (str): The length of the period: `YEAR`, `12-MOS`, `3-MOS`, `6-MOS`, `9-MOS`.
        PERIOD_START (str): The first day of the period.
        PERIOD_END (str): The last day of the period.
        COLUMNS (str): The tag of the column header line (`<S>` then a `<C>` per column).
        COLUMN (str): The tag marking a column in the header line.
    """

    FILED = "FILED AS OF DATE"
    FORM = "CONFORMED SUBMISSION TYPE"
    DOCUMENT_TYPE = "<TYPE>"
    SCHEDULE_TYPE = "EX-27"
    ARTICLE = "ARTICLE"
    MULTIPLIER = "MULTIPLIER"
    CURRENCY = "CURRENCY"
    PERIOD_TYPE = "PERIOD-TYPE"
    PERIOD_START = "PERIOD-START"
    PERIOD_END = "PERIOD-END"
    COLUMNS = "<S>"
    COLUMN = "<C>"
