from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class CompanyMeta(StrEnum):
    """Enums representing the meta keys of a companies request, read back with the response.

    Attributes:
        COMPANY (str): The company of the chronology the document is read for.
        FILER (str): The SEC filer (10 digits) of a `companyfacts` document.
        LISTING (str): The listing of a quote page, `EXCHANGE:SYMBOL`.
        CANDIDATE (str): The index of the Google exchange code tried, among the listing's candidates.
        QUERY (str): The assignee search of a patents window.
        AFTER (str): The first priority date of a patents window.
        BEFORE (str): The day after the last priority date of a patents window.
        COUNTRY (str): The patent office of a patents window, empty for every office.
        EXPECTED (str): The publications the search counts in a window (known once it was counted).
        STEP (str): What a request of the patents search or of OpenAlex reads (a count, an export, a page).
        PAGE (str): The page of a paged listing.
        CURSOR (str): The cursor of an OpenAlex listing.
        YEAR (str): The publication year of an OpenAlex listing.
        PUBLICATION (str): The publication of a patent page.
        REASON (str): Why an identity resolver checks an identifier.
        TICKER (str): The listed ticker an identity resolver expects a SEC filer to state.
        FISCAL_YEARS (str): The researched fiscal years citing a document.
        SOURCE (str): A document as the researched figures cite it.
    """

    COMPANY = "company"
    FILER = "filer"
    LISTING = "listing"
    CANDIDATE = "candidate"
    QUERY = "query"
    AFTER = "after"
    BEFORE = "before"
    COUNTRY = "country"
    EXPECTED = "expected"
    STEP = "step"
    PAGE = "page"
    CURSOR = "cursor"
    YEAR = "year"
    PUBLICATION = "publication"
    REASON = "reason"
    TICKER = "ticker"
    FISCAL_YEARS = "fiscal-years"
    SOURCE = "source"
