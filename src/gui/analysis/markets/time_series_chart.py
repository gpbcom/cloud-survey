from __future__ import annotations

# Standard Library Imports.
import html
import itertools
import math
import statistics
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.analysis.events.event_markers import EventMarkers
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme
from models.history.chronology import Chronology
from models.history.timeline.notable_event import NotableEvent
from models.markets.charts.chart_dot import ChartDot
from models.markets.charts.chart_line import ChartLine


class TimeSeriesChart(QWidget):
    """A time chart of the markets cards: a line per company or listing, dots for lone values, dashed event markers.

    Attributes:
        AXIS_WIDTH (ClassVar[int]): The width of the value axis, left of the plot.
        STRIP_ROW (ClassVar[int]): The height of a row of event labels, above the legend.
        STRIP_ROWS (ClassVar[int]): The rows of event labels.
        LEGEND_ROW (ClassVar[int]): The height of a row of the legend.
        AXIS_HEIGHT (ClassVar[int]): The height of the year axis, below the plot.
        RIGHT (ClassVar[int]): The margin right of the plot.
        PLOT_HEIGHT (ClassVar[int]): The preferred height of the plot.
        TICK_SPACING (ClassVar[int]): The fewest pixels between two year ticks.
        YEAR_STEPS (ClassVar[Tuple[int, ...]]): The year steps the axis chooses from.
        DOT_REACH (ClassVar[float]): How close, in pixels, the mouse must be to a dot to hover it.
        GAP_FACTOR (ClassVar[float]): How many times the usual spacing two points of a line may be apart and still be
            joined.
        GAP_FLOOR_DAYS (ClassVar[int]): The fewest days between two points that may break a line.
        theme (Theme): The application theme.
        lines (List[ChartLine]): The lines drawn.
        dots (List[ChartDot]): The lone values drawn.
        hidden (Set[str]): The keys of the lines hidden by a click on their legend entry.
        unit (str): The unit printed after the values, e.g. `%` or `USD`.
        log_y (bool): Whether the value axis is logarithmic.
        floor_zero (bool): Whether the value axis starts at zero (the shares).
        events (List[NotableEvent]): The events drawn as markers.
        chronology (Optional[Chronology]): Names the companies of the events in their tooltips.
        message (str): What the chart says when it has nothing to draw.
        legend (List[Tuple[QRectF, str]]): The legend entries of the last paint, for the mouse.
        dot_hits (List[Tuple[QPointF, ChartDot]]): The dots of the last paint, for the mouse.
        markers (EventMarkers): Paints the event markers (shared with the leaders chart).
        zoom (ChartZoom): Zooms the years (drag, Ctrl+wheel), reset by a double-click or Escape.
        logger (Logger): The chart logger.

    Notes:
        The x axis is in fractional years, as the leaders chart, so the event markers sit on the same dates. Hovering
        the plot lists the value of every line at that date, hovering a dot explains it, clicking a legend entry
        hides or shows its line.
        - A line breaks where two of its points are much further apart than usual (no release for years, a
          listing suspended): a straight segment there would draw values nobody measured.
    """

    AXIS_WIDTH: ClassVar[int] = 72
    STRIP_ROW: ClassVar[int] = 16
    STRIP_ROWS: ClassVar[int] = 2
    LEGEND_ROW: ClassVar[int] = 20
    AXIS_HEIGHT: ClassVar[int] = 24
    RIGHT: ClassVar[int] = 16
    PLOT_HEIGHT: ClassVar[int] = 300
    TICK_SPACING: ClassVar[int] = 56
    YEAR_STEPS: ClassVar[Tuple[int, ...]] = (1, 2, 5, 10, 20)
    DOT_REACH: ClassVar[float] = 7.0
    GAP_FACTOR: ClassVar[float] = 2.5
    GAP_FLOOR_DAYS: ClassVar[int] = 45

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.lines: List[ChartLine] = []
        self.dots: List[ChartDot] = []
        self.hidden: Set[str] = set()
        self.unit = ""
        self.log_y = False
        self.floor_zero = True
        self.events: List[NotableEvent] = []
        self.chronology: Optional[Chronology] = None
        self.message = "Loading..."
        self.legend: List[Tuple[QRectF, str]] = []
        self.dot_hits: List[Tuple[QPointF, ChartDot]] = []
        self.markers = EventMarkers(theme, self.logger)
        self.zoom = ChartZoom(self, zoom_y=False, logger=self.logger)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(self.PLOT_HEIGHT)

    ############################
    # Internal Helpers Methods #
    ############################

    def _year(self, day: date) -> float:
        """Place a day on the time axis.

        Args:
            day (date): The day.

        Returns:
            float: The fractional year, e.g. 2016.5 for early July 2016.
        """
        start = date(day.year, 1, 1)
        length = (date(day.year + 1, 1, 1) - start).days
        return day.year + (day - start).days / length

    def _gap_days(self) -> float:
        """Get how far apart two points of a line may be and still be joined.

        Returns:
            float: The days, `GAP_FACTOR` times the median spacing of the points of every line, `GAP_FLOOR_DAYS` at
                least.

        Notes:
            The spacing is measured over every line, so that it is the period of the segment (a month, a quarter, a
            year): a company named in a few releases only has few points, and its own spacing would be years.
        """
        spacings = [(b[0] - a[0]).days for line in self.lines for a, b in itertools.pairwise(line.points)]
        usual = statistics.median(spacings) if spacings else 0
        return max(self.GAP_FLOOR_DAYS, self.GAP_FACTOR * usual)

    def _shown(self) -> List[ChartLine]:
        """Get the lines not hidden.

        Returns:
            List[ChartLine]: The lines drawn.
        """
        return [line for line in self.lines if line.key not in self.hidden]

    def _legend_layout(self) -> List[Tuple[QRectF, ChartLine]]:
        """Lay the legend entries out in rows, below the event strip.

        Returns:
            List[Tuple[QRectF, ChartLine]]: The box of each line's entry.
        """
        metrics = self.fontMetrics()
        top = self.STRIP_ROW * self.STRIP_ROWS + 6
        x, y = float(self.AXIS_WIDTH), float(top)
        boxes: List[Tuple[QRectF, ChartLine]] = []
        for line in self.lines:
            width = metrics.horizontalAdvance(line.label) + 26
            if x + width > self.width() - self.RIGHT and x > self.AXIS_WIDTH:
                x, y = float(self.AXIS_WIDTH), y + self.LEGEND_ROW
            boxes.append((QRectF(x, y, width, self.LEGEND_ROW - 2), line))
            x += width + 8
        return boxes

    def _plot(self) -> QRectF:
        """Get the plot area: below the event strip and the legend, above the year axis.

        Returns:
            QRectF: The plot area.
        """
        boxes = self._legend_layout()
        legend_bottom = boxes[-1][0].bottom() if boxes else float(self.STRIP_ROW * self.STRIP_ROWS)
        top = legend_bottom + 8
        width = max(self.width() - self.AXIS_WIDTH - self.RIGHT, 80)
        height = max(self.height() - top - self.AXIS_HEIGHT, 60)
        return QRectF(self.AXIS_WIDTH, top, width, height)

    def _x_full(self) -> Optional[Tuple[float, float]]:
        """Get the years every line and dot spans.

        Returns:
            Optional[Tuple[float, float]]: The first and last fractional years, `None` without data.
        """
        years = [self._year(day) for line in self._shown() for day, _ in line.points[:1] + line.points[-1:]]
        years += [self._year(dot.day) for dot in self.dots]
        if not years:
            return None
        low, high = min(years), max(years)
        return (low - 0.25, high + 0.25) if high - low > 0.5 else (low - 1.0, high + 1.0)

    def _y_range(self, x_low: float, x_high: float) -> Tuple[float, float]:
        """Get the values shown in the years of the window.

        Args:
            x_low (float): The first year shown.
            x_high (float): The last year shown.

        Returns:
            Tuple[float, float]: The lowest and highest values of the axis, padded.
        """
        values = [
            value
            for line in self._shown()
            for day, value in line.points
            if x_low <= self._year(day) <= x_high and (value > 0 or not self.log_y)
        ]
        values += [dot.value for dot in self.dots if x_low <= self._year(dot.day) <= x_high]
        if not values:
            return (1.0, 10.0) if self.log_y else (0.0, 1.0)
        low, high = min(values), max(values)
        if self.log_y:
            return low / 1.25, high * 1.25
        if self.floor_zero:
            low = min(0.0, low)
        pad = (high - low) * 0.06 or abs(high) * 0.1 or 1.0
        return (low if self.floor_zero else low - pad), high + pad

    def _frame(self) -> Optional[PlotFrame]:
        """Map the years and values shown to the pixels, through the zoom.

        Returns:
            Optional[PlotFrame]: The frame, `None` without data.
        """
        full = self._x_full()
        if full is None:
            return None
        x_range = self.zoom.x_range(*full)
        frame = PlotFrame(self._plot(), x_range, self._y_range(*x_range), log_y=self.log_y)
        self.zoom.set_frame(frame, full, None)
        return frame

    def _y_ticks(self, frame: PlotFrame) -> List[float]:
        """Choose the ticks of the value axis.

        Args:
            frame (PlotFrame): The frame.

        Returns:
            List[float]: Round values within the axis: 1, 2 and 5 times the powers of ten.
        """
        low, high = frame.y_low, frame.y_high
        if self.log_y:
            ticks = [
                mantissa * 10.0**power
                for power in range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1)
                for mantissa in (1, 2, 5)
            ]
            shown = [tick for tick in ticks if low <= tick <= high]
            return shown if len(shown) <= 9 else [tick for tick in shown if math.log10(tick).is_integer()]
        raw = (high - low) / 5 or 1.0
        power = 10.0 ** math.floor(math.log10(raw))
        step = next((mantissa * power for mantissa in (1, 2, 5, 10) if mantissa * power >= raw), 10 * power)
        first = math.ceil(low / step) * step
        return [first + index * step for index in range(int((high - first) / step) + 1)]

    def _format(self, value: float) -> str:
        """Print a value with the unit of the chart.

        Args:
            value (float): The value.

        Returns:
            str: The value, rounded for its size, with its unit.
        """
        size = abs(value)
        text = (
            f"{value:,.0f}"
            if size >= 1000
            else f"{value:.1f}"
            if size >= 10
            else f"{value:.2f}"
            if size >= 0.1
            else f"{value:.3g}"
        )
        return f"{text}%" if self.unit == "%" else f"{text} {self.unit}".strip()

    def _paint_axes(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the grid, the value axis and the year axis.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        plot = frame.area
        painter.fillRect(plot, QColor(self.theme.SURFACE))
        for tick in self._y_ticks(frame):
            y = frame.map_y(tick)
            painter.setPen(QPen(QColor(self.theme.BORDER), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(0, y - 9, self.AXIS_WIDTH - 6, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._format(tick),
            )
        per_year = plot.width() / max(frame.x_high - frame.x_low, 1e-9)
        step = next((step for step in self.YEAR_STEPS if step * per_year >= self.TICK_SPACING), self.YEAR_STEPS[-1])
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

    def _paint_lines(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the lines, broken where the points are far apart, and the dots of the lines drawn point by point.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        painter.save()
        painter.setClipRect(frame.area)
        gap = self._gap_days()
        for line in self._shown():
            color = QColor(line.color)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.DashLine if line.dashed else Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            started = False
            previous: Optional[date] = None
            for day, value in line.points:
                if self.log_y and value <= 0:
                    started = False
                    continue
                point = frame.map(self._year(day), value)
                if previous is not None and (day - previous).days > gap:
                    started = False
                previous = day
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
            painter.drawPath(path)
            if line.dots:
                painter.setBrush(color)
                for day, value in line.points:
                    if value > 0 or not self.log_y:
                        painter.drawEllipse(frame.map(self._year(day), value), 3.0, 3.0)
        painter.restore()

    def _paint_dots(self, painter: QPainter, frame: PlotFrame) -> None:
        """Paint the lone values, outlined, and remember them for the mouse.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The frame.
        """
        self.dot_hits = []
        painter.save()
        painter.setClipRect(frame.area.adjusted(-6, -6, 6, 6))
        for dot in self.dots:
            year = self._year(dot.day)
            if not frame.x_low <= year <= frame.x_high:
                continue
            center = frame.map(year, dot.value)
            painter.setPen(QPen(QColor(self.theme.TEXT), 1.2))
            painter.setBrush(QColor(dot.color))
            painter.drawEllipse(center, 5.0, 5.0)
            self.dot_hits.append((center, dot))
        painter.restore()

    def _paint_legend(self, painter: QPainter) -> None:
        """Paint the legend, a hidden line's entry faded, and remember the entries for the mouse.

        Args:
            painter (QPainter): The painter.
        """
        self.legend = []
        for box, line in self._legend_layout():
            hidden = line.key in self.hidden
            color = QColor(line.color)
            if hidden:
                color.setAlpha(70)
            swatch = QRectF(box.left() + 2, box.center().y() - 1.5, 14, 3)
            painter.fillRect(swatch, color)
            painter.setPen(QColor(self.theme.TEXT_MUTED if hidden else self.theme.TEXT))
            painter.drawText(box.adjusted(20, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, line.label)
            self.legend.append((box, line.key))

    def _nearest(self, line: ChartLine, year: float) -> Optional[Tuple[date, float]]:
        """Find the point of a line nearest a year.

        Args:
            line (ChartLine): The line.
            year (float): The year.

        Returns:
            Optional[Tuple[date, float]]: The nearest point, `None` for an empty line.
        """
        return min(line.points, key=lambda point: abs(self._year(point[0]) - year), default=None)

    def _hover_text(self, position: QPointF) -> Optional[str]:
        """Explain what is under the mouse: a dot, a marker, or the values of the lines at that date.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The rich text tooltip, `None` over nothing.
        """
        plot = self._plot()
        for center, dot in self.dot_hits:
            if math.hypot(center.x() - position.x(), center.y() - position.y()) <= self.DOT_REACH:
                return f"<qt><b style='color:{dot.color}'>{html.escape(dot.label)}</b><br>{dot.tooltip}</qt>"
        event = self.markers.at(position, plot.top() - self.STRIP_ROW)
        if event is not None:
            return self.markers.tooltip(event, self.chronology)
        frame = self.zoom.frame
        if frame is None or not plot.contains(position):
            return None
        year = frame.value_x(position.x())
        reach = (frame.x_high - frame.x_low) * 0.02
        rows: List[Tuple[float, str]] = []
        for line in self._shown():
            point = self._nearest(line, year)
            if point is None or abs(self._year(point[0]) - year) > max(reach, 0.1):
                continue
            note = f" <span style='color:{self.theme.TEXT_MUTED}'>{html.escape(line.note)}</span>" if line.note else ""
            rows.append(
                (
                    point[1],
                    f"<span style='color:{line.color}'>■</span> {html.escape(line.label)}: "
                    f"<b>{self._format(point[1])}</b> ({point[0].isoformat()[:7]}){note}",
                )
            )
        if not rows:
            return None
        rows.sort(key=lambda row: row[0], reverse=True)
        return "<qt>" + "<br>".join(text for _, text in rows) + "</qt>"

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_data(
        self,
        lines: Sequence[ChartLine],
        dots: Sequence[ChartDot],
        unit: str,
        log_y: bool,
        floor_zero: bool,
        key: str,
    ) -> None:
        """Draw lines and dots.

        Args:
            lines (Sequence[ChartLine]): The lines.
            dots (Sequence[ChartDot]): The lone values.
            unit (str): The unit printed after the values.
            log_y (bool): Whether the value axis is logarithmic.
            floor_zero (bool): Whether the value axis starts at zero.
            key (str): What the chart shows: the zoom is kept while it stays the same.
        """
        self.lines, self.dots = list(lines), list(dots)
        self.unit, self.log_y, self.floor_zero = unit, log_y, floor_zero
        self.hidden &= {line.key for line in self.lines}
        self.zoom.follow(key)
        self.message = "" if self.lines or self.dots else self.message
        self.update()
        self.logger.debug("Time chart %s: %d lines, %d dots.", key, len(self.lines), len(self.dots))

    def set_events(self, events: Sequence[NotableEvent], chronology: Optional[Chronology]) -> None:
        """Draw events as markers.

        Args:
            events (Sequence[NotableEvent]): The events picked.
            chronology (Optional[Chronology]): Names their companies in the tooltips.
        """
        self.events, self.chronology = list(events), chronology
        self.update()

    def set_message(self, message: str) -> None:
        """Say why there is nothing to draw.

        Args:
            message (str): The message.
        """
        self.message = message
        self.lines, self.dots = [], []
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(1000, self.PLOT_HEIGHT + 120)

    def event(self, event: Optional[QEvent]) -> bool:
        """Explain what is hovered (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            text = self._hover_text(QPointF(event.pos()))
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:
        """Hide or show the line of a clicked legend entry (Qt override).

        Args:
            event (Optional[QMouseEvent]): The event.
        """
        if event is not None and event.button() is Qt.MouseButton.LeftButton:
            key = next((key for box, key in self.legend if box.contains(event.position())), None)
            if key is not None:
                self.hidden ^= {key}
                self.logger.debug("Time chart line %s %s.", key, "hidden" if key in self.hidden else "shown")
                self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the axes, the lines, the dots, the markers, the legend and the zoom band (Qt override).

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
        self._paint_axes(painter, frame)
        self._paint_lines(painter, frame)
        self._paint_dots(painter, frame)
        self.markers.paint(
            painter,
            frame,
            self.events,
            (2.0, self.STRIP_ROWS, self.STRIP_ROW),
            (frame.area.left() - self.AXIS_WIDTH + 4, self.width() - 2),
        )
        self._paint_legend(painter)
        self.zoom.paint(painter)
        painter.end()
