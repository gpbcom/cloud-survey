from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWIDGETSIZE_MAX, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget  # noqa: E501

# First Party Imports.
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.layout.panes.folding_pane import FoldingPane


class SidePane(FoldingPane):
    """A side panel (the details of the selected item) which folds to a thin strip, giving its width to the others.

    Attributes:
        key (str): The pane key, e.g. `catalogue/details`, remembering whether it is folded.
        title (str): What the pane shows, read vertically on the strip while it is folded.
        store (ChartStateStore): The store remembering the folded state.
        content (QWidget): The panel shown while the pane is unfolded.
        toggle (QToolButton): Folds or unfolds the pane.
        strip_label (QLabel): The title of the pane, on the strip while it is folded.
        strip (QWidget): The strip holding the toggle, beside the panel.
        folded (bool): Whether only the strip is shown.
        logger (Logger): The pane logger.

    Notes:
        - The toggle takes the keyboard focus: Space or Enter folds and unfolds the pane.
        - The folded state is remembered by the store, from one session to the next.
    """

    def __init__(
        self,
        key: str,
        title: str,
        content: QWidget,
        store: ChartStateStore,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the pane, folded as it was left.

        Args:
            key (str): The pane key.
            title (str): What the pane shows.
            content (QWidget): The panel.
            store (ChartStateStore): The store remembering the folded state.
            logger (Optional[Logger]): The pane logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.key, self.title, self.store, self.content = key, title, store, content  # noqa: E501
        self.folded = False
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.strip_label = QLabel("\n".join(title))
        self.strip_label.setObjectName("muted")
        self.strip_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.strip = QWidget()
        strip_layout = QVBoxLayout(self.strip)
        strip_layout.setContentsMargins(0, 4, 0, 4)
        strip_layout.setSpacing(6)
        strip_layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignHCenter)
        strip_layout.addWidget(self.strip_label, 0, Qt.AlignmentFlag.AlignHCenter)
        strip_layout.addStretch(1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.strip)
        layout.addWidget(content, 1)
        self.toggle.clicked.connect(lambda: self.set_folded(not self.folded))
        self._apply(not store.expanded(key))

    ############################
    # Internal Helpers Methods #
    ############################

    def _strip_width(self) -> int:
        """Get the width of the strip.

        Returns:
            int: The width of the strip holding the toggle, in pixels.
        """
        return max(self.strip.sizeHint().width(), self.toggle.sizeHint().width()) + 4   # noqa: E501

    def _apply(self, folded: bool) -> None:
        """Show the panel, or only the strip.

        Args:
            folded (bool): Whether the pane is folded.
        """
        self.folded = folded
        self.content.setVisible(not folded)
        self.strip_label.setVisible(folded)
        self.toggle.setArrowType(Qt.ArrowType.LeftArrow if folded else Qt.ArrowType.RightArrow)
        tip = f"Show the {self.title.lower()}" if folded else f"Hide the {self.title.lower()}"
        self.toggle.setToolTip(tip)
        self.toggle.setAccessibleName(f"{self.title}, {'folded' if folded else 'shown'}")
        self.setMaximumWidth(self._strip_width() if folded else QWIDGETSIZE_MAX)
        self.logger.debug("Side pane %s %s.", self.key, "folded" if folded else "unfolded")

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_folded(self, folded: bool) -> None:
        """Fold or unfold the pane, and remember it.

        Args:
            folded (bool): Whether only the strip is shown.
        """
        if folded == self.folded:
            return
        self._apply(folded)
        self.store.set_expanded(self.key, not folded)
        self.folded_changed.emit(folded)

    def is_folded(self) -> bool:
        """Tell whether the pane is folded.

        Returns:
            bool: Whether only the strip is shown.
        """
        return self.folded

    def folds_along(self) -> Qt.Orientation:
        """Tell along which direction the pane folds.

        Returns:
            Qt.Orientation: `Horizontal`, it folds to a strip.
        """
        return Qt.Orientation.Horizontal

    def folded_extent(self) -> int:
        """Get the width of the pane once folded.

        Returns:
            int: The width of the strip, in pixels.
        """
        return self._strip_width()
