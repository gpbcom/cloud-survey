from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class SecIdentityStep(StrEnum):
    """Enums representing what a request of the SEC identity resolver reads.

    Attributes:
        TICKERS (str): The listed filers (`company_tickers_exchange.json`).
        SUBMISSIONS (str): The submissions of a filer, which state its name, former names and tickers.
    """

    TICKERS = "tickers"
    SUBMISSIONS = "submissions"


@unique
class SecIdentityField(StrEnum):
    """Enums representing the fields the SEC identity resolver reads.

    Attributes:
        FIELDS (str): The column names of the tickers file.
        DATA (str): Its rows.
        CIK (str): The filer column.
        NAME (str): The name column of the tickers file, the name of a filer in its submissions.
        TICKER (str): The ticker column of the tickers file.
        EXCHANGE (str): The exchange column of the tickers file.
        TICKERS (str): The tickers of a filer in its submissions.
        FORMER_NAMES (str): The former names of a filer in its submissions.
    """

    FIELDS = "fields"
    DATA = "data"
    CIK = "cik"
    NAME = "name"
    TICKER = "ticker"
    EXCHANGE = "exchange"
    TICKERS = "tickers"
    FORMER_NAMES = "formerNames"
