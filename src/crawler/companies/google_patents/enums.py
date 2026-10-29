from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class PatentsStep(StrEnum):
    """Enums representing what a request of the Google Patents search reads.

    Attributes:
        COUNT (str): The number of publications of a window (the JSON search, 10 results asked).
        EXPORT (str): The publications of a window (the CSV export, up to about a thousand rows).
    """

    COUNT = "count"
    EXPORT = "export"


@unique
class PatentsSearchField(StrEnum):
    """Enums representing the fields of a Google Patents JSON search answer.

    Attributes:
        RESULTS (str): The answer.
        TOTAL (str): The number of publications the search counts.
    """

    RESULTS = "results"
    TOTAL = "total_num_results"


@unique
class PatentsExportColumn(StrEnum):
    """Enums representing the columns of a Google Patents CSV export (its second line names them).

    Attributes:
        ID (str): The publication, written with hyphens (`US-2023214654-A1`).
        TITLE (str): The title.
        ASSIGNEE (str): The assignee.
        INVENTORS (str): The inventors, comma-separated.
        PRIORITY (str): The priority date.
        FILING (str): The filing date.
        PUBLICATION (str): The publication date.
        GRANT (str): The grant date, blank for an application.
        LINK (str): The publication page (its path names the publication as the page does).
    """

    ID = "id"
    TITLE = "title"
    ASSIGNEE = "assignee"
    INVENTORS = "inventor/author"
    PRIORITY = "priority date"
    FILING = "filing/creation date"
    PUBLICATION = "publication date"
    GRANT = "grant date"
    LINK = "result link"


@unique
class PatentPageProperty(StrEnum):
    """Enums representing the microdata properties of a Google Patents publication page.

    Attributes:
        TITLE (str): The title.
        ABSTRACT (str): The abstract section.
        INVENTOR (str): An inventor.
        ASSIGNEE_ORIGINAL (str): An assignee the publication was filed by.
        ASSIGNEE_CURRENT (str): An assignee holding it now.
        PRIORITY_DATE (str): The priority date.
        FILING_DATE (str): The filing date.
        PUBLICATION_DATE (str): The publication date.
        FAMILY_ID (str): The DOCDB family.
        CLASSIFICATIONS (str): A CPC classification path.
        CODE (str): The code of a classification.
        LEAF (str): Marks the most specific code of a classification path.
        CLAIMS (str): The claims section.
        COUNT (str): The count of a section.
        PUBLICATION_NUMBER (str): The publication of a citation row.
        EXAMINER_CITED (str): The examiner mark of a citation row.
        EVENTS (str): An event of the legal timeline (the grant among them).
        DATE (str): The date of a citation row or an event.
        TYPE (str): The type of an event.
    """

    TITLE = "title"
    ABSTRACT = "abstract"
    INVENTOR = "inventor"
    ASSIGNEE_ORIGINAL = "assigneeOriginal"
    ASSIGNEE_CURRENT = "assigneeCurrent"
    PRIORITY_DATE = "priorityDate"
    FILING_DATE = "filingDate"
    PUBLICATION_DATE = "publicationDate"
    FAMILY_ID = "familyId"
    CLASSIFICATIONS = "classifications"
    CODE = "Code"
    LEAF = "Leaf"
    CLAIMS = "claims"
    COUNT = "count"
    PUBLICATION_NUMBER = "publicationNumber"
    EXAMINER_CITED = "examinerCited"
    EVENTS = "events"
    DATE = "date"
    TYPE = "type"


@unique
class CitationRow(StrEnum):
    """Enums representing the citation tables of a publication page, by the property of their rows.

    Attributes:
        CITES (str): The publications it cites (examiner and applicant).
        CITES_ORIGINAL (str): The publications it cites, as filed.
        CITED_BY (str): The publications citing it.
        CITED_BY_ORIGINAL (str): The publications citing it, as filed.
        FAMILY_CITES (str): The publications its family cites.
        FAMILY_CITED_BY (str): The publications citing its family.
    """

    CITES = "backwardReferences"
    CITES_ORIGINAL = "backwardReferencesOrig"
    CITED_BY = "forwardReferences"
    CITED_BY_ORIGINAL = "forwardReferencesOrig"
    FAMILY_CITES = "backwardReferencesFamily"
    FAMILY_CITED_BY = "forwardReferencesFamily"
