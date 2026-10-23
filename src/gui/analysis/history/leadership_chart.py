from __future__ import annotations

# Standard Library Imports.
import html
import math
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QHelpEvent, QLinearGradient, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from analytics.history.chronology_timeline import ChronologyTimeline
from gui.analysis.events.event_markers import EventMarkers, MarkerHit
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme
from models.history.chronology import Chronology
from models.history.timeline.notable_event import NotableEvent
from models.history.timeline.reign import Reign

type BandHit = Tuple[QRectF, Reign]


class LeadershipChart(QWidget):
    """The leaders of computing over time: a swimlane per segment, a band per reign, a dashed marker per event.

    Attributes:
        LABEL_WIDTH (ClassVar[int]): The width of the segment names, left of the lanes.
        LANE_HEIGHT (ClassVar[int]): The height of a lane.
        LANE_GAP (ClassVar[int]): The space between two lanes.
        STRIP_ROW (ClassVar[int]): The height of a row of event labels, above the lanes.
        STRIP_ROWS (ClassVar[int]): The rows of event labels (labels step down a row when they would overlap).
        AXIS_HEIGHT (ClassVar[int]): The height of the year axis, below the lanes.
        RIGHT (ClassVar[int]): The margin right of the lanes.
        TICK_SPACING (ClassVar[int]): The fewest pixels between two year ticks.
        YEAR_STEPS (ClassVar[Tuple[int, ...]]): The year steps the axis chooses from.
        FADE (ClassVar[int]): The length, in pixels, of the fade ending a reign still running.
        picked (pyqtSignal): Emitted with the key of a clicked band (`reign:...`) or marker (`event:...`).
        theme (Theme): The application theme.
        timeline (ChronologyTimeline): Names the periods and the enum values.
        chronology (Optional[Chronology]): The chronology drawn.
        events (List[NotableEvent]): The events drawn as markers.
        highlighted (Optional[str]): The key of the band or marker outlined.
        message (str): What the chart says without a chronology.
        bands (List[BandHit]): The bands of the last paint, for the mouse.
        markers (List[MarkerHit]): The markers of the last paint, for the mouse.
        marker_painter (EventMarkers): Paints the markers (shared with the market share and stock charts).
        zoom (ChartZoom): Zooms the years (drag, Ctrl+wheel), reset by a double-click or Escape.
        logger (Logger): The chart logger.

    Notes:
        The markers copy the policy shocks of mega-trends: a dashed line in the policy-shock colour across the lanes,
        its label in the same colour near the top of the plot, centred on the line. Labels that would overlap step
        down a row, and are left out beyond the last row (the line and its tooltip stay). Hovering a band or a marker
        explains it, clicking it selects its line in the chronology table.
    """

    LABEL_WIDTH: ClassVar[int] = 170
    LANE_HEIGHT: ClassVar[int] = 24
    LANE_GAP: ClassVar[int] = 4
    STRIP_ROW: ClassVar[int] = 16
    STRIP_ROWS: ClassVar[int] = 3
    AXIS_HEIGHT: ClassVar[int] = 26
    RIGHT: ClassVar[int] = 16
    TICK_SPACING: ClassVar[int] = 56
    YEAR_STEPS: ClassVar[Tuple[int, ...]] = (1, 2, 5, 10, 20)
    FADE: ClassVar[int] = 22

    picked = pyqtSignal(str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.timeline = ChronologyTimeline(self.logger)
        self.chronology: Optional[Chronology] = None
        self.events: List[NotableEvent] = []
        self.highlighted: Optional[str] = None
        self.message = "Loading the chronology..."
        self.bands: List[BandHit] = []
        self.markers: List[MarkerHit] = []
        self.marker_painter = EventMarkers(theme, self.logger)
        self.zoom = ChartZoom(self, zoom_y=False, logger=self.logger)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(self._height())

    ############################
    # Internal Helpers Methods #
    ############################

    def _lanes(self) -> int:
        """Count the lanes.

        Returns:
            int: The segments of the chronology, at least one.
        """
        return max(len(self.chronology.segments) if self.chronology else 0, 1)

    def _height(self) -> int:
        """Get the height fitting every lane.

        Returns:
            int: The label strip, the lanes and the axis.
        """
        top = self.STRIP_ROW * self.STRIP_ROWS + 8
        return top + self._lanes() * (self.LANE_HEIGHT + self.LANE_GAP) + self.AXIS_HEIGHT + 8

    def _plot(self) -> QRectF:
        """Get the area of the lanes.

        Returns:
            QRectF: Right of the segment names, below the label strip, above the axis.
        """
        top = self.STRIP_ROW * self.STRIP_ROWS + 8
        width = max(self.width() - self.LABEL_WIDTH - self.RIGHT, 80)
        return QRectF(self.LABEL_WIDTH, top, width, self._lanes() * (self.LANE_HEIGHT + self.LANE_GAP))

    def _frame(self) -> Optional[PlotFrame]:
        """Map the years shown to the pixels, through the zoom.

        Returns:
            Optional[PlotFrame]: The frame, `None` without a chronology.
        """
        if self.chronology is None:
            return None
        start, end = self.chronology.span()
        full = (math.floor(start) - 1.0, end + 0.5)
        frame = PlotFrame(self._plot(), self.zoom.x_range(*full), (0.0, 1.0))
        self.zoom.set_frame(frame, full, None)
        return frame

    def _lane(self, index: int) -> QRectF:
        """Get the area of a lane.

        Args:
            index (int): The lane, from the top.

        Returns:
            QRectF: Its area, across the plot.
        """
        plot = self._plot()
        top = plot.top() + index * (self.LANE_HEIGHT + self.LANE_GAP) + self.LANE_GAP / 2
        return QRectF(plot.left(), top, plot.width(), self.LANE_HEIGHT)

    def _step(self, frame: PlotFrame) -> int:
        """Choose the year step of the axis.

        Args:
            frame (PlotFrame): The frame.

        Returns:
            int: The smallest step leaving `TICK_SPACING` pixels between two ticks.
        """
        per_year = frame.area.width() / max(frame.x_high - frame.x_low, 1e-9)
        return next((step for step in self.YEAR_STEPS if step * per_year >= self.TICK_SPACING), self.YEAR_STEPS[-1])

    def _ink(self, fill: QColor) -> QColor:
        """Choose a readable text colour on a band.

        Args:
            fill (QColor): The colour of the band.

        Returns:
            QColor: Dark on light bands, light on dark ones.
        """
        luminance = 0.2126 * fill.redF() + 0.7152 * fill.greenF() + 0.0722 * fill.blueF()
        return QColor(self.theme.WINDOW if luminance > 0.55 else self.theme.TEXT)

    def _paint_lanes(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the lanes, the segment names and the year axis.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        chronology = self.chronology
        if chronology is None:
            return
        for index, segment in enumerate(chronology.segments):
            lane = self._lane(index)
            painter.fillRect(lane, QColor(self.theme.SURFACE_ALT if index % 2 else self.theme.SURFACE))
            painter.setPen(QColor(self.theme.TEXT))
            name = painter.fontMetrics().elidedText(segment.label, Qt.TextElideMode.ElideRight, self.LABEL_WIDTH - 14)
            painter.drawText(
                QRectF(0, lane.top(), self.LABEL_WIDTH - 8, lane.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                name,
            )
        plot = frame.area
        step = self._step(frame)
        year = math.ceil(frame.x_low / step) * step
        while year <= frame.x_high:
            x = frame.map_x(year)
            painter.setPen(QPen(QColor(self.theme.BORDER), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(x - 30, plot.bottom() + 4, 60, self.AXIS_HEIGHT - 6), Qt.AlignmentFlag.AlignHCenter, str(year)
            )
            year += step

    def _paint_bands(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint a band per reign, in its company colour, and remember them for the mouse.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        chronology = self.chronology
        self.bands = []
        if chronology is None:
            return
        painter.save()
        painter.setClipRect(frame.area)
        for index, segment in enumerate(chronology.segments):
            lane = self._lane(index).adjusted(0, 2, 0, -2)
            for reign in chronology.reigns_of(segment.key):
                left = frame.map_x(reign.begins())
                right = frame.map_x(reign.ends(chronology.as_of))
                if right < frame.area.left() or left > frame.area.right() or right - left < 0.5:
                    continue
                band = QRectF(left, lane.top(), right - left, lane.height())
                company = chronology.company(reign.company)
                fill = self.theme.company_color(company) if company else QColor(self.theme.ACCENT)
                if reign.end is None and band.width() > self.FADE:
                    fade = QLinearGradient(band.right() - self.FADE, 0, band.right(), 0)
                    ending = QColor(fill)
                    ending.setAlpha(40)
                    fade.setColorAt(0.0, fill)
                    fade.setColorAt(1.0, ending)
                    painter.setBrush(fade)
                else:
                    painter.setBrush(fill)
                outlined = self.highlighted == reign.key()
                painter.setPen(QPen(QColor(self.theme.TEXT), 2) if outlined else Qt.PenStyle.NoPen)
                painter.drawRoundedRect(band.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
                label = (company.label if company else reign.company) + (" \u25b8" if reign.end is None else "")
                if band.width() > 28:
                    painter.setPen(self._ink(fill))
                    shown = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(band.width()) - 10)
                    painter.drawText(band.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, shown)
                self.bands.append((band, reign))
        painter.restore()

    def _paint_markers(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the events as dashed markers, their labels staggered in the strip, and remember them for the mouse.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        self.markers = self.marker_painter.paint(
            painter,
            frame,
            self.events,
            (4.0, self.STRIP_ROWS, self.STRIP_ROW),
            (frame.area.left() - self.LABEL_WIDTH + 4, self.width() - 2),
            self.highlighted,
        )

    def _marker_at(self, position: QPointF) -> Optional[NotableEvent]:
        """Find the marker under the mouse: on its line or its label.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[NotableEvent]: The nearest event within reach, if any.
        """
        return self.marker_painter.at(position, self._plot().top() - self.STRIP_ROW * self.STRIP_ROWS)

    def _band_at(self, position: QPointF) -> Optional[Reign]:
        """Find the band under the mouse.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[Reign]: The reign of the band, if any.
        """
        return next((reign for band, reign in self.bands if band.contains(position)), None)

    def _reign_tooltip(self, reign: Reign) -> str:
        """Explain a band.

        Args:
            reign (Reign): Its reign.

        Returns:
            str: The rich text tooltip.
        """
        chronology = self.chronology
        company = chronology.company(reign.company) if chronology else None
        segment = chronology.segment(reign.segment) if chronology else None
        color = self.theme.company_color(company).name() if company else self.theme.ACCENT
        criteria = ", ".join(self.timeline.name(criterion) for criterion in reign.criteria) or "-"
        leader = html.escape(company.label if company else reign.company)
        led = html.escape(segment.label if segment else reign.segment)
        rows = [
            f"<p style='margin:0'><b style='color:{color}'>{leader}</b> leads {led}, {self.timeline.period(reign)}</p>",
            f"<p><b>Evidence:</b> {html.escape(reign.share)}</p>",
            f"<p><b>Decisive criteria:</b> {html.escape(criteria)}</p>",
            f"<p><b>Why it led:</b> {html.escape(reign.rise)}</p>",
            f"<p><b>Why it fell, or where it stands:</b> {html.escape(reign.fall)}</p>",
            f"<p style='color:{self.theme.TEXT_MUTED}'>Sources: {html.escape(', '.join(reign.sources))}. "
            "Click to find it in the chronology.</p>",
        ]
        return "<qt>" + "".join(rows) + "</qt>"

    def _event_tooltip(self, event: NotableEvent) -> str:
        """Explain a marker.

        Args:
            event (NotableEvent): Its event.

        Returns:
            str: The rich text tooltip.
        """
        return self.marker_painter.tooltip(event, self.chronology, "Click to find it in the chronology.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_chronology(self, chronology: Chronology) -> None:
        """Draw a chronology.

        Args:
            chronology (Chronology): The segments, the reigns and the events.
        """
        self.chronology = chronology
        self.zoom.follow(chronology.as_of)
        self.setMinimumHeight(self._height())
        self.updateGeometry()
        self.update()
        self.logger.debug("Leadership chart: %d lanes, %d reigns.", len(chronology.segments), len(chronology.reigns))

    def set_events(self, events: List[NotableEvent]) -> None:
        """Draw events as markers.

        Args:
            events (List[NotableEvent]): The events picked.
        """
        self.events = list(events)
        self.update()
        self.logger.debug("Leadership chart: %d event markers.", len(self.events))

    def set_message(self, message: str) -> None:
        """Say why there is nothing to draw.

        Args:
            message (str): The message.
        """
        self.message = message
        self.chronology = None
        self.update()

    def highlight(self, key: Optional[str]) -> None:
        """Outline a band or thicken a marker.

        Args:
            key (Optional[str]): The key of the reign or event, `None` for none.
        """
        self.highlighted = key
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size: every lane (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(1000, self._height())

    def event(self, event: Optional[QEvent]) -> bool:
        """Explain the hovered marker or band (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            position = QPointF(event.pos())
            marker = self._marker_at(position)
            reign = self._band_at(position) if marker is None else None
            if marker is not None:
                QToolTip.showText(event.globalPos(), self._event_tooltip(marker), self)
            elif reign is not None:
                QToolTip.showText(event.globalPos(), self._reign_tooltip(reign), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:
        """Pick the clicked marker or band (Qt override).

        Args:
            event (Optional[QMouseEvent]): The event.
        """
        if event is not None and event.button() is Qt.MouseButton.LeftButton:
            position = event.position()
            marker = self._marker_at(position)
            reign = self._band_at(position) if marker is None else None
            key = f"event:{marker.key}" if marker is not None else reign.key() if reign is not None else None
            if key is not None:
                self.highlight(key)
                self.logger.debug("Leadership chart: %s picked.", key)
                self.picked.emit(key)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the lanes, the bands, the markers and the zoom band (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = self._frame()
        if frame is None:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                self.message,
            )
            painter.end()
            return
        self._paint_lanes(painter, frame)
        self._paint_bands(painter, frame)
        self._paint_markers(painter, frame)
        self.zoom.paint(painter)
        painter.end()
