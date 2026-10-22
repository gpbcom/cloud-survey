from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

# First Party Imports.
from gui.charts.base.chart_zoom import ChartZoom
from gui.charts.base.plot_frame import PlotFrame
from gui.theme import Theme
from models.cloud.enums import CloudProvider


class ProviderBarChart(QWidget):
    """Horizontal bar chart of the number of products of each cloud provider, with its country flag.

    Attributes:
        ROW_HEIGHT (ClassVar[int]): The height of a provider row, in pixels.
        FLAG_HEIGHT (ClassVar[int]): The height of the country flags, in pixels.
        COUNT_WIDTH (ClassVar[int]): The width of the product counts, in pixels.
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The charted providers, one row each.
        counts (Dict[CloudProvider, int]): The number of products, by cloud provider.
        zoom (ChartZoom): The zoom of the counts (Ctrl + wheel or a dragged rectangle, reset by a double-click).
    """

    ROW_HEIGHT: ClassVar[int] = 22
    FLAG_HEIGHT: ClassVar[int] = 10
    COUNT_WIDTH: ClassVar[int] = 44

    def __init__(self, theme: Theme) -> None:
        """Build an empty chart of every provider.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.zoom = ChartZoom(self, zoom_y=False, anchor_low=True)
        self.theme = theme
        self.providers: List[CloudProvider] = list(CloudProvider)
        self.counts: Dict[CloudProvider, int] = {}
        self.setMinimumHeight(self.ROW_HEIGHT * len(self.providers))

    ############################
    # Internal Helpers Methods #
    ############################

    def _label_width(self) -> int:
        """Get the width of the label column: the flag and the longest short provider name.

        Returns:
            int: The label column width, in pixels.
        """
        metrics = self.fontMetrics()
        labels = [self.theme.PROVIDER_SHORT_LABELS[provider] for provider in self.providers]
        widest = max((metrics.horizontalAdvance(label) for label in labels), default=0)
        return round(self.FLAG_HEIGHT * 1.5) + 6 + widest + 10

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_counts(self, counts: Dict[CloudProvider, int], providers: Optional[List[CloudProvider]] = None) -> None:
        """Show new product counts.

        Args:
            counts (Dict[CloudProvider, int]): The number of products, by cloud provider.
            providers (Optional[List[CloudProvider]]): The charted providers, every provider by default.
        """
        self.counts = counts
        self.providers = list(CloudProvider) if providers is None else providers
        self.setMinimumHeight(self.ROW_HEIGHT * len(self.providers))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        """Get the preferred size (Qt override): one fixed height row per provider.

        Returns:
            QSize: The preferred size.
        """
        return QSize(480, self.ROW_HEIGHT * len(self.providers))

    def paintEvent(self, event: Optional[QPaintEvent]) -> None:
        """Paint one labelled bar per provider (Qt override).

        Args:
            event (Optional[QPaintEvent]): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        highest = max((self.counts.get(provider, 0) for provider in self.providers), default=0) or 1
        label_width, row_height = self._label_width(), self.ROW_HEIGHT
        flag_width = round(self.FLAG_HEIGHT * 1.5)
        bar_space = max(self.width() - label_width - self.COUNT_WIDTH - 8, 1)
        shown = self.zoom.x_range(0.0, float(highest))[1]
        frame = PlotFrame(QRectF(label_width, 0, bar_space, self.height()), (0.0, shown), (0.0, 1.0))
        self.zoom.set_frame(frame, (0.0, float(highest)), None)
        for row, provider in enumerate(self.providers):
            top = row * row_height
            count = self.counts.get(provider, 0)
            flag = self.theme.flag_pixmap(provider.country, self.FLAG_HEIGHT)
            painter.drawPixmap(0, top + (row_height - self.FLAG_HEIGHT) // 2, flag)
            painter.setPen(QColor(self.theme.TEXT_MUTED))
            label_box = QRect(flag_width + 6, top, label_width - flag_width - 6, row_height)
            painter.drawText(label_box, Qt.AlignmentFlag.AlignVCenter, self.theme.PROVIDER_SHORT_LABELS[provider])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme.SURFACE_ALT))
            track = QRect(label_width, top + row_height // 4, bar_space, row_height // 2)
            painter.drawRoundedRect(track, 4, 4)
            painter.setBrush(self.theme.provider_color(provider))
            painter.drawRoundedRect(
                track.adjusted(0, 0, -bar_space + round(bar_space * min(count / shown, 1)), 0), 4, 4
            )
            painter.setPen(QColor(self.theme.TEXT))
            count_box = QRect(label_width + bar_space + 8, top, self.COUNT_WIDTH, row_height)
            painter.drawText(count_box, Qt.AlignmentFlag.AlignVCenter, str(count) if count else "\u2013")
        self.zoom.paint(painter)
        painter.end()
