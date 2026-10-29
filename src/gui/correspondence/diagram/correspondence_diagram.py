from __future__ import annotations

# Standard Library Imports.
import csv
import html
import io
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QHelpEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.correspondence.diagram.diagram_layout import DiagramLayout
from gui.correspondence.diagram.shapes.diagram_edge import DiagramEdge
from gui.correspondence.diagram.shapes.diagram_group import DiagramGroup
from gui.correspondence.diagram.shapes.diagram_pill import DiagramPill
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.correspondence.enums import ConceptSource, MatchStrength, MemberRole


class CorrespondenceDiagram(QWidget):
    """The correspondence diagram: one row per concept, its services per provider joined by coloured connectors.

    Attributes:
        READABLE_COLUMN (ClassVar[float]): The width of a provider column by default, its names readable.
        COLUMN_RANGE (ClassVar[Tuple[float, float]]): The narrowest and the widest provider column asked for.
        WIDTH_STEP (ClassVar[float]): How much a click on widen (or a Ctrl + wheel notch) widens the columns.
        DIMMED (ClassVar[float]): The opacity of the rows which are not hovered, while a row is.
        CONCEPT_FILL (ClassVar[str]): The fill of the concept pills.
        laid_out (pyqtSignal): Emitted once the rows are placed again (the header follows the columns).
        concept_selected (pyqtSignal): Emitted with the concept of a clicked row.
        service_selected (pyqtSignal): Emitted with the product of a clicked service pill.
        theme (Theme): The application theme.
        groups (List[DiagramGroup]): The rows shown, grouped by domain.
        columns (List[CloudProvider]): The provider columns.
        strength (MatchStrength): Whether the partial services are shown.
        layout_ (Optional[DiagramLayout]): The placed rows, `None` before the first read.
        message (str): What the diagram says when it shows no row.
        title (str): The header of the first column (what the rows stand for).
        available (Tuple[int, int]): The width and height the diagram fills (the visible part of its scroll area).
        column_target (Optional[float]): The width asked for the provider columns (the diagram scrolls sideways when
            they do not fit), `None` to fit every column to the available width.
        hovered (Optional[int]): The concept of the hovered row.
        selected (Optional[int]): The concept of the selected row.
        logger (Logger): The diagram logger.

    Notes:
        - The provider columns are readable by default (the area scrolls sideways when they do not all fit, the
          header following): widen, narrow, or fit every column to the width (all at once, names shortened). Ctrl +
          wheel widens or narrows them, the plain wheel scrolls the rows. The diagram always fills its area.
        - Only the rows crossing the painted area are drawn: the diagram stays fluid with hundreds of rows.
        - Hovering a row dims the others, clicking it shows it in the details panel.
    """

    READABLE_COLUMN: ClassVar[float] = 140.0
    COLUMN_RANGE: ClassVar[Tuple[float, float]] = (18.0, 640.0)
    WIDTH_STEP: ClassVar[float] = 1.25
    DIMMED: ClassVar[float] = 0.28
    CONCEPT_FILL: ClassVar[str] = "#0b161b"

    laid_out = pyqtSignal()
    concept_selected = pyqtSignal(int)
    service_selected = pyqtSignal(int)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty diagram.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The diagram logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.groups: List[DiagramGroup] = []
        self.columns: List[CloudProvider] = []
        self.strength = MatchStrength.ANY
        self.layout_: Optional[DiagramLayout] = None
        self.message = "Reading the correspondences…"
        self.title = "Service concept"
        self.available = (960, 320)
        self.column_target: Optional[float] = self.READABLE_COLUMN
        self.hovered: Optional[int] = None
        self.selected: Optional[int] = None
        self.setMouseTracking(True)
        self.logger.debug("Correspondence diagram built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _needed_width(self, column: float) -> float:
        """Get the width of a diagram whose provider columns have a given width.

        Args:
            column (float): The width of a provider column.

        Returns:
            float: The width of the diagram (concept column, provider columns and the spaces between them).
        """
        fixed = 2 * DiagramLayout.MARGIN + DiagramLayout.BAND_WIDTH + 8
        readable = column >= DiagramLayout.NARROW_COLUMN
        concept = DiagramLayout.CONCEPT_WIDTH if readable else DiagramLayout.COMPACT_CONCEPT_WIDTH
        share = column / 0.75 if column / 3 <= DiagramLayout.COLUMN_GAP else column + DiagramLayout.COLUMN_GAP
        return fixed + concept + max(len(self.columns), 1) * share + 1

    def _relayout(self) -> None:
        """Place the rows again for the available width and the asked column width, and fill the area."""
        width, height = self.available
        drawn = (
            float(width) if self.column_target is None else max(float(width), self._needed_width(self.column_target))
        )
        self.layout_ = DiagramLayout(self.groups, self.columns, self.strength, self.logger, drawn)
        self.setFixedSize(QSize(max(int(self.layout_.width), width), max(int(self.layout_.height), height)))
        self.update()
        self.logger.debug(
            "Correspondence diagram laid out: %d rows, %d columns, %.0f x %.0f px.",
            len(self.layout_.rows),
            len(self.columns),
            self.layout_.width,
            self.layout_.height,
        )
        self.laid_out.emit()

    def _set_column_target(self, column: Optional[float]) -> None:
        """Ask for a width of the provider columns, then place the rows again.

        Args:
            column (Optional[float]): The width, kept within `COLUMN_RANGE`, `None` to fit every column.
        """
        low, high = self.COLUMN_RANGE
        self.column_target = None if column is None else max(low, min(high, column))
        self.logger.debug("Correspondence columns: %s.", "fitted" if column is None else f"{self.column_target:.0f} px")
        self._relayout()

    def _tooltip(self, pill: DiagramPill) -> str:
        """Write the tooltip of a pill.

        Args:
            pill (DiagramPill): The pill.

        Returns:
            str: Rich text: the service (provider, role, confidence, source, description), the concept, or the gap.
        """
        if pill.is_concept():
            return f"<b>{html.escape(pill.text)}</b><br>{html.escape(self.theme.CORRESPONDENCE_LABELS[pill.kind])}"
        if pill.member is None or pill.provider is None:
            provider = self.theme.provider_label(pill.provider) if pill.provider else ""
            return f"No {html.escape(provider)} service in this row"
        member = pill.member
        role = "Equivalent" if member.role is MemberRole.EQUIVALENT else "Partial"
        source = "set by hand" if member.source is ConceptSource.USER else f"AI, {member.confidence}% sure"
        lines = [
            f"<b>{html.escape(member.name)}</b>",
            f"{html.escape(self.theme.provider_label(member.provider))} · {role} · {source}",
        ]
        if member.deleted:
            lines.append("<i>Deleted from its catalogue</i>")
        if member.description:
            lines.append(html.escape(member.description))
        return "<br>".join(lines)

    def _paint_edge(self, painter: QPainter, edge: DiagramEdge) -> None:
        """Paint a connector.

        Args:
            painter (QPainter): The painter.
            edge (DiagramEdge): The connector.
        """
        pen = QPen(self.theme.correspondence_edge(edge.kind), edge.width())
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if edge.partial:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(edge.path())

    def _paint_pill(self, painter: QPainter, pill: DiagramPill) -> None:
        """Paint a pill: the concept, a service tinted by its class, or a dashed empty slot.

        Args:
            painter (QPainter): The painter.
            pill (DiagramPill): The pill.
        """
        rect = pill.rect
        font = QFont(self.font())
        if pill.is_gap():
            painter.setPen(QPen(QColor(self.theme.BORDER), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(self.theme.SURFACE))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            if rect.width() >= 60:
                text = painter.fontMetrics().elidedText(
                    "—  no equivalent", Qt.TextElideMode.ElideRight, int(rect.width()) - 8
                )
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            return
        if pill.is_concept():
            painter.setPen(QPen(self.theme.correspondence_edge(pill.kind), 1.4))
            painter.setBrush(QColor(self.CONCEPT_FILL))
            painter.drawRoundedRect(rect, 8, 8)
            font.setBold(True)
            ink = QColor(self.theme.TEXT)
        else:
            member = pill.member
            pen = QPen(QColor(self.theme.correspondence_edge(pill.kind)), 1.0)
            if member is not None and member.role is MemberRole.PARTIAL:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(self.theme.correspondence_fill(pill.kind))
            painter.drawRoundedRect(rect, 8, 8)
            if pill.provider is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self.theme.provider_color(pill.provider))
                painter.drawRoundedRect(QRectF(rect.left() + 6, rect.center().y() - 4, 8, 8), 4, 4)
            font.setStrikeOut(member is not None and member.deleted)
            ink = self.theme.correspondence_ink(pill.kind)
        painter.setFont(font)
        painter.setPen(ink)
        text_rect = rect.adjusted(20 if not pill.is_concept() else 10, 0, -6, 0)
        mark = " ✎" if pill.member is not None and pill.member.source is ConceptSource.USER else ""
        room = int(text_rect.width()) - (14 if mark else 0)
        if room < 30:
            return
        text = painter.fontMetrics().elidedText(pill.text, Qt.TextElideMode.ElideRight, room)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text + mark)

    def _paint_groups(self, painter: QPainter, layout: DiagramLayout, visible: QRectF) -> None:
        """Paint the domain headers and bands crossing the painted area.

        Args:
            painter (QPainter): The painter.
            layout (DiagramLayout): The placed diagram.
            visible (QRectF): The painted area.
        """
        bold = QFont(self.font())
        bold.setBold(True)
        for group in layout.groups:
            color = QColor(group.color)
            if group.band.intersects(visible):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(group.band, 2, 2)
            if not group.header.intersects(visible):
                continue
            painter.setFont(bold)
            painter.setPen(color)
            painter.drawText(
                group.header.adjusted(0, 4, 0, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                group.title,
            )
            painter.setPen(QPen(QColor(self.theme.BORDER), 1))
            painter.drawLine(group.header.bottomLeft(), group.header.bottomRight())

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_rows(
        self,
        groups: Sequence[DiagramGroup],
        columns: Sequence[CloudProvider],
        strength: MatchStrength = MatchStrength.ANY,
        message: str = "No concept matches the filters.",
        title: str = "Service concept",
    ) -> None:
        """Show rows.

        Args:
            groups (Sequence[DiagramGroup]): The rows, grouped by domain.
            columns (Sequence[CloudProvider]): The provider columns, in their order.
            strength (MatchStrength): Whether the partial services are shown.
            message (str): What the diagram says when there is no row.
            title (str): The header of the first column (what the rows stand for).
        """
        self.groups, self.columns, self.strength = list(groups), list(columns), strength
        self.message, self.title = message, title
        self.hovered = None
        self._relayout()
        if self.layout_ is not None and self.selected not in self.layout_.rows:
            self.selected = None
        self.logger.debug("Correspondence diagram shows %d rows.", len(self.layout_.rows) if self.layout_ else 0)

    def set_message(self, message: str) -> None:
        """Say something instead of the rows (e.g. while reading, or after an error).

        Args:
            message (str): The message.
        """
        self.logger.debug("Correspondence diagram message: %s", message)
        self.message = message
        self.groups = []
        self._relayout()

    def fit(self, width: int, height: int) -> None:
        """Fill a new area (the scroll area was resized).

        Args:
            width (int): The width to fill, in pixels.
            height (int): The height to fill, in pixels.
        """
        if (width, height) == self.available:
            return
        self.available = (max(width, 200), max(height, 80))
        self.logger.debug("Correspondence diagram fitted to %d x %d px.", *self.available)
        self._relayout()

    def select(self, concept_id: Optional[int]) -> None:
        """Highlight the row of a concept.

        Args:
            concept_id (Optional[int]): The concept, `None` for none.
        """
        if concept_id is not None and self.layout_ is not None and concept_id not in self.layout_.rows:
            self.logger.debug("The concept %d is not shown in the diagram: nothing is highlighted.", concept_id)
        self.selected = concept_id
        self.update()

    def widen(self) -> None:
        """Widen the provider columns (the diagram scrolls sideways once they no longer fit)."""
        current = self.layout_.column_width if self.layout_ is not None else self.READABLE_COLUMN
        self._set_column_target(current * self.WIDTH_STEP)

    def narrow(self) -> None:
        """Narrow the provider columns."""
        current = self.layout_.column_width if self.layout_ is not None else self.READABLE_COLUMN
        self._set_column_target(current / self.WIDTH_STEP)

    def fit_all(self) -> None:
        """Fit every provider column to the available width (all at once, the names shortened)."""
        self._set_column_target(None)

    def readable(self) -> None:
        """Give the provider columns their readable width again (the default)."""
        self._set_column_target(self.READABLE_COLUMN)

    def csv(self) -> str:
        """Export the shown rows.

        Returns:
            str: One CSV line per row: its name, its domain, then the services of each provider column.
        """
        layout = self.layout_
        if layout is None or not layout.rows:
            self.logger.warning("No row shown: the correspondence CSV is empty.")
            return ""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([self.title, "Domain", *(self.theme.provider_label(provider) for provider in layout.columns)])
        for group in layout.groups:
            for concept in group.concepts:
                cells = [
                    "; ".join(
                        member.name + (" (partial)" if member.role is MemberRole.PARTIAL else "")
                        for member in concept.members_of(provider, layout.strength)
                    )
                    for provider in layout.columns
                ]
                writer.writerow([concept.name, group.title, *cells])
        self.logger.info("Correspondence CSV written: %d rows, %d provider columns.", len(layout.rows), len(layout.columns))
        return buffer.getvalue()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): the placed rows.

        Returns:
            QSize: The preferred size.
        """
        if self.layout_ is None:
            return QSize(*self.available)
        return QSize(int(self.layout_.width), int(self.layout_.height))

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltips, follow the hovered row, select the clicked one (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        layout = self.layout_
        if event is None or layout is None:
            return super().event(event)
        match event.type():
            case QEvent.Type.ToolTip if isinstance(event, QHelpEvent):
                pill = layout.pill_at(QPointF(event.pos()))
                if pill is None:
                    QToolTip.hideText()
                else:
                    QToolTip.showText(event.globalPos(), self._tooltip(pill), self)
                return True
            case QEvent.Type.MouseMove if isinstance(event, QMouseEvent):
                hovered = layout.concept_at(event.position())
                if hovered != self.hovered:
                    self.hovered = hovered
                    self.update()
            case QEvent.Type.MouseButtonRelease if isinstance(event, QMouseEvent):
                if event.button() is Qt.MouseButton.LeftButton:
                    concept_id = layout.concept_at(event.position())
                    if concept_id is not None:
                        self.logger.debug("Concept %d clicked in the diagram.", concept_id)
                        self.select(concept_id)
                        self.concept_selected.emit(concept_id)
                    pill = layout.pill_at(event.position())
                    if pill is not None and pill.member is not None:
                        self.service_selected.emit(pill.member.product_id)
            case QEvent.Type.Leave:
                if self.hovered is not None:
                    self.hovered = None
                    self.update()
        return super().event(event)

    def wheelEvent(self, event: Optional[QWheelEvent]) -> None:
        """Widen or narrow the columns with Ctrl + wheel, let the plain wheel scroll the rows (Qt override).

        Args:
            event (Optional[QWheelEvent]): The wheel event.
        """
        if event is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.widen()
            else:
                self.narrow()
            event.accept()
            return
        event.ignore()

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the rows crossing the painted area (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.theme.SURFACE))
        layout = self.layout_
        if layout is None or not layout.rows:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            area = QRectF(0, 0, *self.available).adjusted(12, 24, -12, 0)
            painter.drawText(
                area, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.message
            )
            painter.end()
            return
        visible = QRectF(event.rect()) if event is not None else QRectF(self.rect())
        self._paint_groups(painter, layout, visible)
        bands = layout.rows
        if self.selected is not None and self.selected in bands:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.SURFACE_ALT))
            painter.drawRoundedRect(bands[self.selected].adjusted(6, -5, 0, 5), 10, 10)
        shown = {concept_id for concept_id, band in bands.items() if band.adjusted(0, -8, 0, 8).intersects(visible)}
        focus = self.hovered
        for edge in (edge for edge in layout.edges if edge.concept_id in shown):
            painter.setOpacity(1.0 if focus is None or edge.concept_id == focus else self.DIMMED)
            self._paint_edge(painter, edge)
        for pill in (pill for pill in layout.pills if pill.concept_id in shown):
            painter.setOpacity(1.0 if focus is None or pill.concept_id == focus else self.DIMMED)
            self._paint_pill(painter, pill)
        painter.setOpacity(1.0)
        painter.end()
