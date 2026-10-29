from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget


class ChartWindow(QDialog):
    """A window showing a chart (or a diagram) widened, out of its card, until it is closed.

    Attributes:
        SCREEN_SHARE (ClassVar[float]): The share of the screen the window takes when it opens.
        closed (pyqtSignal): Emitted once the window is closed (its chart goes back to its card).
        body (QWidget): The chart shown.
        title_label (QLabel): The title of the chart.
        close_button (QToolButton): Closes the window (as Escape does).
        logger (Logger): The window logger.

    Notes:
        The chart itself moves into the window (its data, zoom and tooltips kept), and back into its card once the
        window is closed by its × button, by Escape or by the title bar.
    """

    SCREEN_SHARE: ClassVar[float] = 0.92

    closed = pyqtSignal()

    def __init__(self, title: str, body: QWidget, logger: Optional[Logger] = None) -> None:
        """Build the window around a chart.

        Args:
            title (str): The title of the chart.
            body (QWidget): The chart, taken from its card.
            logger (Optional[Logger]): The window logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.body = body
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(False)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setToolTip("Close the window (Esc): the chart goes back to its card")
        self.close_button.setAccessibleName("Close")
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(body, 1)
        body.show()
        self.close_button.clicked.connect(self.reject)
        self.finished.connect(self._on_finished)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.resize(int(area.width() * self.SCREEN_SHARE), int(area.height() * self.SCREEN_SHARE))
        else:
            self.logger.warning("No primary screen: the chart window %r keeps its default size.", title)
        self.logger.debug("Chart %r opened in its own window.", title)

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_finished(self, _: int) -> None:
        """Tell that the window is closed, whichever way.

        Args:
            _ (int): The result of the dialog (unused).
        """
        self.logger.debug("Chart window %r closed.", self.windowTitle())
        self.closed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def release(self) -> QWidget:
        """Give the chart back (before it returns to its card).

        Returns:
            QWidget: The chart, out of the window layout.
        """
        layout = self.layout()
        if layout is not None:
            layout.removeWidget(self.body)
        else:
            self.logger.warning("The chart window %r has no layout to release its chart from.", self.windowTitle())
        self.logger.debug("Chart released from the window %r.", self.windowTitle())
        return self.body
