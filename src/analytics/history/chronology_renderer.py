from __future__ import annotations

# Standard Library Imports.
from collections import Counter
from logging import Logger, getLogger
from typing import ClassVar, List, Optional

# First Party Imports.
from analytics.history.chronology_timeline import ChronologyTimeline
from models.history.chronology import Chronology
from models.history.enums import EventKind


class ChronologyRenderer:
    """Print the chronology as the Markdown guide `docs/analysis/leaders-chronology.md`.

    Attributes:
        SOURCE (ClassVar[str]): The source dossier, relative to the guide.
        ARROW (ClassVar[str]): The arrow between two successive leaders.
        INTERVENTIONS (ClassVar[List[EventKind]]): The event kinds whose outcome the guide sums up.
        timeline (ChronologyTimeline): The dated lines of the chronology.
        logger (Logger): The renderer logger.

    Notes:
        The guide is generated, never edited: `uv run render-chronology` writes it from `conf/history/chronology.yaml`,
        and a test checks the committed guide is what the renderer prints. Pipes in the texts are escaped for the
        Markdown tables.
    """

    SOURCE: ClassVar[str] = "sources/computing-leaders-1964-2026.md"
    ARROW: ClassVar[str] = " \u2192 "
    INTERVENTIONS: ClassVar[List[EventKind]] = [EventKind.REGULATION, EventKind.MARKET_ACCESS]

    def __init__(self, timeline: Optional[ChronologyTimeline] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            timeline (Optional[ChronologyTimeline]): The dated lines of the chronology.
            logger (Optional[Logger]): The renderer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.timeline = timeline if timeline else ChronologyTimeline(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _cell(self, text: str) -> str:
        """Write a text in a Markdown table cell.

        Args:
            text (str): The text.

        Returns:
            str: The text, its pipes escaped, a dash when empty.
        """
        return text.replace("|", "\\|").strip() or "-"

    def _row(self, cells: List[str]) -> str:
        """Write a Markdown table row.

        Args:
            cells (List[str]): The cells.

        Returns:
            str: The row.
        """
        return "| " + " | ".join(self._cell(cell) for cell in cells) + " |"

    def _table(self, headers: List[str], rows: List[List[str]]) -> List[str]:
        """Write a Markdown table.

        Args:
            headers (List[str]): The column names.
            rows (List[List[str]]): The rows.

        Returns:
            List[str]: The lines of the table.
        """
        return [self._row(headers), "|" + "---|" * len(headers), *(self._row(row) for row in rows)]

    def _company(self, chronology: Chronology, key: str) -> str:
        """Name a company.

        Args:
            chronology (Chronology): The chronology.
            key (str): The company key.

        Returns:
            str: Its label.
        """
        company = chronology.company(key)
        return company.label if company else key

    def _header(self, chronology: Chronology) -> List[str]:
        """Write the title and the introduction.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The lines.
        """
        start, _ = chronology.span()
        title = f"Leaders of digital infrastructure, {int(start)}{self.timeline.RANGE}{chronology.as_of[:4]}"
        return [
            "[\u2191 Docs index](../README.md)",
            "",
            f"# {title}",
            "",
            "> Generated from `src/conf/history/chronology.yaml` by `uv run render-chronology`. Edit the YAML and run "
            "it again: a test checks that this page matches.",
            "",
            'This page prints the chronology drawn in the Analysis tab, card "Leaders of digital infrastructure": '
            "who led each segment of computing and digital infrastructure, from when to when, and the notable events "
            "drawn there as dashed markers, the way mega-trends draws its policy shocks. The market shares and stock "
            "values of these companies over time, worldwide and by area, are in "
            "[market-shares-and-stocks.md](market-shares-and-stocks.md).",
            "",
            f"As of {chronology.as_of}. Every figure comes from [the source dossier]({self.SOURCE}) and keeps its "
            "source tag: [P] primary filing or regulator, [A] academic or business history, [I] industry analyst, "
            "[J] journalistic, [B] blog or aggregator, [K] established literature, not re-verified, "
            "[Int] interpretation.",
            "",
        ]

    def _successions(self, chronology: Chronology) -> List[str]:
        """Write the successive leaders of every segment, in one table.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The lines.
        """
        rows = [
            [
                segment.label,
                self.ARROW.join(
                    f"{self._company(chronology, reign.company)} ({self.timeline.period(reign)})"
                    for reign in chronology.reigns_of(segment.key)
                ),
            ]
            for segment in chronology.segments
        ]
        return ["## Successive leaders", "", *self._table(["Segment", "Leaders, in order"], rows), ""]

    def _segments(self, chronology: Chronology) -> List[str]:
        """Write the reigns of every segment, with their evidence and why they rose and fell.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The lines.
        """
        lines = ["## Leaders by segment", ""]
        headers = [
            "Leader",
            "Period",
            "Evidence",
            "Decisive criteria",
            "Why it led",
            "Why it fell, or where it stands",
            "Sources",
        ]
        for segment in chronology.segments:
            rows = [
                [
                    self._company(chronology, reign.company),
                    self.timeline.period(reign),
                    reign.share,
                    ", ".join(self.timeline.name(criterion) for criterion in reign.criteria),
                    reign.rise,
                    reign.fall,
                    ", ".join(reign.sources),
                ]
                for reign in chronology.reigns_of(segment.key)
            ]
            lines += [f"### {segment.label}", "", segment.description, "", *self._table(headers, rows), ""]
        return lines

    def _chronology(self, chronology: Chronology) -> List[str]:
        """Write every dated line: the changes of leader and the notable events.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The lines.
        """
        rows = [
            [entry.date, entry.kind, entry.segment, entry.companies, entry.what, entry.effect, entry.source]
            for entry in self.timeline.entries(chronology)
        ]
        headers = ["Date", "Kind", "Segment", "Companies", "What happened", "Effect", "Source"]
        return ["## Chronology", "", *self._table(headers, rows), ""]

    def _synthesis(self, chronology: Chronology) -> List[str]:
        """Sum up the criteria of the reigns, the kinds of events and the outcomes of the interventions.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            List[str]: The lines.
        """
        criteria = Counter(criterion for reign in chronology.reigns for criterion in reign.criteria)
        kinds = Counter(event.kind for event in chronology.events)
        interventions = chronology.events_of(self.INTERVENTIONS)
        outcomes = Counter(event.outcome for event in interventions if event.outcome)
        written = ", ".join(f"{self.timeline.name(criterion)} {count}" for criterion, count in criteria.most_common())
        events = ", ".join(f"{self.timeline.name(kind)} {count}" for kind, count in kinds.most_common())
        verdicts = ", ".join(f"{self.timeline.name(outcome)} {count}" for outcome, count in outcomes.most_common())
        return [
            "## What the chronology shows",
            "",
            f"- **Decisive criteria** across the {len(chronology.reigns)} reigns: {written}.",
            f"- **Notable events** ({len(chronology.events)}): {events}.",
            f"- **Outcomes of the {len(interventions)} regulation and market-access events**: {verdicts}.",
            "- The ranking of the criteria and the verdicts on regulation are argued in "
            f"[the source dossier]({self.SOURCE}), sections 3 and 4.",
            "",
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def markdown(self, chronology: Chronology) -> str:
        """Print the chronology as Markdown.

        Args:
            chronology (Chronology): The chronology.

        Returns:
            str: The guide, ending with a newline.
        """
        lines = [
            *self._header(chronology),
            *self._successions(chronology),
            *self._segments(chronology),
            *self._chronology(chronology),
            *self._synthesis(chronology),
        ]
        self.logger.debug("Chronology guide of %d lines.", len(lines))
        return "\n".join(lines).rstrip("\n") + "\n"
