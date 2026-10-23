from __future__ import annotations

# Standard Library Imports.
import html
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

# First Party Imports.
from analytics.history.chronology_timeline import ChronologyTimeline
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme
from models.history.chronology import Chronology
from models.history.timeline.notable_event import NotableEvent

type MarkerHit = Tuple[float, Optional[QRectF], NotableEvent]


class EventMarkers:
    """Paint the notable events of the chronology on a time chart: the policy-shock markers of mega-trends.

    Attributes:
        REACH (ClassVar[float]): How close, in pixels, the mouse must be to a marker line to hover it.
        theme (Theme): The application theme.
        timeline (ChronologyTimeline): Names the enum values.
        hits (List[MarkerHit]): The markers of the last paint (their x, their label box and their event).
        logger (Logger): The painter logger.

    Notes:
        A marker is a dashed line in the policy-shock colour across the plot, its label in the same colour in a
        strip above the plot, centred on the line. Labels that would overlap step down a row, and are left out
        beyond the last row (the line and its tooltip stay). The leaders, market share and stock charts share it,
        so that one pick in the "Notable events" menu marks the same dates on all of them.
    """

    REACH: ClassVar[float] = 4.0

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize the painter.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The painter logger.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.timeline = ChronologyTimeline(self.logger)
        self.hits: List[MarkerHit] = []

    ############################
    # Publicly Exposed Methods #
    ############################

    def paint(
        self,
        painter: QPainter,
        frame: PlotFrame,
        events: Sequence[NotableEvent],
        strip: Tuple[float, int, int],
        bounds: Tuple[float, float],
        highlighted: Optional[str] = None,
    ) -> List[MarkerHit]:
        """Paint the events within the frame's years as dashed markers, their labels staggered in the strip.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame, its x values in fractional years.
            events (Sequence[NotableEvent]): The events picked.
            strip (Tuple[float, int, int]): The top of the label strip, its rows and the height of a row.
            bounds (Tuple[float, float]): The leftmost and rightmost pixels a label may use.
            highlighted (Optional[str]): The key (`event:<key>`) of the marker drawn thicker, if any.

        Returns:
            List[MarkerHit]: The markers painted, also kept in `hits` for the mouse.
        """
        top, rows, row_height = strip
        self.hits = []
        color = QColor(self.theme.POLICY_SHOCK)
        metrics = painter.fontMetrics()
        ends = [-math.inf] * rows
        for event in sorted(events, key=lambda item: item.when()):
            when = event.when()
            if not frame.x_low <= when <= frame.x_high:
                continue
            x = frame.map_x(when)
            width = metrics.horizontalAdvance(event.label) + 8
            left = min(max(x - width / 2, bounds[0]), bounds[1] - width)
            row = next((index for index, end in enumerate(ends) if end <= left), None)
            label: Optional[QRectF] = None
            if row is not None:
                ends[row] = left + width + 4
                label = QRectF(left, top + row * row_height, width, row_height)
            strong = highlighted == f"event:{event.key}"
            painter.setPen(QPen(color, 2 if strong else 1, Qt.PenStyle.DashLine))
            line_top = label.bottom() if label is not None else frame.area.top()
            painter.drawLine(QPointF(x, line_top), QPointF(x, frame.area.bottom()))
            if label is not None:
                painter.setPen(color)
                font = painter.font()
                font.setBold(strong)
                painter.setFont(font)
                painter.drawText(label, Qt.AlignmentFlag.AlignCenter, event.label)
                font.setBold(False)
                painter.setFont(font)
            self.hits.append((x, label, event))
        return self.hits

    def at(self, position: QPointF, top: float) -> Optional[NotableEvent]:
        """Find the marker under the mouse: on its label, or near its line.

        Args:
            position (QPointF): The mouse position.
            top (float): The top of the label strip (the lines are not hovered above it).

        Returns:
            Optional[NotableEvent]: The nearest event within reach, if any.
        """
        best: Optional[NotableEvent] = None
        reach = self.REACH
        for x, label, event in self.hits:
            if label is not None and label.contains(position):
                return event
            distance = abs(x - position.x())
            if distance <= reach and position.y() >= top:
                best, reach = event, distance
        return best

    def tooltip(self, event: NotableEvent, chronology: Optional[Chronology], hint: str = "") -> str:
        """Explain a marker.

        Args:
            event (NotableEvent): Its event.
            chronology (Optional[Chronology]): The chronology naming its companies and segment.
            hint (str): What a click on it does, if anything.

        Returns:
            str: The rich text tooltip.
        """
        names = [chronology.company(key) for key in event.companies] if chronology else []
        companies = ", ".join(company.label for company in names if company)
        segment = chronology.segment(event.segment) if chronology and event.segment else None
        heading = f"{event.date} — {event.label}"
        rows = [
            f"<p style='margin:0'><b style='color:{self.theme.POLICY_SHOCK}'>{html.escape(heading)}</b></p>",
            f"<p style='margin:0'>{html.escape(self.timeline.name(event.kind))}"
            + (f" · {html.escape(segment.label)}" if segment else "")
            + (f" · {html.escape(companies)}" if companies else "")
            + "</p>",
            f"<p>{html.escape(event.description)}</p>",
        ]
        if event.outcome:
            rows.append(f"<p><b>Outcome:</b> {html.escape(self.timeline.name(event.outcome))}</p>")
        rows.append(f"<p style='color:{self.theme.TEXT_MUTED}'>Source: {html.escape(event.source)}. {hint}</p>")
        return "<qt>" + "".join(rows) + "</qt>"
