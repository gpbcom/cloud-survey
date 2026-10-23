from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from models.history.enums import DatePrecision, EventKind, EventOutcome

# First Party Imports.
from models.history.exception import InvalidHistoryKeyError
from models.history.timeline.partial_date import PartialDate


class NotableEvent(BaseModel):
    """A notable event of the computing chronology: a dashed marker of the leaders chart (a policy-shock look).

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a key: lower-case words joined by hyphens.
        key (str): Its key, e.g. `us-v-ibm-filed`.
        date (str): When it happened, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        label (str): Its short name, drawn on the chart.
        kind (EventKind): What kind of event it is.
        companies (List[str]): The companies concerned.
        segment (Optional[str]): The segment concerned, if one.
        outcome (Optional[EventOutcome]): What it changed, the verdict of the dossier, if any.
        description (str): What happened.
        source (str): The source, with its tag.
        default (bool): Whether the chart shows it until the analyst picks otherwise.
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Its key.")
    date: str = Field(description="When it happened.")
    label: str = Field(min_length=1, description="Its short name.")
    kind: EventKind = Field(description="What kind of event it is.")
    companies: List[str] = Field(default_factory=list, description="The companies concerned.")
    segment: Optional[str] = Field(default=None, description="The segment concerned.")
    outcome: Optional[EventOutcome] = Field(default=None, description="What it changed.")
    description: str = Field(default="", description="What happened.")
    source: str = Field(default="", description="The source.")
    default: bool = Field(default=False, description="Whether the chart shows it at first.")

    @field_validator("key", mode="before")
    def validate_key(cls, value: JsonValue) -> JsonValue:
        """Validate the raw key: lower-case words joined by hyphens.

        Args:
            value (JsonValue): The raw key.

        Returns:
            JsonValue: The key, trimmed.

        Raises:
            InvalidHistoryKeyError: If it is not lower-case words joined by hyphens.
        """
        if not isinstance(value, str):
            return value
        key = value.strip()
        if not cls.KEY.match(key):
            raise InvalidHistoryKeyError("event key", value, "lower-case words joined by hyphens")
        return key

    @field_validator("date", mode="before")
    def validate_date(cls, value: JsonValue) -> JsonValue:
        """Validate the raw date: a valid partial date.

        Args:
            value (JsonValue): The raw date (a year may be given as a number).

        Returns:
            JsonValue: The date, as text.

        Raises:
            InvalidHistoryDateError: If it is not a valid date.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str):
            PartialDate().parts(value)
            return value.strip()
        return value

    @field_validator("label", "description", "source", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text.
        """
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: each once, in their order.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies.
        """
        if not isinstance(value, list):
            return value
        unique: List[JsonValue] = [*dict.fromkeys(str(item).strip() for item in value)]
        return unique

    ############################
    # Publicly Exposed Methods #
    ############################

    def when(self) -> float:
        """Place the event on a time axis.

        Returns:
            float: Its fractional year (the start of its period).
        """
        return PartialDate().fraction(self.date)

    def year(self) -> int:
        """Get the year of the event.

        Returns:
            int: Its year.
        """
        return PartialDate().parts(self.date)[0]

    def precision(self) -> DatePrecision:
        """Tell how precisely the date is known.

        Returns:
            DatePrecision: The year, the month or the day.
        """
        return PartialDate().parts(self.date)[3]
