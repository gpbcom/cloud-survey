from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum
from logging import Logger, getLogger
from typing import ClassVar, List, Optional

# First Party Imports.
from models.history.chronology import Chronology
from models.history.timeline.reign import Reign
from models.history.timeline.timeline_entry import TimelineEntry


class ChronologyTimeline:
    """Turn the chronology into the dated lines printed in the analysis: the changes of leader and the events.

    Attributes:
        LEADERSHIP (ClassVar[str]): The kind of a change of leader.
        RANGE (ClassVar[str]): The dash between two years (an en dash).
        logger (Logger): The timeline logger.

    Notes:
        Each reign gives a line when it starts ("Google takes the lead in search, after Yahoo"), and a second one when
        it ends without a successor (the segment fades out). Each event gives a line. The lines are sorted by date,
        the changes of leader first on a tie.
    """

    LEADERSHIP: ClassVar[str] = "Leadership"
    RANGE: ClassVar[str] = "\u2013"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the timeline.

        Args:
            logger (Optional[Logger]): The timeline logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _company(self, chronology: Chronology, key: str) -> str:
        """Name a company.

        Args:
            chronology (Chronology): The chronology.
            key (str): The company key.

        Returns:
            str: Its label, its key when unknown.
        """
        company = chronology.company(key)
        return company.label if company else key

    def _segment(self, chronology: Chronology, key: Optional[str]) -> str:
        """Name a segment.

        Args:
            chronology (Chronology): The chronology.
            key (Optional[str]): The segment key, if any.

        Returns:
            str: Its label, empty without a segment.
        """
        if not key:
            return ""
        segment = chronology.segment(key)
        return segment.label if segment else key

    def _inline(self, label: str) -> str:
        """Write a segment name inside a sentence: its first letter lowered, unless it starts an acronym.

        Args:
            label (str): The segment name, e.g. `Frontier AI labs` or `PCs`.

        Returns:
            str: E.g. `frontier AI labs`, `PCs`.
        """
        if len(label) > 1 and label[1].isupper():
            return label
        return label[:1].lower() + label[1:]

    def _reign_lines(self, chronology: Chronology, reigns: List[Reign]) -> List[TimelineEntry]:
        """Write the lines of the reigns of a segment.

        Args:
            chronology (Chronology): The chronology.
            reigns (List[Reign]): The reigns of the segment, the earliest first.

        Returns:
            List[TimelineEntry]: A line per change of leader, and one when the last leader leaves no successor.
        """
        lines: List[TimelineEntry] = []
        for index, reign in enumerate(reigns):
            leader = self._company(chronology, reign.company)
            segment = self._segment(chronology, reign.segment)
            before = self._company(chronology, reigns[index - 1].company) if index else ""
            what = f"{leader} takes the lead in {self._inline(segment)}" + (f", after {before}" if before else "")
            lines.append(
                TimelineEntry(
                    key=reign.key(),
                    date=reign.start,
                    when=reign.begins(),
                    kind=self.LEADERSHIP,
                    segment=segment,
                    companies=leader,
                    what=f"{what}. {reign.rise}".strip(),
                    effect=reign.share,
                    source=", ".join(reign.sources),
                )
            )
            if reign.end and index == len(reigns) - 1:
                lines.append(
                    TimelineEntry(
                        key=reign.key(),
                        date=reign.end,
                        when=reign.ends(chronology.as_of),
                        kind=self.LEADERSHIP,
                        segment=segment,
                        companies=leader,
                        what=f"{leader}'s lead ends. {reign.fall}".strip(),
                        effect="No successor in this segment: the market moved on.",
                        source=", ".join(reign.sources),
                    )
                )
        return lines

    ############################
    # Publicly Exposed Methods #
    ############################

    def name(self, value: StrEnum) -> str:
        """Write an enum value for a reader, e.g. `market-access` as `Market access`.

        Args:
            value (StrEnum): The value.

        Returns:
            str: Its readable name.
        """
        return value.value.replace("-", " ").capitalize()

    def period(self, reign: Reign) -> str:
        """Write the period of a reign, e.g. `1981-1994` with an en dash, or `2013-` when it still runs.

        Args:
            reign (Reign): The reign.

        Returns:
            str: Its start and end years.
        """
        return f"{reign.start[:4]}{self.RANGE}{reign.end[:4] if reign.end else ''}"

    def entries(self, chronology: Chronology) -> List[TimelineEntry]:
        """List every line of the chronology, by date.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[TimelineEntry]: The changes of leader and the events, the earliest first.
        """
        lines: List[TimelineEntry] = []
        for segment in chronology.segments:
            lines += self._reign_lines(chronology, chronology.reigns_of(segment.key))
        for event in chronology.events_of():
            lines.append(
                TimelineEntry(
                    key=f"event:{event.key}",
                    date=event.date,
                    when=event.when(),
                    kind=self.name(event.kind),
                    segment=self._segment(chronology, event.segment),
                    companies=", ".join(self._company(chronology, key) for key in event.companies),
                    what=f"{event.label}. {event.description}".strip(),
                    effect=self.name(event.outcome) if event.outcome else "",
                    source=event.source,
                )
            )
        lines.sort(key=lambda line: (line.when, line.kind != self.LEADERSHIP, line.segment))
        self.logger.debug("Chronology timeline of %d lines.", len(lines))
        return lines
