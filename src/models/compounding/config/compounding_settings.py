from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import DateCaveat
from models.compounding.exception import DuplicateCompoundingEntryError
from models.markets.field_check import MarketFieldCheck


class CompoundingSettings(BaseModel):
    """How the service-compounding models are fitted.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        last_year (int): The last complete year fitted (the current year is partial).
        lags (List[int]): The lags tried, in years, between holding the foundations and entering.
        bootstrap (int): The cluster bootstrap resamples of the intervals.
        placebo (int): The random foundation sets of the placebo test.
        seed (int): The seed of the resampling (the results are reproducible).
        min_events (int): The fewest entries for a provider's own fit.
        held_caveats (List[DateCaveat]): The date caveats meaning "launched on or before", counted as held at the
            start of the window, not as launches.
        precedence_share (float): The share of the other providers that must have entered a category before another
            for the first to be a data-driven foundation of the second.
        precedence_providers (int): The fewest other providers holding both categories for that share to count.
        data_driven_size (int): The most data-driven foundations of a category.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    last_year: int = Field(default=2025, description="The last complete year fitted.")
    lags: List[int] = Field(default_factory=lambda: [1, 2, 3], min_length=1, description="The lags tried.")
    bootstrap: int = Field(default=300, description="The bootstrap resamples.")
    placebo: int = Field(default=300, description="The placebo foundation sets.")
    seed: int = Field(default=1, description="The seed of the resampling.")
    min_events: int = Field(default=15, description="The fewest entries for a provider's own fit.")
    held_caveats: List[DateCaveat] = Field(default_factory=list, description="The caveats counted as held.")
    precedence_share: float = Field(default=0.6, description="The precedence share of a data-driven foundation.")
    precedence_providers: int = Field(default=3, description="The fewest providers behind that share.")
    data_driven_size: int = Field(default=3, description="The most data-driven foundations of a category.")

    @field_validator("last_year", mode="before")
    def validate_last_year(cls, value: JsonValue) -> JsonValue:
        """Validate the raw last year: a year between 2010 and 2100.

        Args:
            value (JsonValue): The raw year.

        Returns:
            JsonValue: The year.

        Raises:
            InvalidMarketNumberError: If it is not a whole year in range.
        """
        return cls.CHECK.number(value, "last year", low=2010, high=2100, integer=True)

    @field_validator("lags", mode="before")
    def validate_lags(cls, value: JsonValue) -> JsonValue:
        """Validate the raw lags: a list of 1 to 5 years, each once.

        Args:
            value (JsonValue): The raw lags.

        Returns:
            JsonValue: The lags, sorted.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketNumberError: If a lag is not a whole number of 1 to 5 years.
            DuplicateCompoundingEntryError: If a lag is listed twice.
        """
        lags: List[JsonValue] = []
        for item in cls.CHECK.items(value, "lags", "whole numbers of years"):
            lag = cls.CHECK.number(item, "lag", low=1, high=5, integer=True)
            if lag in lags:
                raise DuplicateCompoundingEntryError("lag", str(lag))
            lags.append(lag)
        ordered: List[JsonValue] = []
        ordered.extend(sorted(lag for lag in lags if isinstance(lag, int)))
        return ordered

    @field_validator("bootstrap", "placebo", mode="before")
    def validate_draws(cls, value: JsonValue) -> JsonValue:
        """Validate a raw number of draws: a whole number from 0 to 5000.

        Args:
            value (JsonValue): The raw number.

        Returns:
            JsonValue: The number.

        Raises:
            InvalidMarketNumberError: If it is not a whole number in range.
        """
        return cls.CHECK.number(value, "number of draws", low=0, high=5000, integer=True)

    @field_validator("seed", mode="before")
    def validate_seed(cls, value: JsonValue) -> JsonValue:
        """Validate the raw seed: a whole number.

        Args:
            value (JsonValue): The raw seed.

        Returns:
            JsonValue: The seed.

        Raises:
            InvalidMarketNumberError: If it is not a whole number.
        """
        return cls.CHECK.number(value, "seed", low=0, integer=True)

    @field_validator("min_events", "precedence_providers", "data_driven_size", mode="before")
    def validate_count(cls, value: JsonValue) -> JsonValue:
        """Validate a raw count: a whole number from 1 to 1000.

        Args:
            value (JsonValue): The raw count.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidMarketNumberError: If it is not a whole number in range.
        """
        return cls.CHECK.number(value, "count", low=1, high=1000, integer=True)

    @field_validator("held_caveats", mode="before")
    def validate_held_caveats(cls, value: JsonValue) -> JsonValue:
        """Validate the raw held caveats: a list of date caveats, each once.

        Args:
            value (JsonValue): The raw caveats.

        Returns:
            JsonValue: The caveats (checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompoundingEntryError: If a caveat is listed twice.
        """
        items = cls.CHECK.items(value, "held caveats", "date caveats")
        if len({str(item) for item in items}) != len(items):
            raise DuplicateCompoundingEntryError("held caveat", ", ".join(str(item) for item in items))
        return items

    @field_validator("precedence_share", mode="before")
    def validate_precedence_share(cls, value: JsonValue) -> JsonValue:
        """Validate the raw precedence share: a share above one half, up to 1.

        Args:
            value (JsonValue): The raw share.

        Returns:
            JsonValue: The share.

        Raises:
            InvalidMarketNumberError: If it is not in (0.5, 1].
        """
        return cls.CHECK.number(value, "precedence share", low=0.5, high=1, strict_low=True)
