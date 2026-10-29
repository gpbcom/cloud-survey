from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class OpenAlexStep(StrEnum):
    """Enums representing what a request to OpenAlex reads.

    Attributes:
        COUNT (str): The papers of a company per publication year (`group_by`).
        WORKS (str): A page of the company's papers.
        AUTHORS (str): The profiles of a batch of the company's researchers.
    """

    COUNT = "count"
    WORKS = "works"
    AUTHORS = "authors"


@unique
class OpenAlexField(StrEnum):
    """Enums representing the fields of an OpenAlex answer.

    Attributes:
        META (str): The answer's metadata.
        NEXT_CURSOR (str): The cursor of the next page, `null` on the last one.
        COUNT (str): The number of results.
        GROUP_BY (str): The groups of a `group_by` answer.
        KEY (str): The key of a group.
        RESULTS (str): The results of a page.
        ID (str): The identifier of a work, an author or an institution.
        DOI (str): The DOI of a work.
        TITLE (str): The title of a work.
        DISPLAY_NAME (str): The name of an author, a source or a topic.
        YEAR (str): The publication year of a work.
        DATE (str): The publication date of a work.
        TYPE (str): The type of a work.
        LANGUAGE (str): The language of a work.
        CITED_BY (str): The citations received.
        FWCI (str): The field-weighted citation impact of a work.
        OPEN_ACCESS (str): The open access state of a work.
        IS_OA (str): Whether a work is open access.
        PRIMARY_LOCATION (str): Where a work appeared first.
        SOURCE (str): The source (journal, conference, repository) of a location.
        PRIMARY_TOPIC (str): The main topic of a work.
        AUTHORSHIPS (str): The authors of a work, with their institutions.
        AUTHOR (str): The author of an authorship.
        ORCID (str): The ORCID of an author.
        INSTITUTIONS (str): The institutions of an authorship.
        WORKS_COUNT (str): The works of an author.
        SUMMARY (str): The summary statistics of an author.
        H_INDEX (str): The h-index in the summary statistics.
        LAST_INSTITUTIONS (str): The institutions an author was last seen at.
        LINEAGE (str): An institution and its parents.
        AFFILIATIONS (str): The affiliation texts of an authorship, or the institutions of an author's profile.
        RAW_AFFILIATION (str): An affiliation text, as the paper prints it.
        INSTITUTION_IDS (str): The institutions OpenAlex resolved an affiliation text to.
        INSTITUTION (str): The institution of a profile affiliation.
        YEARS (str): The years of a profile affiliation.
    """

    META = "meta"
    NEXT_CURSOR = "next_cursor"
    COUNT = "count"
    GROUP_BY = "group_by"
    KEY = "key"
    RESULTS = "results"
    ID = "id"
    DOI = "doi"
    TITLE = "title"
    DISPLAY_NAME = "display_name"
    YEAR = "publication_year"
    DATE = "publication_date"
    TYPE = "type"
    LANGUAGE = "language"
    CITED_BY = "cited_by_count"
    FWCI = "fwci"
    OPEN_ACCESS = "open_access"
    IS_OA = "is_oa"
    PRIMARY_LOCATION = "primary_location"
    SOURCE = "source"
    PRIMARY_TOPIC = "primary_topic"
    AUTHORSHIPS = "authorships"
    AUTHOR = "author"
    ORCID = "orcid"
    INSTITUTIONS = "institutions"
    WORKS_COUNT = "works_count"
    SUMMARY = "summary_stats"
    H_INDEX = "h_index"
    LAST_INSTITUTIONS = "last_known_institutions"
    LINEAGE = "lineage"
    AFFILIATIONS = "affiliations"
    RAW_AFFILIATION = "raw_affiliation_string"
    INSTITUTION_IDS = "institution_ids"
    INSTITUTION = "institution"
    YEARS = "years"
