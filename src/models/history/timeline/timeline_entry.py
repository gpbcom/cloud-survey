from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class TimelineEntry(BaseModel):
    """A line of the printed chronology: a change of leader, or a notable event.

    Attributes:
        key (str): The reign or event it comes from (links the table and the chart).
        date (str): When it happened, as written in the chronology.
        when (float): Its fractional year, to sort the lines.
        kind (str): `Leadership`, or the kind of the event.
        segment (str): The segment concerned, empty when none.
        companies (str): The companies concerned.
        what (str): What happened.
        effect (str): Its effect: the evidence of a lead, or the outcome of an event.
        source (str): Where it comes from, with the source tags.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, description="The reign or event it comes from.")
    date: str = Field(min_length=1, description="When it happened.")
    when: float = Field(description="Its fractional year.")
    kind: str = Field(min_length=1, description="Leadership, or the kind of the event.")
    segment: str = Field(default="", description="The segment concerned.")
    companies: str = Field(default="", description="The companies concerned.")
    what: str = Field(default="", description="What happened.")
    effect: str = Field(default="", description="Its effect.")
    source: str = Field(default="", description="Where it comes from.")
