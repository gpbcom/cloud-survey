from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class TrendForceMeta(StrEnum):
    """Enums representing the meta keys of a TrendForce request, read back with the response.

    Attributes:
        KIND (str): Whether the page is a listing or a release (a `TrendForcePage` value).
        PAGE (str): The number of a listing page.
        TITLE (str): The title of a release, as the listing prints it.
        PUBLISHED (str): The publication day of a release, ISO.
        FAMILY (str): The index of the release family its title matched.
    """

    KIND = "trendforce_kind"
    PAGE = "trendforce_page"
    TITLE = "trendforce_title"
    PUBLISHED = "trendforce_published"
    FAMILY = "trendforce_family"


@unique
class TrendForcePage(StrEnum):
    """Enums representing the kinds of TrendForce pages read.

    Attributes:
        LISTING (str): A page of the semiconductor news listing.
        RELEASE (str): A press release.
    """

    LISTING = "listing"
    RELEASE = "release"


@unique
class TrendForceSelector(StrEnum):
    """Enums representing the CSS selectors of the TrendForce pages.

    Attributes:
        ITEM (str): A release of a listing page.
        LINK (str): The link of a release, holding its title.
        DATE (str): The publication day of a release, e.g. `9 September 2026`.
        BODY (str): The body of a release page.
        BODY_END (str): Where the text of a release ends in its body: the links to the previous and next releases
            follow (their titles must not be read).
    """

    ITEM = "div.list-item"
    LINK = "a.title-link"
    DATE = "h4"
    BODY = "article.presscenter"
    BODY_END = '<div class="text-center press-choose-post"'
