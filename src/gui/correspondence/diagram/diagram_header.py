from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QHelpEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.correspondence.diagram.diagram_layout import DiagramLayout
from gui.theme import Theme
from models.cloud.enums import CloudProvider


class DiagramHeader(QWidget):
    """The column headers of the correspondence diagram, kept above its rows while they scroll.

    Attributes:
        theme (Theme): The application theme.
        layout_ (Optional[DiagramLayout]): The placed diagram (its columns), `None` before the first read.
        title (str): The header of the first column.
        offset (int): How far the diagram is scrolled sideways, in pixels.
        logger (Logger): The header logger.

    Notes:
        Each provider header shows its colour, its flag, its name and the services shown in its column (its full
        name in the tooltip when the column is narrow).
    """

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty header.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The header logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.layout_: Optional[DiagramLayout] = None
        self.title = "Service concept"
        self.offset = 0
        self.setFixedHeight(int(DiagramLayout.HEADER_HEIGHT))
        self.logger.debug("Correspondence header built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _paint_provider(self, painter: QPainter, provider: CloudProvider, rect: QRectF, count: int) -> None:
        """Paint the header of a provider column: colour, flag (when it fits), name, then the services shown.

        Args:
            painter (QPainter): The painter.
            provider (CloudProvider): The provider of the column.
            rect (QRectF): Where the header is drawn.
            count (int): The services shown in the column.
        """
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.theme.SURFACE_ALT))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setBrush(self.theme.provider_color(provider))
        painter.drawRoundedRect(QRectF(rect.left(), rect.top(), 5, rect.height()), 2, 2)
        wide = rect.width() >= DiagramLayout.NARROW_COLUMN
        flag_width = 22 if wide else 0
        if wide:
            painter.drawPixmap(int(rect.left() + 10), int(rect.top() + 6), self.theme.flag_pixmap(provider.country, 12))
        bold = QFont(self.font())
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(self.theme.TEXT))
        title = QRectF(rect.left() + 9 + flag_width, rect.top() + 1, rect.width() - 12 - flag_width, rect.height() / 2)
        label = self.theme.PROVIDER_SHORT_LABELS[provider]
        name = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(title.width()))
        if name in ("", "…"):
            name = label[:1]
            title = QRectF(rect.left() + 5, rect.top() + 1, rect.width() - 5, rect.height() / 2)
        painter.drawText(title, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(self.font())
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        caption = QRectF(rect.left() + 9, rect.center().y(), rect.width() - 12, rect.height() / 2 - 1)
        label = f"{count:,} services" if wide else f"{count:,}"
        text = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(caption.width()))
        painter.drawText(caption, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_layout(self, layout: Optional[DiagramLayout], title: str) -> None:
        """Follow the columns of the diagram.

        Args:
            layout (Optional[DiagramLayout]): The placed diagram.
            title (str): The header of the first column.
        """
        self.layout_ = layout
        self.title = title
        self.update()

    def set_offset(self, offset: int) -> None:
        """Follow the sideways scrolling of the diagram.

        Args:
            offset (int): How far the diagram is scrolled, in pixels.
        """
        self.offset = offset
        self.update()

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the full name and the services of the provider under the mouse (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        layout = self.layout_
        if event is not None and event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            x = event.pos().x() + self.offset
            if layout is not None:
                for provider, rect in zip(layout.columns, layout.headers[1:], strict=True):
                    if rect.left() <= x <= rect.right():
                        count = layout.counts.get(provider, 0)
                        text = f"<b>{self.theme.provider_label(provider)}</b><br>{count:,} services shown"
                        QToolTip.showText(event.globalPos(), text, self)
                        return True
            QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the headers, scrolled with the diagram (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.theme.SURFACE))
        layout = self.layout_
        if layout is None:
            painter.end()
            return
        painter.translate(-self.offset, 0)
        bold = QFont(self.font())
        bold.setBold(True)
        concept_header, *provider_headers = layout.headers
        painter.setPen(QColor(self.theme.TEXT_MUTED))
        painter.drawText(concept_header, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        for provider, rect in zip(layout.columns, provider_headers, strict=True):
            count = layout.counts.get(provider, 0)
            self._paint_provider(painter, provider, rect, count)
        painter.end()
