from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QHelpEvent, QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QToolTip, QWidget

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.correspondence.rows.coverage_cell import CoverageCell


class CoverageMatrix(QWidget):
    """The coverage matrix: for each pair of providers, the share of the services of one matched at the other.

    Attributes:
        CELL (ClassVar[Tuple[int, int]]): The size of a cell, in pixels.
        LABEL_WIDTH (ClassVar[int]): The width of the row labels.
        HEADER_HEIGHT (ClassVar[int]): The height of the column labels.
        LOW (ClassVar[str]): The colour of a share of 0%.
        HIGH (ClassVar[str]): The colour of a share of 100%.
        pair_selected (pyqtSignal): Emitted with the two providers of a clicked cell (row, then column).
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The providers of the rows and the columns, in their order.
        cells (Dict[Tuple[CloudProvider, CloudProvider], CoverageCell]): The cells, by row and column provider.
        logger (Logger): The matrix logger.

    Notes:
        A row reads: the share of the listed services of its provider having an equivalent at the provider of the
        column. Clicking a cell shows the two providers side by side in the diagram, their gaps first.
    """

    CELL: ClassVar[Tuple[int, int]] = (86, 30)
    LABEL_WIDTH: ClassVar[int] = 150
    HEADER_HEIGHT: ClassVar[int] = 34
    LOW: ClassVar[str] = "#1d2531"
    HIGH: ClassVar[str] = "#2fb3cc"

    pair_selected = pyqtSignal(str, str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build an empty matrix.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The matrix logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.providers: List[CloudProvider] = []
        self.cells: Dict[Tuple[CloudProvider, CloudProvider], CoverageCell] = {}
        self.setMouseTracking(True)
        self.logger.debug("Coverage matrix built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _cell_rect(self, row: int, column: int) -> QRectF:
        """Get where a cell is drawn.

        Args:
            row (int): The row.
            column (int): The column.

        Returns:
            QRectF: The cell, a small gap around it.
        """
        width, height = self.CELL
        return QRectF(
            self.LABEL_WIDTH + column * width + 2, self.HEADER_HEIGHT + row * height + 2, width - 4, height - 4
        )

    def _cell_at(self, point: QPointF) -> Optional[Tuple[CloudProvider, CloudProvider]]:
        """Find the cell under a point.

        Args:
            point (QPointF): The point.

        Returns:
            Optional[Tuple[CloudProvider, CloudProvider]]: Its row and column providers, `None` outside the cells or
                on the diagonal.
        """
        width, height = self.CELL
        column = int((point.x() - self.LABEL_WIDTH) // width)
        row = int((point.y() - self.HEADER_HEIGHT) // height)
        count = len(self.providers)
        if (
            point.x() < self.LABEL_WIDTH
            or point.y() < self.HEADER_HEIGHT
            or not (0 <= row < count and 0 <= column < count)
        ):
            return None
        if row == column:
            return None
        return self.providers[row], self.providers[column]

    def _color(self, share: float) -> QColor:
        """Get the colour of a share.

        Args:
            share (float): The share, in percent.

        Returns:
            QColor: A colour between `LOW` (0%) and `HIGH` (100%).
        """
        low, high = QColor(self.LOW), QColor(self.HIGH)
        ratio = max(0.0, min(1.0, share / 100))
        return QColor(
            round(low.red() + (high.red() - low.red()) * ratio),
            round(low.green() + (high.green() - low.green()) * ratio),
            round(low.blue() + (high.blue() - low.blue()) * ratio),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): one cell per pair of providers.

        Returns:
            QSize: The preferred size.
        """
        width, height = self.CELL
        count = max(len(self.providers), 1)
        return QSize(self.LABEL_WIDTH + count * width + 4, self.HEADER_HEIGHT + count * height + 4)

    def set_cells(self, providers: List[CloudProvider], cells: List[CoverageCell]) -> None:
        """Show the coverage of providers.

        Args:
            providers (List[CloudProvider]): The providers, in their order.
            cells (List[CoverageCell]): The coverage of each ordered pair.
        """
        self.providers = list(providers)
        self.cells = {(cell.source, cell.target): cell for cell in cells}
        self.setFixedSize(self.sizeHint())
        self.update()
        if not self.providers:
            self.logger.warning("No provider column: the coverage matrix is empty.")
        elif not self.cells:
            self.logger.warning("No coverage known between the %d providers.", len(self.providers))
        self.logger.debug("Coverage of %d providers shown.", len(self.providers))

    def event(self, event: Optional[QEvent]) -> bool:
        """Show the tooltip of a cell, and select the clicked pair (Qt override).

        Args:
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event was handled.
        """
        if event is None:
            return super().event(event)
        if event.type() is QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            pair = self._cell_at(QPointF(event.pos()))
            cell = self.cells.get(pair) if pair is not None else None
            if cell is None:
                QToolTip.hideText()
                return True
            source = self.theme.provider_label(cell.source)
            target = self.theme.provider_label(cell.target)
            QToolTip.showText(
                event.globalPos(),
                f"{cell.matched:,} of the {cell.total:,} {source} services have an equivalent at {target}"
                f" ({cell.share():.0f}%).<br>Click to compare them in the diagram.",
                self,
            )
            return True
        if (
            event.type() is QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() is Qt.MouseButton.LeftButton
        ):
            pair = self._cell_at(event.position())
            if pair is not None:
                self.logger.debug("Coverage cell %s / %s clicked.", pair[0].value, pair[1].value)
                self.pair_selected.emit(pair[0].value, pair[1].value)
                return True
        return super().event(event)

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint the labels and the cells (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.CELL
        if not self.providers:
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(12, 24, -12, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                "No coverage yet",
            )
            painter.end()
            return
        bold = QFont(self.font())
        bold.setBold(True)
        for index, provider in enumerate(self.providers):
            painter.setPen(self.theme.provider_color(provider))
            label = self.theme.PROVIDER_SHORT_LABELS[provider]
            header = QRectF(self.LABEL_WIDTH + index * width, 0, width, self.HEADER_HEIGHT)
            painter.drawText(
                header,
                Qt.AlignmentFlag.AlignCenter,
                painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, width - 6),
            )
            row_label = QRectF(0, self.HEADER_HEIGHT + index * height, self.LABEL_WIDTH - 10, height)
            painter.drawText(row_label, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        painter.setFont(bold)
        for row, source in enumerate(self.providers):
            for column, target in enumerate(self.providers):
                rect = self._cell_rect(row, column)
                if row == column:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(self.theme.SURFACE_ALT))
                    painter.drawRoundedRect(rect, 6, 6)
                    continue
                cell = self.cells.get((source, target))
                share = cell.share() if cell is not None else 0.0
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._color(share))
                painter.drawRoundedRect(rect, 6, 6)
                painter.setPen(QColor("#11151c" if share >= 55 else self.theme.TEXT))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{share:.0f}%" if cell is not None else "—")
        painter.end()
