from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QWIDGETSIZE_MAX, QFrame, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget

# First Party Imports.
from gui.charts.sections.section.chart_section import ChartSection
from gui.layout.panes.folding_pane import FoldingPane


class SectionStack(FoldingPane):
    """Column of collapsible sections sharing its height: the expanded ones grow, the collapsed ones keep a header.

    Attributes:
        content (QWidget): The column of widgets and sections.
        column (QVBoxLayout): The layout of the column, its last item a spacer pushing the collapsed sections up.
        area (Optional[QScrollArea]): Scrolls the column when the sections do not fit, `None` for a column which
            never scrolls (a table, which scrolls itself).
        weights (Dict[ChartSection, int]): The share of the free height of each section, while it is expanded.
        fixed (List[QWidget]): The widgets of fixed height (e.g. headline figures), above the sections.
        folded (bool): Whether every section is collapsed.
        logger (Logger): The stack logger.

    Notes:
        - Each expanded section takes a share of the free height proportional to its weight, above its minimum (a
          chart keeps its minimum height: the column scrolls rather than squeezing it).
        - Once every section is collapsed the stack is folded: it is no taller than its headers, so that a
          `FoldingSplitter` gives the rest of the height to its other panes.
        - More generally, the stack is never taller than its content (the headers of the collapsed sections, the
          expanded charts which keep their natural height): the panes below stick to it. An expanded chart which
          grows (e.g. a trend chart) lifts that limit. The limit follows the content: its width (wrapping figures),
          its sections and their charts.
        - A capped stack (or a splitter of capped stacks) is centered by a box layout giving it more height than its
          maximum: the layout holding it ends with a spacer (`addStretch(0)`), which takes the rest, so that the
          stack sticks to the top.
    """

    def __init__(self, scrollable: bool = True, logger: Optional[Logger] = None) -> None:
        """Build an empty stack.

        Args:
            scrollable (bool): Whether the column scrolls when its sections do not fit.
            logger (Optional[Logger]): The stack logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.weights: Dict[ChartSection, int] = {}
        self.fixed: List[QWidget] = []
        self.folded = False
        self.content = QWidget()
        self.column = QVBoxLayout(self.content)
        self.column.setContentsMargins(0, 0, 8 if scrollable else 0, 0)
        self.column.setSpacing(16)
        self.column.addStretch(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.area: Optional[QScrollArea] = None
        if scrollable:
            self.area = QScrollArea()
            self.area.setWidget(self.content)
            self.area.setWidgetResizable(True)
            self.area.setFrameShape(QFrame.Shape.NoFrame)
            layout.addWidget(self.area)
        else:
            layout.addWidget(self.content)
        self.content.installEventFilter(self)
        self.logger.debug("Section stack built (%s).", "scrollable" if scrollable else "not scrollable")

    ############################
    # Internal Helpers Methods #
    ############################

    def _headers_height(self) -> int:
        """Get the height of the fixed widgets and of the collapsed sections.

        Returns:
            int: The height of its fixed widgets and section headers, in pixels.
        """
        self.column.activate()
        frame = 2 * self.area.frameWidth() if self.area is not None else 0
        return self.content.sizeHint().height() + frame

    def _widget_height(self, widget: QWidget, width: int) -> int:
        """Get the largest height a widget of the column needs.

        Args:
            widget (QWidget): A fixed widget or a section.
            width (int): The width of the column, in pixels.

        Returns:
            int: Its header (a collapsed section), its maximum height (an expanded section, unlimited when it grows)
                or its height at that width (a fixed widget), in pixels.
        """
        if isinstance(widget, ChartSection) and widget in self.weights:
            return widget.maximumHeight() if widget.is_expanded() else widget.sizeHint().height()
        if widget.hasHeightForWidth() and width > 0:
            return widget.heightForWidth(width)
        return widget.sizeHint().height()

    def _content_height(self) -> int:
        """Get the largest height the column needs.

        Returns:
            int: The height of its widgets, spacing and margins (and the frame of the scroll area), `QWIDGETSIZE_MAX`
                when an expanded section grows.
        """
        margins = self.column.contentsMargins()
        width = self.content.width() - margins.left() - margins.right()
        heights: List[int] = []
        for index in range(self.column.count()):
            item = self.column.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and not widget.isHidden():
                heights.append(self._widget_height(widget, width))
        if any(height >= QWIDGETSIZE_MAX for height in heights):
            return QWIDGETSIZE_MAX
        frame = 2 * self.area.frameWidth() if self.area is not None else 0
        spacing = self.column.spacing() * max(len(heights) - 1, 0)
        return sum(heights) + spacing + margins.top() + margins.bottom() + frame

    def _fit_splitter(self, height: int) -> None:
        """Give the stack exactly the height of its content in its splitter, the largest other pane taking the rest.

        Args:
            height (int): The height of the content, in pixels.
        """
        splitter = self.parentWidget()
        if not isinstance(splitter, QSplitter):
            return
        sizes, index = splitter.sizes(), splitter.indexOf(self)
        others = [other for other in range(len(sizes)) if other != index]
        if index < 0 or not others or sum(sizes) <= 0 or sizes[index] == height:
            return
        receiver = max(others, key=lambda other: sizes[other])
        sizes[receiver] += sizes[index] - height
        sizes[index] = height
        if sizes[receiver] > 0:
            splitter.setSizes(sizes)
            self.logger.debug("Section stack fitted to its content in its splitter: %s.", sizes)

    def _cap(self) -> None:
        """Keep the stack as tall as its content (no taller when it does not grow), the panes below sticking to it."""
        height = self._content_height()
        if height != self.maximumHeight():
            self.setMaximumHeight(height)
            self.logger.debug("Section stack capped at %s px.", "no" if height >= QWIDGETSIZE_MAX else height)
        if height < QWIDGETSIZE_MAX:
            self._fit_splitter(height)

    def _update(self) -> None:
        """Share the free height between the expanded sections, and fold the stack when none is expanded."""
        expanded = [section for section in self.weights if section.is_expanded()]
        for section, weight in self.weights.items():
            grows = section.is_expanded() and weight > 0
            self.column.setStretchFactor(section, weight if section.is_expanded() else 0)
            policy = QSizePolicy.Policy.Expanding if grows else QSizePolicy.Policy.Maximum
            section.setSizePolicy(QSizePolicy.Policy.Preferred, policy)
        growing = any(self.weights[section] > 0 for section in expanded)
        self.column.setStretch(self.column.count() - 1, 0 if growing else 1)
        folded = bool(self.weights) and not expanded
        self._cap()
        self.logger.debug("%d of %d sections expanded.", len(expanded), len(self.weights))
        if folded != self.folded:
            self.folded = folded
            self.logger.debug("Section stack %s.", "folded" if folded else "unfolded")
            self.folded_changed.emit(folded)

    ############################
    # Publicly Exposed Methods #
    ############################

    def add_widget(self, widget: QWidget) -> QWidget:
        """Add a widget of fixed height below the others (e.g. headline figures).

        Args:
            widget (QWidget): The widget.

        Returns:
            QWidget: The same widget.
        """
        self.column.insertWidget(self.column.count() - 1, widget, 0)
        self.fixed.append(widget)
        self._cap()
        return widget

    def add_section(self, section: ChartSection, weight: int = 1) -> ChartSection:
        """Add a collapsible section below the others.

        Args:
            section (ChartSection): The section.
            weight (int): Its share of the free height while expanded,
                `0` to keep its natural height.

        Returns:
            ChartSection: The same section.
        """
        self.weights[section] = weight
        self.column.insertWidget(self.column.count() - 1, section, weight)
        section.toggled.connect(lambda key, expanded: self._update())
        self._update()
        self.logger.debug("Section %s added to the stack (weight %d).", section.key, weight)
        return section

    def stacked_sections(self) -> List[ChartSection]:
        """Get the sections of the stack.

        Returns:
            List[ChartSection]: The sections, top to bottom.
        """
        return list(self.weights)

    def is_folded(self) -> bool:
        """Tell whether every section is collapsed.

        Returns:
            bool: Whether the stack only shows headers.
        """
        return self.folded

    def folds_along(self) -> Qt.Orientation:
        """Tell along which direction the stack folds.

        Returns:
            Qt.Orientation: `Vertical`, it folds to the headers of its sections.
        """
        return Qt.Orientation.Vertical

    def folded_extent(self) -> int:
        """Get the height of the stack once folded.

        Returns:
            int: The height of its fixed widgets (at their width: wrapping figures take several rows) and section
                headers, in pixels.
        """
        height = self._content_height()
        return height if height < QWIDGETSIZE_MAX else self._headers_height()

    def eventFilter(self, watched: Optional[QObject], event: Optional[QEvent]) -> bool:
        """Follow the content: its width (wrapping figures), its sections and their charts (Qt override).

        Args:
            watched (Optional[QObject]): The column of widgets and sections.
            event (Optional[QEvent]): The event.

        Returns:
            bool: Always `False`: the column handles the event too.
        """
        follows = event is not None and event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Resize)
        if watched is self.content and follows:
            self._cap()
        return False
