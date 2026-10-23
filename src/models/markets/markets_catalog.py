from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Dict, List, Optional, Pattern, Set

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.markets.catalog.currency_series import CurrencySeries
from models.markets.catalog.google_finance_settings import GoogleFinanceSettings
from models.markets.catalog.market_area import MarketArea
from models.markets.catalog.series_label import SeriesLabel
from models.markets.catalog.share_segment import ShareSegment
from models.markets.enums import AreaKind, ShareSource, StatCounterStat
from models.markets.exception import (
    DuplicateMarketKeyError,
    InvalidMarketListError,
    InvalidMarketValueError,
    UnknownMarketReferenceError,
)
from models.markets.field_check import MarketFieldCheck
from models.markets.listings.hq_region import HqRegion
from models.markets.listings.manual_share import ManualShare
from models.markets.listings.stock_listing import StockListing
from models.markets.listings.valuation_point import ValuationPoint
from models.markets.press.press_family import PressFamily


class MarketsCatalog(BaseModel):
    """What the market shares and the stock values are read for (`conf/history/markets.yaml`).

    Attributes:
        MONTH (ClassVar[Pattern[str]]): The format of a month: `YYYY-MM`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        UNIQUE_KEYS (ClassVar[Dict[str, str]]): The key attribute of each list whose entries must be unique, with
            the name its errors give an entry.
        statcounter_from (str): The first month asked from StatCounter, `YYYY-MM` (its data start in 2009-01).
        google_finance (GoogleFinanceSettings): How the price histories are asked from Google Finance.
        segments (List[ShareSegment]): The markets whose shares are followed, in display order.
        areas (List[MarketArea]): The areas the shares are measured in, in display order.
        labels (List[SeriesLabel]): The company behind each label of a share source.
        currencies (List[CurrencySeries]): The FRED series converting each currency to US dollars.
        regions (List[HqRegion]): The regions the listed companies are grouped by.
        listings (List[StockListing]): The listings whose prices are read.
        valuations (List[ValuationPoint]): The sourced valuation points of the dossier.
        press (List[PressFamily]): The families of analyst press releases read, the narrow ones first.
        manual_shares (List[ManualShare]): The shares of the source dossier no crawled source gives (pre-2009).
        press_names (List[str]): The companies the press releases name without a company of the chronology (Elpida,
            Powerchip…): read under their own name, so that their share never goes to the company named before.

    Notes:
        The companies named by the labels, the listings and the valuations are the chronology's
        (`conf/history/chronology.yaml`): the loader checks them against it.
    """

    MONTH: ClassVar[Pattern[str]] = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()
    UNIQUE_KEYS: ClassVar[Dict[str, str]] = {
        "segments": "segment",
        "areas": "area",
        "currencies": "currency",
        "regions": "region",
        "listings": "listing",
    }

    model_config = ConfigDict(frozen=True, extra="forbid")

    statcounter_from: str = Field(default="2009-01", description="The first month asked from StatCounter.")
    google_finance: GoogleFinanceSettings = Field(
        default_factory=GoogleFinanceSettings, description="How the price histories are asked."
    )
    segments: List[ShareSegment] = Field(default_factory=list, description="The markets followed.")
    areas: List[MarketArea] = Field(default_factory=list, description="The areas.")
    labels: List[SeriesLabel] = Field(default_factory=list, description="The company behind each label.")
    currencies: List[CurrencySeries] = Field(default_factory=list, description="The FRED series of each currency.")
    regions: List[HqRegion] = Field(default_factory=list, description="The headquarters regions.")
    listings: List[StockListing] = Field(default_factory=list, description="The listings.")
    valuations: List[ValuationPoint] = Field(default_factory=list, description="The valuation points.")
    press: List[PressFamily] = Field(default_factory=list, description="The families of press releases read.")
    manual_shares: List[ManualShare] = Field(default_factory=list, description="The shares of the source dossier.")
    press_names: List[str] = Field(default_factory=list, description="The unmapped companies of the releases.")

    @field_validator("statcounter_from", mode="before")
    def validate_statcounter_from(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first month: `YYYY-MM`.

        Args:
            value (JsonValue): The raw month.

        Returns:
            JsonValue: The month, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not written `YYYY-MM`.
        """
        month = cls.CHECK.text(value, "first StatCounter month", 7) or ""
        if not cls.MONTH.match(month):
            raise InvalidMarketValueError("first StatCounter month", month, "YYYY-MM")
        return month

    @field_validator("segments", "areas", "currencies", "regions", "listings", mode="before")
    def validate_unique(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw entries: each key once.

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries.

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateMarketKeyError: If two entries share a key.
        """
        kind = cls.UNIQUE_KEYS[str(info.field_name)]
        value = cls.CHECK.items(value, f"catalogue {info.field_name}", f"{kind} entries")
        attribute = {"currency": "currency", "listing": "symbol"}.get(kind, "key")
        seen: Set[str] = set()
        for item in value:
            raw = item.get(attribute) if isinstance(item, dict) else None
            key = "".join(raw.split()).upper() if kind == "listing" and isinstance(raw, str) else raw
            if isinstance(key, str) and key.strip() in seen:
                raise DuplicateMarketKeyError(kind, key.strip())
            if isinstance(key, str):
                seen.add(key.strip())
        return value

    @field_validator("google_finance", mode="before")
    def validate_google_finance(cls, value: JsonValue) -> JsonValue:
        """Validate the raw Google Finance settings: a mapping (or the settings themselves).

        Args:
            value (JsonValue): The raw settings.

        Returns:
            JsonValue: The settings (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If they are not a mapping.
        """
        if isinstance(value, (dict, GoogleFinanceSettings)):
            return value
        raise InvalidMarketListError("Google Finance settings", "a mapping of settings")

    @field_validator("labels", "valuations", "press", "manual_shares", mode="before")
    def validate_entries(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate raw entries of a list without keys: a list of mappings (or of the entries themselves).

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is not a list of mappings.
        """
        entries = cls.CHECK.items(value, f"catalogue {info.field_name}", "entries")
        if not all(
            isinstance(entry, (dict, SeriesLabel, ValuationPoint, PressFamily, ManualShare)) for entry in entries
        ):
            raise InvalidMarketListError(f"catalogue {info.field_name}", "a list of mappings")
        return entries

    @field_validator("press_names", mode="before")
    def validate_press_names(cls, value: JsonValue) -> JsonValue:
        """Validate the raw unmapped company names: texts of 1 to 80 characters, each once.

        Args:
            value (JsonValue): The raw names.

        Returns:
            JsonValue: The names, trimmed, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a name is not a text of 1 to 80 characters.
        """
        names = [cls.CHECK.text(item, "press name", 80) for item in cls.CHECK.items(value, "press names", "names")]
        unique: List[JsonValue] = [*dict.fromkeys(name for name in names if name)]
        return unique

    @field_validator("areas", mode="before")
    def validate_union_members(cls, value: JsonValue) -> JsonValue:
        """Validate the raw unions: each member is a country area of the catalogue.

        Args:
            value (JsonValue): The raw areas.

        Returns:
            JsonValue: The areas.

        Raises:
            UnknownMarketReferenceError: If a union names a country the catalogue does not define.
        """
        if not isinstance(value, list):
            return value
        entries = [item for item in value if isinstance(item, dict)]
        countries = {str(item.get("key", "")).strip() for item in entries if item.get("kind") == AreaKind.COUNTRY.value}
        for item in entries:
            members = item.get("members")
            for member in members if isinstance(members, list) else []:
                code = member.strip().upper() if isinstance(member, str) else str(member)
                if code not in countries:
                    raise UnknownMarketReferenceError(f"member country of {item.get('key')}", code)
        return value

    @field_validator("listings", mode="before")
    def validate_listing_currencies(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw listings: each currency converts to US dollars.

        Args:
            value (JsonValue): The raw listings.
            info (ValidationInfo): The fields validated before (the currencies).

        Returns:
            JsonValue: The listings.

        Raises:
            UnknownMarketReferenceError: If a listing trades in a currency without FRED series.
        """
        if not isinstance(value, list):
            return value
        series = info.data.get("currencies")
        known = {"USD"} | ({entry.currency for entry in series} if isinstance(series, list) else set())
        for item in value:
            currency = item.get("currency") if isinstance(item, dict) else None
            code = currency.strip().upper() if isinstance(currency, str) else None
            if code and code not in known:
                raise UnknownMarketReferenceError("currency", code)
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def area(self, key: str) -> Optional[MarketArea]:
        """Get an area.

        Args:
            key (str): Its key.

        Returns:
            Optional[MarketArea]: The area, `None` when unknown.
        """
        return next((area for area in self.areas if area.key == key), None)

    def segment(self, key: str) -> Optional[ShareSegment]:
        """Get a segment.

        Args:
            key (str): Its key.

        Returns:
            Optional[ShareSegment]: The segment, `None` when unknown.
        """
        return next((segment for segment in self.segments if segment.key == key), None)

    def statcounter_segments(self, stats: Optional[List[StatCounterStat]] = None) -> List[ShareSegment]:
        """Get the segments read from StatCounter.

        Args:
            stats (Optional[List[StatCounterStat]]): Only these statistics, all of them when `None` or empty.

        Returns:
            List[ShareSegment]: The StatCounter segments, in display order.
        """
        return [
            segment
            for segment in self.segments
            if segment.source is ShareSource.STATCOUNTER and segment.stat and (not stats or segment.stat in stats)
        ]

    def press_families(self, source: ShareSource) -> List[PressFamily]:
        """Get the families of press releases of a firm.

        Args:
            source (ShareSource): The firm.

        Returns:
            List[PressFamily]: Its families, in the catalogue order.
        """
        return [family for family in self.press if family.source is source]

    def company_of(self, source: ShareSource, label: str) -> Optional[str]:
        """Get the company behind a label of a share source.

        Args:
            source (ShareSource): The source.
            label (str): The label, as printed.

        Returns:
            Optional[str]: The company key, `None` when the label belongs to none.
        """
        return next((entry.company for entry in self.labels if entry.source is source and entry.label == label), None)

    def listings_of(self, company: str) -> List[StockListing]:
        """Get the listings of a company, the primary one first.

        Args:
            company (str): The company key.

        Returns:
            List[StockListing]: Its listings.
        """
        return sorted(
            (listing for listing in self.listings if listing.company == company), key=lambda entry: not entry.primary
        )

    def listing(self, symbol: str) -> Optional[StockListing]:
        """Get a listing.

        Args:
            symbol (str): The listing, `EXCHANGE:SYMBOL`.

        Returns:
            Optional[StockListing]: The listing, `None` when unknown.
        """
        return next((listing for listing in self.listings if listing.symbol == symbol), None)

    def currency_series(self, currency: str) -> Optional[CurrencySeries]:
        """Get the FRED series of a currency.

        Args:
            currency (str): The currency.

        Returns:
            Optional[CurrencySeries]: Its series, `None` for the US dollar or an unknown currency.
        """
        return next((entry for entry in self.currencies if entry.currency == currency), None)

    def region_of(self, country: Optional[str]) -> Optional[HqRegion]:
        """Get the region of a country of headquarters.

        Args:
            country (Optional[str]): The country, ISO 3166-1 alpha-2.

        Returns:
            Optional[HqRegion]: Its region, `None` when the country is unknown or in no region.
        """
        return next((region for region in self.regions if country and country in region.countries), None)
