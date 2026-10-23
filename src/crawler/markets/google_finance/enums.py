from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class GoogleFinanceMeta(StrEnum):
    """Enums representing the meta keys of a Google Finance request, read back with the response.

    Attributes:
        LISTING (str): The listing of the catalogue, `EXCHANGE:SYMBOL`.
        CANDIDATE (str): The index of the Google exchange code tried, among the listing's candidates.
    """

    LISTING = "google_finance_listing"
    CANDIDATE = "google_finance_candidate"


@unique
class GoogleFinanceHeader(StrEnum):
    """Enums representing the headers the chart RPC expects.

    Attributes:
        SAME_DOMAIN (str): Marks the call as the page's own (`1`), without which the RPC refuses it.
        CONTENT_TYPE (str): The form encoding of the body.
        COOKIE (str): The consent cookies.
        REFERER (str): The quote page the chart belongs to.
    """

    SAME_DOMAIN = "X-Same-Domain"
    CONTENT_TYPE = "Content-Type"
    COOKIE = "Cookie"
    REFERER = "Referer"


@unique
class BatchExecuteField(StrEnum):
    """Enums representing the markers of a `batchexecute` request and response.

    Attributes:
        PREFIX (str): The anti-JSON-hijacking prefix of the response body.
        ENVELOPE (str): The tag of an envelope carrying an RPC payload.
        REQUEST (str): The form field holding the doubly encoded request.
        GENERIC (str): The last member of a request envelope.
        CONSENT_HOST (str): The host of Google's consent wall.
    """

    PREFIX = ")]}'"
    ENVELOPE = "wrb.fr"
    REQUEST = "f.req"
    GENERIC = "generic"
    CONSENT_HOST = "consent.google.com"
