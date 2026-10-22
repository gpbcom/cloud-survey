from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QNativeGestureEvent, QPainter, QPen, QWheelEvent  # noqa: E501
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.charts.base.plot_frame import PlotFrame

Range = Tuple[float, float]


class ChartZoom(QObject):
    """The zoom of a chart: the windows of its axes shown instead of their full ranges, set with the mouse.

    Attributes:
        ZOOM_IN (ClassVar[float]): The share of the shown span kept by one wheel step in.
        MIN_SPAN (ClassVar[float]): The smallest window, as a share of the full range.
        DRAG_PIXELS (ClassVar[int]): The distance the mouse must travel for a drag to draw a zoom rectangle.
        PAN_STEP (ClassVar[float]): The share of the shown span one wheel step scrolls a zoomed chart by.
        HINT (ClassVar[str]): The hint painted while the chart is zoomed.
        BAND_COLOR (ClassVar[str]): The colour of the zoom rectangle.
        changed (pyqtSignal): Emitted when a window changes, the chart then paints itself again.
        x_window_changed (pyqtSignal): Emitted with the new x window (`None` for the full range) when the user
            changes it, to zoom charts sharing the x axis together.
        target (QWidget): The zoomed chart.
        zoom_x (bool): Whether the x axis can be zoomed.
        zoom_y (bool): Whether the y axis can be zoomed.
        wheel_y (bool): Whether the wheel zooms the y axis too (both axes of a scatter or a matrix), only the x axis
            of a time chart otherwise (Shift for the y axis).
        anchor_low (bool): Whether the windows start at the low bound of the full range (bars growing from zero).
        frame (Optional[PlotFrame]): The plot frame of the latest paint, mapping the values to the pixels.
        full_x (Optional[Range]): The full x range of the latest paint.
        full_y (Optional[Range]): The full y range of the latest paint.
        x_window (Optional[Range]): The shown x window, `None` for the full range.
        y_window (Optional[Range]): The shown y window, `None` for the full range.
        band_start (Optional[QPointF]): Where the zoom rectangle started, `None` while not dragging.
        band_end (Optional[QPointF]): Where the zoom rectangle ends.
        pan_from (Optional[QPointF]): Where the middle-button drag scrolling the zoomed chart was last, `None` while
            not dragging.
        key (Optional[str]): What the chart shows (its axes): another one resets the zoom.
        logger (Logger): The zoom logger.

    Notes:
        - Ctrl + wheel (or a pinch) zooms around the mouse, Ctrl + Shift + wheel the y axis only, and a drag draws the
          rectangle zoomed into. A double-click or Escape shows the full ranges again.
        - A zoomed chart scrolls within its full ranges: the wheel (Shift + wheel or a sideways swipe for the other
          axis) or a middle-button drag. The wheel over a chart which is not zoomed scrolls the page.
        - The charts read their ranges through `x_range` and `y_range` and give their frame back with `set_frame`
          at each paint. A window is kept within the full range, which may change with new data.
    """

    ZOOM_IN: ClassVar[float] = 0.8
    MIN_SPAN: ClassVar[float] = 0.01
    DRAG_PIXELS: ClassVar[int] = 6
    PAN_STEP: ClassVar[float] = 0.1
    HINT: ClassVar[str] = "Zoomed · wheel to scroll · double-click or Esc to reset"
    BAND_COLOR: ClassVar[str] = "#5B8DEF"

    changed = pyqtSignal()
    x_window_changed = pyqtSignal(object)

    def __init__(
        self,
        target: QWidget,
        zoom_x: bool = True,
        zoom_y: bool = True,
        wheel_y: bool = False,
        anchor_low: bool = False,
        logger: Optional[Logger] = None,
    ) -> None:
        """Watch the mouse over a chart.

        Args:
            target (QWidget): The chart.
            zoom_x (bool): Whether the x axis can be zoomed.
            zoom_y (bool): Whether the y axis can be zoomed.
            wheel_y (bool): Whether the wheel zooms the y axis too.
            anchor_low (bool): Whether the windows start at the low bound of the full range.
            logger (Optional[Logger]): The zoom logger.
        """
        super().__init__(target)
        self.logger = logger if logger else getLogger(__name__)
        self.target = target
        self.zoom_x, self.zoom_y, self.wheel_y, self.anchor_low = zoom_x, zoom_y, wheel_y, anchor_low  # noqa: E501
        self.frame: Optional[PlotFrame] = None
        self.full_x: Optional[Range] = None
        self.full_y: Optional[Range] = None
        self.x_window: Optional[Range] = None
        self.y_window: Optional[Range] = None
        self.band_start: Optional[QPointF] = None
        self.band_end: Optional[QPointF] = None
        self.pan_from: Optional[QPointF] = None
        self.key: Optional[str] = None
        if target.focusPolicy() == Qt.FocusPolicy.NoFocus:
            target.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        target.installEventFilter(self)
        self.changed.connect(target.update)

    ############################
    # Internal Helpers Methods #
    ############################

    def _scale(self, value: float, log: bool) -> float:
        """Get where a value lies on its axis scale.

        Args:
            value (float): The value.
            log (bool): Whether the axis is logarithmic.

        Returns:
            float: The value, or its logarithm.
        """
        return math.log10(max(value, 1e-12)) if log else value

    def _unscale(self, value: float, log: bool) -> float:
        """Get the value at a place of its axis scale (the inverse of `_scale`).

        Args:
            value (float): The place on the scale.
            log (bool): Whether the axis is logarithmic.

        Returns:
            float: The value.
        """
        return float(10**value) if log else value

    def _clamp(self, window: Range, full: Range, log: bool) -> Optional[Range]:
        """Keep a window within the full range, no narrower than `MIN_SPAN` of it.

        Args:
            window (Range): The wished window.
            full (Range): The full range.
            log (bool): Whether the axis is logarithmic.

        Returns:
            Optional[Range]: The window, `None` when it covers the full range.
        """
        full_low, full_high = (self._scale(value, log) for value in sorted(full))
        low, high = (self._scale(value, log) for value in sorted(window))
        full_span = full_high - full_low
        if full_span <= 0:
            return None
        start = full_low if self.anchor_low else low
        span = min(max(high - start, full_span * self.MIN_SPAN), full_span)
        low = full_low if self.anchor_low else min(max((low + high - span) / 2, full_low), full_high - span)
        high = low + span
        if span >= full_span * (1 - 1e-9):
            return None
        return self._unscale(low, log), self._unscale(high, log)

    def _scaled(self, window: Range, center: float, factor: float, log: bool) -> Range:
        """Scale a window around a value.

        Args:
            window (Range): The shown window.
            center (float): The value staying under the mouse.
            factor (float): The share of the span kept (below 1 zooms in).
            log (bool): Whether the axis is logarithmic.

        Returns:
            Range: The scaled window (not clamped yet).
        """
        low, high = (self._scale(value, log) for value in window)
        middle = self._scale(center, log)
        return (
            self._unscale(middle - (middle - low) * factor, log),
            self._unscale(middle + (high - middle) * factor, log),
        )

    def _in_plot(self, position: QPointF) -> bool:
        """Tell whether the mouse is over the plot.

        Args:
            position (QPointF): The mouse position.

        Returns:
            bool: Whether it is inside the plot area of the latest paint.
        """
        return self.frame is not None and self.frame.area.contains(position)

    def _zoomed(self) -> bool:
        """Tell whether an axis is zoomed.

        Returns:
            bool: Whether a window is shown instead of a full range.
        """
        return self.x_window is not None or self.y_window is not None

    def _zoom_at(self, position: QPointF, factor: float, x: bool, y: bool) -> None:  # noqa: E501
        """Zoom the axes around the value under the mouse.

        Args:
            position (QPointF): The mouse position.
            factor (float): The share of the span kept (below 1 zooms in).
            x (bool): Whether the x axis is zoomed.
            y (bool): Whether the y axis is zoomed.
        """
        frame = self.frame
        if frame is None:
            return
        if x and self.zoom_x and self.full_x is not None:
            shown = self.x_window or self.full_x
            wished = self._scaled(shown, frame.value_x(position.x()), factor, frame.log_x)  # noqa: E501
            self.x_window = self._clamp(wished, self.full_x, frame.log_x)
            self.x_window_changed.emit(self.x_window)
        if y and self.zoom_y and self.full_y is not None:
            shown = self.y_window or self.full_y
            wished = self._scaled(shown, frame.value_y(position.y()), factor, frame.log_y)  # noqa: E501
            self.y_window = self._clamp(wished, self.full_y, frame.log_y)
        self.logger.debug("Chart zoomed (factor %.2f): x %s, y %s.", factor, self.x_window, self.y_window)
        self.changed.emit()

    def _shifted(self, window: Range, full: Range, shift: float, log: bool) -> Optional[Range]:  # noqa: E501
        """Move a window along its axis, within the full range, keeping its span.

        Args:
            window (Range): The shown window.
            full (Range): The full range.
            shift (float): How far it moves, as a share of its span (positive towards the high values).
            log (bool): Whether the axis is logarithmic.

        Returns:
            Optional[Range]: The moved window.
        """
        low, high = (self._scale(value, log) for value in window)
        full_low, full_high = (self._scale(value, log) for value in sorted(full))  # noqa: E501
        span = high - low
        low = min(max(low + span * shift, full_low), full_high - span)
        return self._clamp((self._unscale(low, log), self._unscale(low + span, log)), full, log)  # noqa: E501

    def _pan(self, x_shift: float, y_shift: float) -> None:
        """Scroll the zoomed windows.

        Args:
            x_shift (float): How far the x window moves, as a share of its span.
            y_shift (float): How far the y window moves, as a share of its span.
        """
        frame = self.frame
        if frame is None or self.anchor_low:
            return
        if x_shift and self.x_window is not None and self.full_x is not None:
            self.x_window = self._shifted(self.x_window, self.full_x, x_shift, frame.log_x)
            self.x_window_changed.emit(self.x_window)
        if y_shift and self.y_window is not None and self.full_y is not None:
            self.y_window = self._shifted(self.y_window, self.full_y, y_shift, frame.log_y)
        self.logger.debug("Zoomed chart scrolled: x %s, y %s.", self.x_window, self.y_window)
        self.changed.emit()

    def _on_wheel(self, event: QWheelEvent) -> bool:
        """Zoom (Ctrl) or scroll a zoomed chart with the wheel.

        Args:
            event (QWheelEvent): The wheel event.

        Returns:
            bool: Whether the zoom used the event (the page does not scroll then).
        """
        position = event.position()
        if not self._in_plot(position):
            return False
        modifiers = event.modifiers()
        vertical, sideways = event.angleDelta().y() / 120, event.angleDelta().x() / 120
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if not vertical:
                return False
            only_y = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            self._zoom_at(position, self.ZOOM_IN**vertical, not only_y, only_y or self.wheel_y)
            return True
        if not self._zoomed() or self.anchor_low:
            return False
        inverted = -1 if self.frame is not None and self.frame.invert_y else 1
        if modifiers & Qt.KeyboardModifier.ShiftModifier or self.x_window is None:
            self._pan(-sideways * self.PAN_STEP, (vertical or sideways) * self.PAN_STEP * inverted)
        else:
            self._pan(-(vertical or sideways) * self.PAN_STEP, 0.0)
        return True

    def _drag_pan(self, position: QPointF) -> None:
        """Scroll a zoomed chart with the middle-button drag.

        Args:
            position (QPointF): The mouse position.
        """
        frame, start = self.frame, self.pan_from
        if frame is None or start is None:
            return
        self.pan_from = position
        if self.x_window is not None and self.full_x is not None:
            span = frame.value_x(frame.area.right()) - frame.value_x(frame.area.left())
            moved = frame.value_x(start.x()) - frame.value_x(position.x())
            self._pan(moved / span if span else 0.0, 0.0)
        if self.y_window is not None and self.full_y is not None:
            span = frame.value_y(frame.area.top()) - frame.value_y(frame.area.bottom())
            moved = frame.value_y(start.y()) - frame.value_y(position.y())
            self._pan(0.0, moved / span if span else 0.0)

    def _apply_band(self) -> bool:
        """Zoom into the dragged rectangle.

        Returns:
            bool: Whether the rectangle was large enough to zoom into.
        """
        start, end, frame = self.band_start, self.band_end, self.frame
        self.band_start, self.band_end = None, None
        if start is None or end is None or frame is None:
            return False
        moved_x, moved_y = abs(end.x() - start.x()), abs(end.y() - start.y())
        if max(moved_x, moved_y) < self.DRAG_PIXELS:
            self.changed.emit()
            return False
        if self.zoom_x and self.full_x is not None and moved_x >= self.DRAG_PIXELS:
            wished = (frame.value_x(start.x()), frame.value_x(end.x()))
            self.x_window = self._clamp(wished, self.full_x, frame.log_x)
            self.x_window_changed.emit(self.x_window)
        if self.zoom_y and self.full_y is not None and moved_y >= self.DRAG_PIXELS:
            wished = (frame.value_y(start.y()), frame.value_y(end.y()))
            self.y_window = self._clamp(wished, self.full_y, frame.log_y)
        self.logger.info("Chart zoomed into a rectangle: x %s, y %s.", self.x_window, self.y_window)
        self.changed.emit()
        return True

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_frame(self, frame: PlotFrame, full_x: Optional[Range], full_y: Optional[Range]) -> None:  # noqa: E501
        """Remember the frame and the full ranges of the latest paint.

        Args:
            frame (PlotFrame): The plot frame, mapping the shown values to the pixels.
            full_x (Optional[Range]): The full x range, `None` when the x axis is not zoomable.
            full_y (Optional[Range]): The full y range, `None` when the y axis is not zoomable.
        """
        self.frame, self.full_x, self.full_y = frame, full_x, full_y

    def x_range(self, low: float, high: float, log: bool = False) -> Range:
        """Get the shown x range.

        Args:
            low (float): The low bound of the full range.
            high (float): The high bound of the full range.
            log (bool): Whether the axis is logarithmic.

        Returns:
            Range: The x window kept within the full range, the full range when not zoomed.
        """
        window = self._clamp(self.x_window, (low, high), log) if self.x_window is not None else None
        return window if window is not None else (low, high)

    def y_range(self, low: float, high: float, log: bool = False) -> Range:
        """Get the shown y range.

        Args:
            low (float): The low bound of the full range.
            high (float): The high bound of the full range.
            log (bool): Whether the axis is logarithmic.

        Returns:
            Range: The y window kept within the full range, the full range when not zoomed.
        """
        window = self._clamp(self.y_window, (low, high), log) if self.y_window is not None else None
        return window if window is not None else (low, high)

    def is_zoomed(self) -> bool:
        """Tell whether an axis is zoomed.

        Returns:
            bool: Whether a window is shown instead of a full range.
        """
        return self._zoomed()

    def zoom_center(self, factor: float) -> None:
        """Zoom around the middle of the plot (the zoom buttons).

        Args:
            factor (float): The share of the span kept (below 1 zooms in, above 1 zooms out).
        """
        frame = self.frame
        if frame is None:
            self.logger.debug("Nothing painted yet to zoom.")
            return
        self._zoom_at(frame.area.center(), factor, True, self.wheel_y)

    def reset(self) -> None:
        """Show the full ranges again."""
        if not self.is_zoomed():
            return
        self.logger.info("Chart zoom reset.")
        self.x_window, self.y_window = None, None
        self.x_window_changed.emit(None)
        self.changed.emit()

    def follow(self, key: str) -> None:
        """Keep the zoom while the chart shows the same thing, reset it for another one.

        Args:
            key (str): What the chart shows, e.g. its axes.
        """
        if key != self.key:
            self.key = key
            self.x_window, self.y_window = None, None
            self.logger.debug("Chart zoom cleared for new axes.")

    def set_x_window(self, window: Optional[Range]) -> None:
        """Show an x window set by another chart sharing the x axis (without telling it back).

        Args:
            window (Optional[Range]): The x window, `None` for the full range.
        """
        if window != self.x_window:
            self.x_window = window
            self.changed.emit()

    def paint(self, painter: QPainter) -> None:
        """Paint the zoom rectangle being dragged, and the hint while zoomed.

        Args:
            painter (QPainter): The painter of the chart.
        """
        frame = self.frame
        if frame is None:
            return
        painter.save()
        color = QColor(self.BAND_COLOR)
        if self.band_start is not None and self.band_end is not None:
            band = QRectF(self.band_start, self.band_end).normalized().intersected(frame.area)  # noqa: E501
            if not self.zoom_y:
                band = QRectF(band.left(), frame.area.top(), band.width(), frame.area.height())
            if not self.zoom_x:
                band = QRectF(frame.area.left(), band.top(), frame.area.width(), band.height())
            fill = QColor(color)
            fill.setAlpha(50)
            painter.fillRect(band, fill)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.drawRect(band)
        if self.is_zoomed():
            painter.setPen(color)
            box = QRectF(frame.area.right() - 300, frame.area.top() + 2, 296, 16)
            painter.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.HINT)
        painter.restore()

    def eventFilter(self, watched: Optional[QObject], event: Optional[QEvent]) -> bool:
        """Zoom with the wheel, a pinch or a dragged rectangle, reset with a double-click or Escape (Qt override).

        Args:
            watched (Optional[QObject]): The chart.
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was used by the zoom (the chart does not see it then).
        """
        if watched is not self.target or event is None:
            return False
        match event:
            case QWheelEvent():
                return self._on_wheel(event)
            case QNativeGestureEvent() if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                if self._in_plot(event.position()):
                    self._zoom_at(event.position(), max(0.2, 1 - event.value()), True, self.wheel_y)
                    return True
                return False
            case QMouseEvent() if event.type() == QEvent.Type.MouseButtonDblClick:
                if self._in_plot(event.position()) and self.is_zoomed():
                    self.reset()
                    return True
                return False
            case QMouseEvent() if event.type() == QEvent.Type.MouseButtonPress:
                if not self._in_plot(event.position()):
                    return False
                if event.button() == Qt.MouseButton.MiddleButton and self.is_zoomed():
                    self.pan_from = event.position()
                    return True
                if event.button() == Qt.MouseButton.LeftButton:
                    self.band_start, self.band_end = event.position(), event.position()
                return False
            case QMouseEvent() if event.type() == QEvent.Type.MouseMove and self.pan_from is not None:
                self._drag_pan(event.position())
                return True
            case QMouseEvent() if event.type() == QEvent.Type.MouseButtonRelease and self.pan_from is not None:
                self.pan_from = None
                return True
            case QMouseEvent() if event.type() == QEvent.Type.MouseMove and self.band_start is not None:
                self.band_end = event.position()
                self.changed.emit()
                return False
            case QMouseEvent() if event.type() == QEvent.Type.MouseButtonRelease and self.band_start is not None:
                self.band_end = event.position()
                return self._apply_band()
            case QKeyEvent() if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if self.is_zoomed():
                    self.reset()
                    return True
                return False
            case _:
                return False
