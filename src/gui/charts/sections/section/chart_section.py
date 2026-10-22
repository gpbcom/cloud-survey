from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QToolButton, QVBoxLayout, QWidget

# First Party Imports.
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_window import ChartWindow


class ChartSection(QFrame):
    """Collapsible card holding a chart: a header (toggle, title, subtitle, tools) above the chart.

    Attributes:
        toggled (pyqtSignal): Emitted with the chart key and whether the section is now expanded, on each toggle.
        key (str): The chart key, e.g. `marketplace/trends`, remembering the expanded state.
        store (ChartStateStore): The store of the chart states.
        body (QWidget): The chart (and its pickers), hidden when collapsed.
        toggle (QToolButton): Expands or collapses the section, showing its title.
        subtitle (QLabel): What the chart shows exactly (grain, transform, forecast), below the title.
        tools (Optional[QWidget]): The header tools (ready-made charts, export, reset), hidden when collapsed.
        widen_button (Optional[QToolButton]): Opens the chart in its own window (`None` for a table or controls).
        placeholder (QLabel): Shown instead of the chart while it is in its own window.
        chart_window (Optional[ChartWindow]): The window of the chart while it is open.
        content (QVBoxLayout): The layout of the card (the header, the subtitle and the chart).
        logger (Logger): The section logger.

    Notes:
        - The toggle takes the keyboard focus: Space or Enter expands and collapses the section.
        - The expanded state is remembered by the store, from one session to the next.
        - "Widen" moves the chart into its own large window (its tooltips kept), closed by its × button or Escape:
          the chart then goes back to its card.
    """

    toggled = pyqtSignal(str, bool)

    def __init__(
        self,
        key: str,
        title: str,
        body: QWidget,
        store: ChartStateStore,
        tools: Optional[QWidget] = None,
        logger: Optional[Logger] = None,
        detachable: bool = True,
    ) -> None:
        """Build the section, expanded as it was left.

        Args:
            key (str): The chart key.
            title (str): The title.
            body (QWidget): The chart (and its pickers).
            store (ChartStateStore): The store of the chart states.
            tools (Optional[QWidget]): The header tools, if any.
            logger (Optional[Logger]): The section logger.
            detachable (bool): Whether the chart can open in its own window (not for a table or controls).
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setObjectName("chartCard")
        self.key, self.store, self.body, self.tools = key, store, body, tools
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle.setText(title)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("chartSubtitle")
        self.subtitle.setWordWrap(True)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self.toggle)
        header.addStretch(1)
        if tools is not None:
            header.addWidget(tools)
        self.widen_button: Optional[QToolButton] = None
        if detachable:
            self.widen_button = QToolButton()
            self.widen_button.setObjectName("chartTool")
            self.widen_button.setText("⤢ Widen")
            self.widen_button.setToolTip("Open the chart in its own large window (× or Esc closes it)")
            header.addWidget(self.widen_button)
        self.placeholder = QLabel("Shown in its own window: close it (× or Esc) to bring it back here.")
        self.placeholder.setObjectName("muted")
        self.placeholder.hide()
        self.chart_window: Optional[ChartWindow] = None
        layout = QVBoxLayout(self)
        self.content = layout
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.subtitle)
        layout.addWidget(body, 1)
        # A body capped at its content (a few bars) caps the section: the column gives the rest to the other charts.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.toggle.clicked.connect(self.set_expanded)
        if self.widen_button is not None:
            self.widen_button.clicked.connect(self.open_window)
        self._apply(store.expanded(key))

    ############################
    # Internal Helpers Methods #
    ############################

    def _apply(self, expanded: bool) -> None:
        """Show or hide the chart.

        Args:
            expanded (bool): Whether the section is expanded.
        """
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setToolTip("Collapse the chart" if expanded else "Expand the chart")
        self.toggle.setAccessibleName(f"{self.toggle.text()}, {'expanded' if expanded else 'collapsed'}")
        self.body.setVisible(expanded or self.chart_window is not None)
        self.subtitle.setVisible(expanded and bool(self.subtitle.text()))
        if self.tools is not None:
            self.tools.setVisible(expanded)
        if self.widen_button is not None:
            self.widen_button.setVisible(expanded)
        if self.chart_window is not None:
            self.placeholder.setVisible(expanded)

    def _on_window_closed(self) -> None:
        """Bring the chart back into its card once its window is closed."""
        window = self.chart_window
        if window is None:
            return
        self.chart_window = None
        body = window.release()
        self.content.replaceWidget(self.placeholder, body)
        self.placeholder.hide()
        self._apply(self.toggle.isChecked())
        window.deleteLater()
        self.logger.info("Chart %s back in its card.", self.key)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_expanded(self, expanded: bool) -> None:
        """Expand or collapse the section, and remember it.

        Args:
            expanded (bool): Whether the section is expanded.
        """
        self._apply(expanded)
        self.store.set_expanded(self.key, expanded)
        self.logger.debug("Chart section %s %s.", self.key, "expanded" if expanded else "collapsed")
        self.toggled.emit(self.key, expanded)

    def is_expanded(self) -> bool:
        """Tell whether the section is expanded.

        Returns:
            bool: Whether the chart is shown.
        """
        return self.toggle.isChecked()

    def set_heading(self, title: str, subtitle: str = "") -> None:
        """Show the title and subtitle of the chart.

        Args:
            title (str): The title.
            subtitle (str): What the chart shows exactly, empty for none.
        """
        self.toggle.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(self.is_expanded() and bool(subtitle))
        self.toggle.setAccessibleName(f"{title}, {'expanded' if self.is_expanded() else 'collapsed'}")

    def title(self) -> str:
        """Get the title of the chart.

        Returns:
            str: The title.
        """
        return self.toggle.text()

    def open_window(self) -> Optional[ChartWindow]:
        """Open the chart in its own large window (or bring the open one to the front).

        Returns:
            Optional[ChartWindow]: The window, `None` when the chart cannot leave its card.
        """
        if self.widen_button is None:
            return None
        if self.chart_window is not None:
            self.chart_window.raise_()
            self.chart_window.activateWindow()
            return self.chart_window
        self.content.replaceWidget(self.body, self.placeholder)
        self.placeholder.show()
        self.chart_window = ChartWindow(self.title(), self.body, self.logger)
        self.chart_window.closed.connect(self._on_window_closed)
        self.chart_window.show()
        self.logger.info("Chart %s opened in its own window.", self.key)
        return self.chart_window
