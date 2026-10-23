from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, List, Optional, Pattern, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class StockListing(BaseModel):
    """A listing of a company on a stock exchange, e.g. TSMC in Taipei (`TPE:2330`) and its New York ADR (`NYSE:TSM`).

    Attributes:
        SYMBOL (ClassVar[Pattern[str]]): The format of a listing: `EXCHANGE:SYMBOL`.
        KEY (ClassVar[Pattern[str]]): The format of a company key: lower-case words joined by hyphens.
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: three upper-case letters.
        GOOGLE_EXCHANGES (ClassVar[Dict[str, Tuple[str, ...]]]): The Google Finance codes an exchange may be filed
            under, most likely first (from mega-trends' `StockSymbol`).
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        company (str): The company of the chronology it belongs to.
        symbol (str): The listing, `EXCHANGE:SYMBOL`, e.g. `NASDAQ:MSFT`.
        currency (str): The currency it trades in, e.g. `TWD`.
        primary (bool): Whether it is the company's main listing (the one its region index and its correlations use).
        note (Optional[str]): What the listing stands for when it is not obvious, e.g. `Parent of AWS`.

    Notes:
        A subsidiary carries its parent's listing (AWS trades as Amazon, Google Cloud as Alphabet), and the note
        says so.
    """

    SYMBOL: ClassVar[Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{0,14}:[A-Z0-9][A-Z0-9.\-]{0,11}$")
    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    GOOGLE_EXCHANGES: ClassVar[Dict[str, Tuple[str, ...]]] = {
        "FWB": ("ETR", "FRA"),
        "XETRA": ("ETR",),
        "LSE": ("LON",),
        "TSX": ("TSE",),
        "HKEX": ("HKG",),
        "SSE": ("SHA",),
        "SZSE": ("SHE",),
        "KOSE": ("KRX",),
        "TWSE": ("TPE",),
        "TSE": ("TYO",),
        "EURONEXT": ("EPA", "AMS", "EBR"),
        "OMX": ("STO", "HEL", "CPH"),
        "AMEX": ("NYSEAMERICAN",),
        "OTC": ("OTCMKTS",),
    }

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(description="The company it belongs to.")
    symbol: str = Field(description="The listing, EXCHANGE:SYMBOL.")
    currency: str = Field(description="The currency it trades in.")
    primary: bool = Field(default=True, description="Whether it is the company's main listing.")
    note: Optional[str] = Field(default=None, max_length=200, description="What the listing stands for.")

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a key of the chronology.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The company key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "company key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("company key", key, "lower-case words joined by hyphens")
        return key

    @field_validator("symbol", mode="before")
    def validate_symbol(cls, value: JsonValue) -> JsonValue:
        """Validate the raw listing: `EXCHANGE:SYMBOL`, upper-cased.

        Args:
            value (JsonValue): The raw listing.

        Returns:
            JsonValue: The listing, upper-cased, without spaces.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not written `EXCHANGE:SYMBOL`.
        """
        symbol = "".join((cls.CHECK.text(value, "stock listing", 30) or "").split()).upper()
        if not cls.SYMBOL.match(symbol):
            raise InvalidMarketValueError("stock listing", symbol, "EXCHANGE:SYMBOL, e.g. NASDAQ:MSFT")
        return symbol

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not three letters.
        """
        currency = (cls.CHECK.text(value, "currency", 3) or "").upper()
        if not cls.CURRENCY.match(currency):
            raise InvalidMarketValueError("currency", currency, "three letters (ISO 4217)")
        return currency

    @field_validator("note", mode="before")
    def validate_note(cls, value: JsonValue) -> JsonValue:
        """Validate the raw note: a text of at most 200 characters, single-spaced, `None` when blank.

        Args:
            value (JsonValue): The raw note.

        Returns:
            JsonValue: The note.

        Raises:
            InvalidMarketTextError: If it is not a text of at most 200 characters.
        """
        return cls.CHECK.text(value, "listing note", 200, optional=True)

    @field_validator("primary", mode="before")
    def validate_primary(cls, value: JsonValue) -> JsonValue:
        """Validate the raw primary flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "primary listing")

    ############################
    # Publicly Exposed Methods #
    ############################

    def exchange(self) -> str:
        """Get the exchange of the listing.

        Returns:
            str: The exchange, e.g. `NASDAQ`.
        """
        return self.symbol.split(":", 1)[0]

    def ticker(self) -> str:
        """Get the ticker of the listing.

        Returns:
            str: The ticker, e.g. `MSFT`.
        """
        return self.symbol.split(":", 1)[1]

    def google_candidates(self) -> List[Tuple[str, str]]:
        """Get the `(ticker, exchange)` pairs Google Finance may file the listing under, most likely first.

        Returns:
            List[Tuple[str, str]]: The ticker with each Google code of its exchange (`FWB:SAP` gives `SAP` on `ETR`
                then `FRA`), the listing itself when its exchange needs no translation.
        """
        exchanges = self.GOOGLE_EXCHANGES.get(self.exchange(), (self.exchange(),))
        return [(self.ticker(), exchange) for exchange in exchanges]
