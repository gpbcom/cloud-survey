from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWIDGETSIZE_MAX,
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QToolButton,
    QWidget,
)

# First Party Imports.
from gui.charts.sections.chart_state_store import ChartStateStore


class FoldingDock(QDockWidget):
    """Dock (the logs) which folds to its title bar, giving its height to the window, and unfolds back.

    Attributes:
        DEFAULT_HEIGHT (ClassVar[int]): The height of the dock when it unfolds without a former height, in pixels.
        folded_changed (pyqtSignal): Emitted with whether the dock is now folded.
        key (str): The dock key, e.g. `window/logs`, remembering whether it is folded.
        store (ChartStateStore): The store remembering the folded state.
        main_window (QMainWindow): The window holding the dock.
        title_bar (QWidget): The title bar: the fold toggle, then the float and close buttons.
        toggle (QToolButton): Folds or unfolds the dock, showing its title.
        float_button (QToolButton): Detaches the dock from the window, or docks it back.
        close_button (QToolButton): Hides the dock (the View menu and the status bar show it again).
        folded (bool): Whether only the title bar is shown.
        height_before (int): The height of the dock before it folded, in pixels.
        logger (Logger): The dock logger.

    Notes:
        - The title bar stays visible while folded: a click on it (or Space on the toggle) unfolds the dock.
        - Folded, the content is squeezed to no height rather than hidden: a dock without visible content would
          shrink to the width of its title bar.
        - `reveal` shows a hidden dock and unfolds it, for the actions bringing the logs back.
    """

    DEFAULT_HEIGHT: ClassVar[int] = 190

    folded_changed = pyqtSignal(bool)

    def __init__(
        self,
        key: str,
        title: str,
        content: QWidget,
        window: QMainWindow,
        store: ChartStateStore,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the dock, folded as it was left.

        Args:
            key (str): The dock key.
            title (str): The dock title.
            content (QWidget): What the dock shows.
            window (QMainWindow): The window holding the dock.
            store (ChartStateStore): The store remembering the folded state.
            logger (Optional[Logger]): The dock logger.
        """
        super().__init__(title, window)
        self.logger = logger if logger else getLogger(__name__)
        self.key, self.store, self.main_window = key, store, window
        self.folded = False
        self.height_before = self.DEFAULT_HEIGHT
        self.setObjectName(key.replace("/", "-"))
        self.setWidget(content)
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle.setText(title)
        self.float_button = self._title_button("⧉", "Detach the panel from the window, or dock it back")
        self.close_button = self._title_button("✕", "Hide the panel (View menu or status bar to show it again)")
        self.title_bar = QWidget()
        self.title_bar.setObjectName("dockTitle")
        row = QHBoxLayout(self.title_bar)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(4)
        row.addWidget(self.toggle)
        row.addStretch(1)
        row.addWidget(self.float_button)
        row.addWidget(self.close_button)
        self.setTitleBarWidget(self.title_bar)
        self.toggle.clicked.connect(lambda: self.set_folded(not self.folded))
        self.float_button.clicked.connect(lambda: self.setFloating(not self.isFloating()))  # noqa: E501
        self.close_button.clicked.connect(self.close)
        self._apply(not store.expanded(key))

    ############################
    # Internal Helpers Methods #
    ############################

    def _title_button(self, text: str, tip: str) -> QToolButton:
        """Build a button of the title bar.

        Args:
            text (str): The button symbol.
            tip (str): What the button does.

        Returns:
            QToolButton: The button.
        """
        button = QToolButton()
        button.setObjectName("chartTool")
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setAutoRaise(True)
        return button

    def _fit_height(self) -> None:
        """Give the docked dock its height: its title bar while folded, its former height otherwise.

        Notes:
            A dock not docked yet (or floating) is left as it is:
            the window lays it out once it is added.
        """
        docked = self.main_window.dockWidgetArea(self) is not Qt.DockWidgetArea.NoDockWidgetArea
        if self.isFloating() or not docked:
            self.logger.debug("Dock %s not docked: its height is left to the window.", self.key)
            return
        height = self.title_bar.sizeHint().height() if self.folded else self.height_before
        self.main_window.resizeDocks([self], [height], Qt.Orientation.Vertical)

    def _apply(self, folded: bool) -> None:
        """Show the content, or only the title bar.

        Args:
            folded (bool): Whether the dock is folded.
        """
        content = self.widget()
        if folded and not self.folded and content is not None and content.height() > 0:
            self.height_before = max(self.height(), self.title_bar.sizeHint().height() * 3)
        self.folded = folded
        if content is not None:
            content.setMaximumHeight(0 if folded else QWIDGETSIZE_MAX)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow if folded else Qt.ArrowType.DownArrow)
        self.toggle.setToolTip(f"Show the {self.toggle.text().lower()}" if folded else "Fold the panel to its title")
        self.toggle.setAccessibleName(f"{self.toggle.text()}, {'folded' if folded else 'expanded'}")
        title_height = self.title_bar.sizeHint().height()
        self.setMaximumHeight(title_height if folded else QWIDGETSIZE_MAX)
        self._fit_height()
        self.logger.debug("Dock %s %s.", self.key, "folded" if folded else "unfolded")

    ############################
    # Publicly Exposed Methods #
    ############################

    def fit_height(self) -> None:
        """Give the docked dock its height (its title bar while folded), once the window holds it."""
        self._fit_height()

    def set_folded(self, folded: bool) -> None:
        """Fold or unfold the dock, and remember it.

        Args:
            folded (bool): Whether only the title bar is shown.
        """
        if folded == self.folded:
            return
        self._apply(folded)
        self.store.set_expanded(self.key, not folded)
        self.folded_changed.emit(folded)

    def is_folded(self) -> bool:
        """Tell whether the dock is folded.

        Returns:
            bool: Whether only the title bar is shown.
        """
        return self.folded

    def reveal(self) -> None:
        """Show the dock, unfolded, even after it was hidden."""
        self.logger.debug("Revealing the dock %s.", self.key)
        self.show()
        self.raise_()
        self.set_folded(False)
