from __future__ import annotations

# Standard Library Imports.
import itertools
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator  # noqa: E501

# First Party Imports.
from models.history.catalog.company import Company
from models.history.catalog.segment_definition import SegmentDefinition
from models.history.enums import EventKind
from models.history.exception import DuplicateKeyError, OverlappingReignError, UnknownReferenceError  # noqa: E501
from models.history.timeline.notable_event import NotableEvent
from models.history.timeline.partial_date import PartialDate
from models.history.timeline.reign import Reign


class Chronology(BaseModel):
    """The leaders of computing and digital infrastructure over time, and the notable events (a curated catalogue).

    Attributes:
        as_of (str): The date of the chronology: the end of the reigns still running.
        segments (List[SegmentDefinition]): The segments, in display order.
        companies (List[Company]): The companies named by the reigns and the events.
        reigns (List[Reign]): Who led each segment, from when to when.
        events (List[NotableEvent]): The notable events.

    Notes:
        The reigns and the events may only name segments and companies defined before them, and the reigns of a
        segment may not overlap (a hand-over at the same date is allowed).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: str = Field(description="The date of the chronology.")
    segments: List[SegmentDefinition] = Field(default_factory=list, description="The segments, in display order.")  # noqa: E501
    companies: List[Company] = Field(default_factory=list, description="The companies.")  # noqa: E501
    reigns: List[Reign] = Field(default_factory=list, description="Who led each segment.")  # noqa: E501
    events: List[NotableEvent] = Field(default_factory=list, description="The notable events.")  # noqa: E501

    @field_validator("as_of", mode="before")
    def validate_as_of(cls, value: JsonValue) -> JsonValue:
        """Validate the raw date of the chronology: a valid partial date.

        Args:
            value (JsonValue): The raw date.

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

    @field_validator("segments", "companies", mode="before")
    def validate_unique(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:  # noqa: E501
        """Validate the raw segments or companies: each key once.

        Args:
            value (JsonValue): The raw entries.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The entries.

        Raises:
            DuplicateKeyError: If two entries share a key.
        """
        if not isinstance(value, list):
            return value
        seen: Set[str] = set()
        for item in value:
            key = str(item.get("key", "")).strip() if isinstance(item, dict) else ""   # noqa: E501
            if key and key in seen:
                raise DuplicateKeyError("segment" if info.field_name == "segments" else "company", key)  # noqa: E501
            seen.add(key)
        return value

    @field_validator("reigns", mode="before")
    def validate_reigns(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:  # noqa: E501
        """Validate the raw reigns: known segments and companies, no overlap within a segment.

        Args:
            value (JsonValue): The raw reigns.
            info (ValidationInfo): The fields validated so far (the date, the segments and the companies).

        Returns:
            JsonValue: The reigns.

        Raises:
            UnknownReferenceError: If a reign names an unknown segment or company.
            OverlappingReignError: If two reigns of a segment overlap.
        """
        if not isinstance(value, list):
            return value
        segments = {segment.key for segment in info.data.get("segments", [])}
        companies = {company.key for company in info.data.get("companies", [])}
        as_of = str(info.data.get("as_of", "9999"))
        dates = PartialDate()
        spans: Dict[str, List[Tuple[float, float, str]]] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            segment, company = str(item.get("segment", "")), str(item.get("company", ""))  # noqa: E501
            if segment not in segments:
                raise UnknownReferenceError("segment", segment)
            if company not in companies:
                raise UnknownReferenceError("company", company)
            start, end = item.get("start"), item.get("end")
            if start is None:
                continue
            begins = dates.fraction(str(start))
            ends = dates.fraction(str(end)) if end is not None else dates.fraction(as_of)  # noqa: E501
            spans.setdefault(segment, []).append((begins, ends, company))
        for segment, reigns in spans.items():
            ordered = sorted(reigns)
            for (_, ends, first), (begins, _, second) in itertools.pairwise(ordered):  # noqa: E501
                if begins < ends:
                    raise OverlappingReignError(segment, first, second)
        return value

    @field_validator("events", mode="before")
    def validate_events(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:  # noqa: E501
        """Validate the raw events: unique keys, known segments and companies.

        Args:
            value (JsonValue): The raw events.
            info (ValidationInfo): The fields validated so far (the segments and the companies).

        Returns:
            JsonValue: The events.

        Raises:
            DuplicateKeyError: If two events share a key.
            UnknownReferenceError: If an event names an unknown segment or company.
        """
        if not isinstance(value, list):
            return value
        segments = {segment.key for segment in info.data.get("segments", [])}
        companies = {company.key for company in info.data.get("companies", [])}
        seen: Set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            if key in seen:
                raise DuplicateKeyError("event", key)
            seen.add(key)
            segment = item.get("segment")
            if segment is not None and str(segment) not in segments:
                raise UnknownReferenceError("segment", str(segment))
            named = item.get("companies")
            for company in named if isinstance(named, list) else []:
                if str(company).strip() not in companies:
                    raise UnknownReferenceError("company", str(company))
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def company(self, key: str) -> Optional[Company]:
        """Get a company.

        Args:
            key (str): Its key.

        Returns:
            Optional[Company]: The company, `None` when unknown.
        """
        return next((company for company in self.companies if company.key == key), None)  # noqa: E501

    def segment(self, key: str) -> Optional[SegmentDefinition]:
        """Get a segment.

        Args:
            key (str): Its key.

        Returns:
            Optional[SegmentDefinition]: The segment, `None` when unknown.
        """
        return next((segment for segment in self.segments if segment.key == key), None)  # noqa: E501

    def reigns_of(self, segment: str) -> List[Reign]:
        """List the reigns of a segment.

        Args:
            segment (str): The segment key.

        Returns:
            List[Reign]: Its reigns, the earliest first.
        """
        return sorted((reign for reign in self.reigns if reign.segment == segment), key=lambda reign: reign.begins())  # noqa: E501

    def events_of(self, kinds: Optional[Sequence[EventKind]] = None) -> List[NotableEvent]:  # noqa: E501
        """List the events, by date.

        Args:
            kinds (Optional[Sequence[EventKind]]): Only these kinds, every kind when `None`.

        Returns:
            List[NotableEvent]: The events, the earliest first.
        """
        chosen = [event for event in self.events if kinds is None or event.kind in kinds]  # noqa: E501
        return sorted(chosen, key=lambda event: event.when())

    def span(self) -> Tuple[float, float]:
        """Get the time span of the chronology.

        Returns:
            Tuple[float, float]: The earliest reign or event and the date of the chronology, as fractional years.
        """
        dates = PartialDate()
        starts = [reign.begins() for reign in self.reigns] + [event.when() for event in self.events]  # noqa: E501
        end = dates.fraction(self.as_of)
        return (min(starts) if starts else end - 1, end)
