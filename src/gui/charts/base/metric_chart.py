from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.charts.base.chart_legend import ChartLegend, LegendEntry
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.charts.common.axis.axis_formatter import AxisFormatter
from gui.charts.common.axis.nice_scale import NiceScale
from gui.charts.common.chart_labels import ChartLabels
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import MetricUnit
from models.trends.matrix.metric_matrix import MetricMatrix
from models.trends.metric_series import MetricSeries

ChartLine = Tuple[MetricSeries, str, QColor, Qt.PenStyle]


class MetricChart(QWidget):
    """Base of the hand-painted metric charts: layout, axes, legend, hover, and the loading, empty and error states.

    Attributes:
        LEFT (ClassVar[int]): The width left of the plot, for the y values and title, in pixels.
        TOP (ClassVar[int]): The margin above the plot, in pixels.
        BOTTOM (ClassVar[int]): The height below the plot, for the x values and title, in pixels.
        RIGHT (ClassVar[int]): The margin right of the plot, in pixels.
        LEGEND_WIDTH (ClassVar[int]): The width of the legend right of the plot, in pixels.
        NARROW (ClassVar[int]): The chart width below which the legend moves below the plot, in pixels.
        LABEL_SPACING (ClassVar[int]): The smallest distance between two x labels, in pixels.
        MIN_HEIGHT (ClassVar[int]): The smallest chart height: below it, the view scrolls, in pixels.
        COMPACT_HEIGHT (ClassVar[int]): The height of a compact chart (a small chart of a facet grid), in pixels.
        WIDE_PLOT_WIDTH (ClassVar[int]): The smallest width of the plot of a widened chart, in pixels.
        WIDE_POINT_SPACING (ClassVar[int]): The width given to each x value of a widened chart, in pixels.
        SPIN_MS (ClassVar[int]): The interval of the loading spinner, in milliseconds.
        SPIN_DELAY (ClassVar[int]): The number of spinner steps before the loading overlay shows (no flicker).
        theme (Theme): The application theme.
        labels (ChartLabels): The names and colours of the options and series.
        formatter (AxisFormatter): The value formatter.
        scale (NiceScale): The axis scale chooser.
        legend (ChartLegend): The legend.
        axes (Optional[ChartAxes]): The shown axes, `None` before the first data.
        lines (List[ChartLine]): The series, their label, colour and line style.
        breaks (List[float]): The x values of the methodology changes.
        last_actual (Optional[float]): The x value of the latest observation (the forecast starts after it).
        as_of (Optional[float]): The month ordinal of the bubbles.
        matrix (Optional[MetricMatrix]): The cells of a matrix chart.
        hidden (Set[str]): The legend labels hidden by a click.
        highlighted (Optional[str]): The legend label under the mouse.
        hover (Optional[QPointF]): The mouse position over the chart.
        plot_area (QRectF): The plot area of the latest paint, for the tooltips.
        wide (bool): Whether the chart is widened: every label in full, the chart scrolling sideways.
        compact (bool): Whether the chart is a small one without legend (a facet grid shows one legend for all).
        loading (bool): Whether new data is being read.
        message (str): Why there is no data (empty or failed), shown instead of the plot.
        spin (int): The step of the loading spinner.
        spin_timer (QTimer): Turns the loading spinner.
        zoom (ChartZoom): The zoom of the axes (Ctrl + wheel, pinch or dragged rectangle, reset by a double-click).
        logger (Logger): The chart logger.

    Notes:
        - The subclasses paint their plot (`_paint_plot`) and tell what is under the mouse (`_tooltip`).
        - A click on a legend entry hides or shows its series, hovering it highlights the series.
        - While loading, the previous chart stays visible, dimmed, under a spinner.
        - The chart is never shorter than its legend (or its rows): with many series the view scrolls rather than
          cutting them. Widened, it is also as wide as its labels need (`natural_width`).
        - Every chart zooms: the subclasses read their ranges through `zoom` and give it their frame back. The zoom
          is kept while new data arrives for the same axes, and reset for other axes.
    """

    LEFT: ClassVar[int] = 72
    TOP: ClassVar[int] = 14
    BOTTOM: ClassVar[int] = 46
    RIGHT: ClassVar[int] = 18
    LEGEND_WIDTH: ClassVar[int] = 210
    NARROW: ClassVar[int] = 640
    LABEL_SPACING: ClassVar[int] = 64
    MIN_HEIGHT: ClassVar[int] = 300
    COMPACT_HEIGHT: ClassVar[int] = 220
    WIDE_PLOT_WIDTH: ClassVar[int] = 960
    WIDE_POINT_SPACING: ClassVar[int] = 48
    SPIN_MS: ClassVar[int] = 80
    SPIN_DELAY: ClassVar[int] = 2

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty chart.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The chart logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.labels = ChartLabels(theme, self.logger)
        self.formatter = AxisFormatter(self.logger)
        self.scale = NiceScale(self.logger)
        self.legend = ChartLegend(theme)
        self.axes: Optional[ChartAxes] = None
        self.lines: List[ChartLine] = []
        self.breaks: List[float] = []
        self.last_actual: Optional[float] = None
        self.as_of: Optional[float] = None
        self.matrix: Optional[MetricMatrix] = None
        self.hidden: Set[str] = set()
        self.highlighted: Optional[str] = None
        self.hover: Optional[QPointF] = None
        self.plot_area = QRectF()
        self.wide = False
        self.compact = False
        self.loading = False
        self.message = ""
        self.spin = 0
        self.spin_timer = QTimer(self)
        self.spin_timer.setInterval(self.SPIN_MS)
        self.spin_timer.timeout.connect(self._on_spin)
        self.zoom = ChartZoom(self, logger=self.logger)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_spin(self) -> None:
        """Turn the loading spinner one step."""
        self.spin += 1
        self.update()

    def _legend_key(self, line: ChartLine) -> str:
        """Get the legend entry of a series, which hides or highlights it.

        Args:
            line (ChartLine): The series.

        Returns:
            str: Its legend label.
        """
        return line[1]

    def _visible(self) -> List[ChartLine]:
        """Get the series not hidden from the legend.

        Returns:
            List[ChartLine]: The visible series.
        """
        return [line for line in self.lines if self._legend_key(line) not in self.hidden]

    def _legend_entries(self) -> List[LegendEntry]:
        """Get the legend entries: one per series.

        Returns:
            List[LegendEntry]: The label, colour and line style of each entry.
        """
        entries: Dict[str, LegendEntry] = {}
        for line in self.lines:
            entries.setdefault(self._legend_key(line), (self._legend_key(line), line[2], line[3]))
        return list(entries.values())

    def _legend_suffixes(self) -> Dict[str, str]:
        """Get the forecast trend shown after the legend labels.

        Returns:
            Dict[str, str]: The annual trend of each extrapolated series, e.g. `+12%/yr`.
        """
        return {
            label: f"{series.trend_pct:+.0f}%/yr" for series, label, _, _ in self.lines if series.trend_pct is not None
        }

    def _has_data(self) -> bool:
        """Tell whether there is anything to plot.

        Returns:
            bool: Whether a series has a point.
        """
        return any(series.points for series, _, _, _ in self.lines)

    def _legend_width(self) -> int:
        """Get the width of the legend laid out right of the plot.

        Returns:
            int: `LEGEND_WIDTH`, or the width of the longest entry when the chart is widened, in pixels.
        """
        if not self.wide:
            return self.LEGEND_WIDTH
        metrics = self.fontMetrics()
        suffixes = self._legend_suffixes()
        widths = [
            metrics.horizontalAdvance(f"{label}  {suffixes[label]}" if label in suffixes else label)
            for label, _, _ in self._legend_entries()
        ]
        return max(self.LEGEND_WIDTH, max(widths, default=0) + ChartLegend.SAMPLE_WIDTH + 6 + 24)

    def _layout(self, painter: QPainter) -> Tuple[QRectF, QRectF, bool]:
        """Split the chart between the plot and the legend.

        Args:
            painter (QPainter): The painter, for the font metrics.

        Returns:
            Tuple[QRectF, QRectF, bool]: The plot area, the legend area and whether the legend is below the plot.
        """
        entries = self._legend_entries()
        width, height = float(self.width()), float(self.height())
        below = width < self.NARROW
        legend_width = self._legend_width()
        if not entries or self.compact:
            return (
                QRectF(self.LEFT, self.TOP, width - self.LEFT - self.RIGHT, height - self.TOP - self.BOTTOM),
                QRectF(),
                below,
            )
        if below:
            legend_height = self.legend.height_below(painter.fontMetrics(), entries, width - self.LEFT - self.RIGHT)
            plot = QRectF(
                self.LEFT, self.TOP, width - self.LEFT - self.RIGHT, height - self.TOP - self.BOTTOM - legend_height - 8
            )
            legend = QRectF(self.LEFT, height - legend_height - 4, width - self.LEFT - self.RIGHT, legend_height)
            return plot, legend, True
        plot = QRectF(
            self.LEFT,
            self.TOP,
            width - self.LEFT - self.RIGHT - legend_width,
            height - self.TOP - self.BOTTOM,
        )
        legend = QRectF(width - legend_width, self.TOP, legend_width - 8, height - self.TOP)
        return plot, legend, False

    def _faded(self, color: QColor, label: str, alpha: int = 255) -> QColor:
        """Fade a series colour when another series is highlighted.

        Args:
            color (QColor): The series colour.
            label (str): The legend label of the series.
            alpha (int): The opacity of the series when not faded, 0 to 255.

        Returns:
            QColor: The colour, mostly transparent when another series is highlighted.
        """
        faded = QColor(color)
        faded.setAlpha(min(alpha, 55) if self.highlighted and self.highlighted != label else alpha)
        return faded

    def _y_unit(self) -> MetricUnit:
        """Get the unit of the y values.

        Returns:
            MetricUnit: The unit of the transform, or of the y metric.
        """
        if self.axes is None:
            return MetricUnit.COUNT
        return self.axes.transform.unit or self.axes.y.unit

    def _currency(self) -> Optional[str]:
        """Get the currency of the shown amounts.

        Returns:
            Optional[str]: The currency, `None` without amounts or when they are in several currencies.
        """
        currencies = {series.currency for series, _, _, _ in self._visible() if series.currency}
        return currencies.pop() if len(currencies) == 1 else None

    def _zoomed_y(
        self, low: float, high: float, ticks: List[float], step: float
    ) -> Tuple[float, float, List[float], float]:
        """Get the shown y range and its grid values, zoomed or not.

        Args:
            low (float): The low bound of the full y range.
            high (float): The high bound of the full y range.
            ticks (List[float]): The grid values of the full range.
            step (float): The step between two grid values of the full range.

        Returns:
            Tuple[float, float, List[float], float]: The shown range, its grid values and their step (the full range
                and its grid when the y axis is not zoomed).
        """
        shown_low, shown_high = self.zoom.y_range(low, high)
        if (shown_low, shown_high) == (low, high):
            return low, high, ticks, step
        nice_low, nice_high, nice_step = self.scale.linear(shown_low, shown_high, include_zero=False)
        margin = nice_step * 1e-6
        inside = [
            value
            for value in self.scale.ticks(nice_low, nice_high, nice_step)
            if shown_low - margin <= value <= shown_high + margin
        ]
        return shown_low, shown_high, inside, nice_step

    def _paint_y_grid(
        self,
        painter: QPainter,
        frame: PlotFrame,
        ticks: List[float],
        unit: MetricUnit,
        step: Optional[float],
    ) -> None:
        """Paint the horizontal grid lines and the y values.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
            ticks (List[float]): The y values of the grid lines.
            unit (MetricUnit): The unit of the y values.
            step (Optional[float]): The step between two grid lines, to choose the decimals.
        """
        currency = self._currency()
        for value in ticks:
            y = frame.map_y(value)
            painter.setPen(QPen(QColor(self.theme.BORDER), 1))
            painter.drawLine(QPointF(frame.area.left(), y), QPointF(frame.area.right(), y))
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            text = self.formatter.value(unit, value, currency, step)
            box = QRectF(frame.area.left() - self.LEFT + 18, y - 8, self.LEFT - 24, 16)
            painter.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_x_values(
        self, painter: QPainter, frame: PlotFrame, values: List[Tuple[float, str]], grid: bool = False
    ) -> None:
        """Paint the x values below the plot, the last one always, the others skipped when too close.

        Args:
            painter (QPainter): The painter.
            frame (PlotFrame): The plot frame.
            values (List[Tuple[float, str]]): The x values and their labels.
            grid (bool): Whether a vertical grid line is drawn at each painted value.
        """
        last_x: Optional[float] = None
        for value, text in sorted(values, reverse=True):
            x = frame.map_x(value)
            if not frame.area.left() - 1 <= x <= frame.area.right() + 1:
                continue
            if last_x is not None and last_x - x < self.LABEL_SPACING:
                continue
            if grid:
                painter.setPen(QPen(QColor(self.theme.BORDER), 1))
                painter.drawLine(QPointF(x, frame.area.top()), QPointF(x, frame.area.bottom()))
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            box = QRectF(x - 40, frame.area.bottom() + 4, 80, 16)
            painter.drawText(box, Qt.AlignmentFlag.AlignHCenter, text)
            last_x = x

    def _paint_titles(self, painter: QPainter, plot: QRectF, x_title: str, y_title: str) -> None:
        """Paint the axis titles: below the x values and vertically left of the y values.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
            x_title (str): The title of the x axis, empty for none.
            y_title (str): The title of the y axis, empty for none.
        """
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        if x_title:
            painter.drawText(
                QRectF(plot.left(), plot.bottom() + 24, plot.width(), 16), Qt.AlignmentFlag.AlignHCenter, x_title
            )
        if y_title:
            painter.save()
            painter.translate(plot.left() - self.LEFT + 4, plot.center().y())
            painter.rotate(-90)
            elided = painter.fontMetrics().elidedText(y_title, Qt.TextElideMode.ElideRight, int(plot.height()))
            painter.drawText(QRectF(-plot.height() / 2, 0, plot.height(), 14), Qt.AlignmentFlag.AlignHCenter, elided)
            painter.restore()
        font.setPixelSize(13)
        painter.setFont(font)

    def _paint_plot(self, painter: QPainter, plot: QRectF) -> None:
        """Paint the plot: overridden by each chart.

        Args:
            painter (QPainter): The painter.
            plot (QRectF): The plot area.
        """
        self.logger.debug("No plot painted in %.0fx%.0f.", plot.width(), plot.height())

    def _tooltip(self, position: QPointF) -> Optional[str]:
        """Describe what is under the mouse: overridden by each chart.

        Args:
            position (QPointF): The mouse position.

        Returns:
            Optional[str]: The tooltip text, `None` for no tooltip.
        """
        return None

    def _paint_message(self, painter: QPainter) -> None:
        """Paint why there is no data, at the top of the chart.

        Args:
            painter (QPainter): The painter.
        """
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        text = self.message or "No data for these axes and filters."
        box = QRectF(self.rect()).adjusted(24, 24, -24, 0)
        painter.drawText(
            box, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, text
        )

    def _paint_loading(self, painter: QPainter) -> None:
        """Dim the chart and paint the loading spinner, once loading lasts.

        Args:
            painter (QPainter): The painter.
        """
        if self.spin < self.SPIN_DELAY:
            return
        veil = QColor(self.theme.SURFACE)
        veil.setAlpha(150)
        painter.fillRect(self.rect(), veil)
        center = QPointF(self.rect().center().x(), min(self.rect().center().y(), 72.0))
        painter.setPen(QPen(QColor(self.theme.ACCENT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        arc = QRectF(center.x() - 12, center.y() - 30, 24, 24)
        painter.drawArc(arc, -(self.spin * 30 % 360) * 16, 270 * 16)
        painter.setPen(QColor(self.theme.TEXT))
        painter.drawText(QRectF(center.x() - 80, center.y(), 160, 20), Qt.AlignmentFlag.AlignHCenter, "Loading…")

    ############################
    # Publicly Exposed Methods #
    ############################

    def needed_height(self) -> int:
        """Get the height fitting the legend right of the plot.

        Returns:
            int: The height, in pixels, at least `MIN_HEIGHT`.
        """
        if self.compact:
            return self.COMPACT_HEIGHT
        entries = len(self._legend_entries()) if self._has_data() else 0
        return max(self.MIN_HEIGHT, self.TOP + entries * ChartLegend.ROW_HEIGHT + 12)

    def natural_width(self) -> int:
        """Get the width of the widened chart: every x value spaced out and the legend in full.

        Returns:
            int: The width, in pixels.
        """
        points = max((len(series.points) for series, _, _, _ in self.lines), default=0)
        plot = max(self.WIDE_PLOT_WIDTH, points * self.WIDE_POINT_SPACING)
        return self.LEFT + plot + self.RIGHT + self._legend_width()

    def fit(self) -> None:
        """Set the smallest size of the chart: the height of its legend (or rows), its natural width once widened."""
        self.setMinimumHeight(self.needed_height())
        self.setMinimumWidth(self.natural_width() if self.wide and self._has_data() else 0)

    def set_wide(self, wide: bool) -> None:
        """Widen the chart (every label in full, scrolling sideways), or fit it to the view again.

        Args:
            wide (bool): Whether the chart is widened.
        """
        self.wide = wide
        self.logger.debug("Chart %s.", "widened" if wide else "fitted to the view")
        self.fit()
        self.update()

    def set_compact(self, compact: bool) -> None:
        """Make the chart a small one without legend (in a facet grid), or a full one again.

        Args:
            compact (bool): Whether the chart is compact.
        """
        self.compact = compact
        self.logger.debug("Chart %s.", "made compact" if compact else "shown in full")
        self.fit()
        self.update()

    def set_loading(self, loading: bool) -> None:
        """Show (or stop showing) that new data is being read.

        Args:
            loading (bool): Whether data is being read.
        """
        self.logger.debug("Chart %s.", "loading" if loading else "no longer loading")
        self.loading = loading
        self.spin = 0
        if loading:
            self.spin_timer.start()
        else:
            self.spin_timer.stop()
        self.update()

    def set_lines(
        self,
        axes: ChartAxes,
        lines: List[ChartLine],
        breaks: Optional[List[float]] = None,
        last_actual: Optional[float] = None,
        as_of: Optional[float] = None,
    ) -> None:
        """Show new series.

        Args:
            axes (ChartAxes): The chart axes.
            lines (List[ChartLine]): The series, their label, colour and line style.
            breaks (Optional[List[float]]): The x values of the methodology changes.
            last_actual (Optional[float]): The x value of the latest observation.
            as_of (Optional[float]): The month ordinal of the bubbles.
        """
        self.logger.debug(
            "Chart showing %d series of %s by %s, %d methodology breaks.",
            len(lines),
            axes.y.value,
            axes.series_by.value,
            len(breaks or []),
        )
        self.zoom.follow(axes.model_dump_json())
        self.axes, self.lines, self.matrix = axes, lines, None
        self.breaks, self.last_actual, self.as_of = breaks or [], last_actual, as_of
        self.hidden &= {self._legend_key(line) for line in lines}
        self.message = ""
        self.set_loading(False)
        self.fit()

    def set_matrix(self, axes: ChartAxes, matrix: MetricMatrix) -> None:
        """Show new matrix cells.

        Args:
            axes (ChartAxes): The chart axes.
            matrix (MetricMatrix): The cells.
        """
        self.logger.debug(
            "Chart showing %d rows by %d columns of %s.", len(matrix.rows), len(matrix.columns), axes.cell.value
        )
        self.zoom.follow(axes.model_dump_json())
        self.axes, self.matrix, self.lines = axes, matrix, []
        self.message = ""
        self.set_loading(False)
        self.fit()

    def set_message(self, message: str) -> None:
        """Show why there is no data, instead of the plot.

        Args:
            message (str): The explanation, e.g. what to crawl first or the storage error.
        """
        self.logger.debug("Chart showing no data: %s", message)
        self.message = message
        self.lines, self.matrix = [], None
        self.set_loading(False)
        self.fit()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override).

        Returns:
            QSize: The preferred size.
        """
        return QSize(760, 340)

    def event(self, event: Optional[QEvent]) -> bool:
        """Follow the mouse: tooltips, highlighted series and legend clicks (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if isinstance(event, QHelpEvent):
            text = self._tooltip(QPointF(event.pos()))
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        if isinstance(event, QMouseEvent) and event.type() == QEvent.Type.MouseMove:
            self.hover = event.position()
            self.highlighted = self.legend.hit(self.hover)
            self.setCursor(Qt.CursorShape.PointingHandCursor if self.highlighted else Qt.CursorShape.ArrowCursor)
            self.update()
        elif isinstance(event, QMouseEvent) and event.type() == QEvent.Type.MouseButtonRelease:
            label = self.legend.hit(event.position())
            if label is not None and event.button() == Qt.MouseButton.LeftButton:
                self.hidden ^= {label}
                self.logger.debug("Series %r %s.", label, "hidden" if label in self.hidden else "shown")
                self.update()
                return True
        elif event is not None and event.type() == QEvent.Type.Leave:
            self.hover, self.highlighted = None, None
            self.update()
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the plot and the legend, or why there is none, and the loading state (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._has_data():
            plot, legend, below = self._layout(painter)
            self.plot_area = plot
            if plot.width() > 20 and plot.height() > 20:
                self._paint_plot(painter, plot)
                self.zoom.paint(painter)
            entries = self._legend_entries()
            if entries and not legend.isEmpty():
                self.legend.paint(
                    painter, legend, entries, self.hidden, self.highlighted, below, self._legend_suffixes()
                )
        elif not self.loading:
            self._paint_message(painter)
        if self.loading:
            self._paint_loading(painter)
        painter.end()
