from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QEnterEvent, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

# First Party Imports.
from gui.theme import Theme


class HelpChip(QWidget):
    """A clickable chip explaining one thing: a coloured badge, a title, a value, and a rich tooltip.

    Attributes:
        HEIGHT (ClassVar[int]): The height of a chip, in pixels.
        PADDING (ClassVar[int]): The space inside the chip, left and right.
        BADGE (ClassVar[int]): The diameter of the badge.
        GAP (ClassVar[int]): The space between the badge, the title and the value.
        VALUE_WIDTH (ClassVar[int]): The widest value shown, elided beyond.
        clicked (pyqtSignal): Emitted when the chip is clicked.
        theme (Theme): The application theme.
        accent (QColor): The colour of the badge and of the highlight.
        symbol (str): The glyph of the badge.
        title (str): The bold title.
        value (str): The value, muted, after the title.
        hovered (bool): Whether the mouse is over the chip.
        selected (bool): Whether the chip is highlighted (picked).
        dimmed (bool): Whether the chip is drawn faded (its parameter is not used).
        logger (Logger): The chip logger.

    Notes:
        The tooltip is rich text: the explanation of the role or of the warning, in its colour.
    """

    HEIGHT: ClassVar[int] = 34
    PADDING: ClassVar[int] = 10
    BADGE: ClassVar[int] = 20
    GAP: ClassVar[int] = 8
    VALUE_WIDTH: ClassVar[int] = 280

    clicked = pyqtSignal()

    def __init__(self, theme: Theme, accent: QColor, symbol: str, title: str, logger: Optional[Logger] = None) -> None:
        """Build a chip.

        Args:
            theme (Theme): The application theme.
            accent (QColor): The colour of the badge and of the highlight.
            symbol (str): The glyph of the badge.
            title (str): The bold title.
            logger (Optional[Logger]): The chip logger.
        """
        super().__init__()
        self.theme = theme
        self.accent = QColor(accent)
        self.symbol, self.title, self.value = symbol, title, ""
        self.hovered = self.selected = self.dimmed = False
        self.logger = logger if logger else getLogger(__name__)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)
        self.logger.debug("Chip %r built.", title)

    ############################
    # Internal Helpers Methods #
    ############################

    def _bold(self) -> QFont:
        """Get the font of the title.

        Returns:
            QFont: The widget font, bold.
        """
        font = QFont(self.font())
        font.setBold(True)
        return font

    def _shown_value(self) -> str:
        """Get the value as drawn: elided beyond `VALUE_WIDTH`.

        Returns:
            str: The value.
        """
        return self.fontMetrics().elidedText(self.value, Qt.TextElideMode.ElideRight, self.VALUE_WIDTH)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_content(self, value: str, tooltip: str, dimmed: bool = False) -> None:
        """Show a value and its explanation.

        Args:
            value (str): The value, after the title.
            tooltip (str): The rich text explanation.
            dimmed (bool): Whether the chip is drawn faded (its parameter is not used).
        """
        self.logger.debug("Chip %r shows %r%s.", self.title, value, " (dimmed)" if dimmed else "")
        self.value, self.dimmed = value, dimmed
        self.setToolTip(tooltip)
        self.setAccessibleDescription(value)
        self.updateGeometry()
        self.update()

    def set_selected(self, selected: bool) -> None:
        """Highlight the chip, or not.

        Args:
            selected (bool): Whether it is highlighted.
        """
        self.logger.debug("Chip %r %s.", self.title, "highlighted" if selected else "not highlighted")
        self.selected = selected
        self.update()

    def sizeHint(self) -> QSize:
        """Get the size fitting the badge, the title and the value (Qt override).

        Returns:
            QSize: The preferred size.
        """
        title = QFontMetrics(self._bold()).horizontalAdvance(self.title)
        value = self.fontMetrics().horizontalAdvance(self._shown_value()) if self.value else 0
        width = self.PADDING * 2 + self.BADGE + self.GAP + title + (self.GAP + value if value else 0)
        return QSize(width, self.HEIGHT)

    def minimumSizeHint(self) -> QSize:
        """Get the smallest size (Qt override).

        Returns:
            QSize: The preferred size, a chip never shrinks.
        """
        return self.sizeHint()

    def enterEvent(self, event: Optional[QEnterEvent]) -> None:
        """Glow when the mouse enters (Qt override).

        Args:
            event (Optional[QEnterEvent]): The event.
        """
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Optional[QEvent]) -> None:
        """Stop glowing when the mouse leaves (Qt override).

        Args:
            event (Optional[QEvent]): The event.
        """
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:
        """Tell the chip was clicked (Qt override).

        Args:
            event (Optional[QMouseEvent]): The event.
        """
        if event is not None and event.button() is Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.logger.debug("Chip %r clicked.", self.title)
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the pill, its badge, its title and its value (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(0.55 if self.dimmed and not self.hovered else 1.0)
        pill = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = QColor(self.theme.SURFACE_ALT)
        if self.hovered or self.selected:
            glow = QColor(self.accent)
            glow.setAlpha(60 if self.selected else 38)
            painter.setBrush(fill)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            fill = glow
        border = QColor(self.accent) if self.hovered or self.selected or self.hasFocus() else QColor(self.theme.BORDER)
        painter.setPen(QPen(border, 2 if self.selected else 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        center = QPointF(self.PADDING + self.BADGE / 2, self.height() / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.accent)
        painter.drawEllipse(center, self.BADGE / 2, self.BADGE / 2)
        painter.setFont(self._bold())
        painter.setPen(QColor(self.theme.WINDOW))
        badge = QRectF(center.x() - self.BADGE / 2, center.y() - self.BADGE / 2, self.BADGE, self.BADGE)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, self.symbol)
        left = self.PADDING + self.BADGE + self.GAP
        painter.setPen(QColor(self.theme.TEXT))
        title_width = QFontMetrics(self._bold()).horizontalAdvance(self.title)
        painter.drawText(QRectF(left, 0, title_width + 2, self.height()), Qt.AlignmentFlag.AlignVCenter, self.title)
        if self.value:
            painter.setFont(self.font())
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(left + title_width + self.GAP, 0, self.width(), self.height()),
                Qt.AlignmentFlag.AlignVCenter,
                self._shown_value(),
            )
        painter.end()
