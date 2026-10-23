from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.history.enums import AdoptionCriterion
from models.history.exception import ReignOrderError
from models.history.timeline.partial_date import PartialDate


class Reign(BaseModel):
    """A company leading a segment from a date to a date: a band of the leaders chart.

    Attributes:
        segment (str): The segment led.
        company (str): The leader.
        start (str): When it took the lead, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
        end (Optional[str]): When it lost it, `None` when it still leads.
        share (str): The evidence of the lead (shares, revenue, valuation), with its source tags.
        criteria (List[AdoptionCriterion]): The adoption criteria the dossier rates as decisive.
        rise (str): Why it took the lead.
        fall (str): Why it lost it, or where it stands.
        sources (List[str]): The sources, with their tags ([P], [A], [I], [J], [B], [K], [Int]).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    segment: str = Field(min_length=1, description="The segment led.")
    company: str = Field(min_length=1, description="The leader.")
    start: str = Field(description="When it took the lead.")
    end: Optional[str] = Field(default=None, description="When it lost it.")
    share: str = Field(default="", description="The evidence of the lead.")
    criteria: List[AdoptionCriterion] = Field(default_factory=list, description="The decisive criteria.")
    rise: str = Field(default="", description="Why it took the lead.")
    fall: str = Field(default="", description="Why it lost it, or where it stands.")
    sources: List[str] = Field(default_factory=list, description="The sources.")

    @field_validator("start", mode="before")
    def validate_start(cls, value: JsonValue) -> JsonValue:
        """Validate the raw start: a valid partial date.

        Args:
            value (JsonValue): The raw start (a year may be given as a number).

        Returns:
            JsonValue: The start, as text.

        Raises:
            InvalidHistoryDateError: If it is not a valid date.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str):
            PartialDate().parts(value)
            return value.strip()
        return value

    @field_validator("end", mode="before")
    def validate_end(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw end: a valid partial date, not before the start.

        Args:
            value (JsonValue): The raw end (a year may be given as a number).
            info (ValidationInfo): The fields validated so far (the start).

        Returns:
            JsonValue: The end, as text.

        Raises:
            InvalidHistoryDateError: If it is not a valid date.
            ReignOrderError: If it comes before the start.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str):
            return value
        dates = PartialDate()
        end = value.strip()
        start = info.data.get("start")
        if isinstance(start, str) and dates.fraction(end) < dates.fraction(start):
            raise ReignOrderError(start, end)
        return end

    @field_validator("share", "rise", "fall", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed, its lines joined.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text.
        """
        return " ".join(value.split()) if isinstance(value, str) else value

    ############################
    # Publicly Exposed Methods #
    ############################

    def key(self) -> str:
        """Identify the reign (to link the chart and the table).

        Returns:
            str: `reign:<segment>:<company>:<start>`.
        """
        return f"reign:{self.segment}:{self.company}:{self.start}"

    def begins(self) -> float:
        """Place the start on a time axis.

        Returns:
            float: Its fractional year.
        """
        return PartialDate().fraction(self.start)

    def ends(self, as_of: str) -> float:
        """Place the end on a time axis.

        Args:
            as_of (str): The date of the chronology, the end of an ongoing reign.

        Returns:
            float: Its fractional year.
        """
        return PartialDate().fraction(self.end if self.end else as_of)
