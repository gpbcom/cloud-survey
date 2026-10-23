from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class IdcField(StrEnum):
    """Enums representing the fields of IDC's press release API (WordPress `press-release` posts).

    Attributes:
        ID (str): The identifier of a release.
        DATE (str): Its publication date-time.
        TITLE (str): Its title, rendered.
        LINK (str): Its page.
        CONTENT (str): Its body, rendered.
        RENDERED (str): The rendered HTML of a title or a body.
        SEARCH (str): The meta key holding the search term of a request.
        PAGE (str): The meta key holding the page of a request.
    """

    ID = "id"
    DATE = "date"
    TITLE = "title"
    LINK = "link"
    CONTENT = "content"
    RENDERED = "rendered"
    SEARCH = "idc_search"
    PAGE = "idc_page"
