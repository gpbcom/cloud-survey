from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """Row of widgets which wraps onto further lines when the width runs out (e.g. a row of filters).

    Attributes:
        items (List[QLayoutItem]): The laid out items, in their order.
        gap (int): The space between two items, horizontally and vertically, in pixels.
        logger (Logger): The layout logger.

    Notes:
        - The layout is no wider than its widest item: a window holding it can always shrink to the screen (and be
          maximized), the items moving to the next lines instead.
        - On each line, the room left is shared between the horizontally expanding items (e.g. a search box).
        - Its height depends on its width (`heightForWidth`), so that its parents grow when it wraps.
    """

    def __init__(self, parent: Optional[QWidget] = None, gap: int = 8, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Build an empty layout.

        Args:
            parent (Optional[QWidget]): The widget laid out, if any.
            gap (int): The space between two items, in pixels.
            logger (Optional[Logger]): The layout logger.
        """
        super().__init__(parent)
        self.logger = logger if logger else getLogger(__name__)
        self.items: List[QLayoutItem] = []
        self.gap = gap
        self.setContentsMargins(0, 0, 0, 0)
        self.logger.debug("Flow layout ready, %d px between items.", gap)

    ############################
    # Internal Helpers Methods #
    ############################

    def _expands(self, item: QLayoutItem) -> bool:
        """Tell whether an item takes a share of the room left on its line.

        Args:
            item (QLayoutItem): The item.

        Returns:
            bool: Whether its widget expands horizontally.
        """
        widget = item.widget()
        return widget is not None and bool(widget.sizePolicy().expandingDirections() & Qt.Orientation.Horizontal) # noqa: E501

    def _place_line(self, line: List[QLayoutItem], left: int, top: int, width: int, height: int) -> None:
        """Give the items of a line their geometry, the room left shared between the expanding ones.

        Args:
            line (List[QLayoutItem]): The items of the line.
            left (int): The left of the line, in pixels.
            top (int): The top of the line, in pixels.
            width (int): The width of the line, in pixels.
            height (int): The height of the line, in pixels.
        """
        used = sum(item.sizeHint().width() for item in line) + self.gap * max(len(line) - 1, 0)
        expanding = [item for item in line if self._expands(item)]
        extra = max(width - used, 0) // len(expanding) if expanding else 0
        x = left
        for item in line:
            hint = item.sizeHint()
            item_width = min(hint.width() + (extra if item in expanding else 0), max(width, item.minimumSize().width()))
            item_height = min(max(hint.height(), item.minimumSize().height()), height)
            item.setGeometry(QRect(QPoint(x, top + (height - item_height) // 2), QSize(item_width, item_height)))
            x += item_width + self.gap

    def _arrange(self, rect: QRect, apply: bool) -> int:
        """Split the items into lines fitting a width, and place them when asked.

        Args:
            rect (QRect): The area of the layout.
            apply (bool): Whether the items are given their geometry, or only the height is computed.

        Returns:
            int: The height needed by the lines, margins included, in pixels.
        """
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())  # noqa: E501
        lines: List[List[QLayoutItem]] = [[]]
        used = 0
        for item in self.items:
            if item.isEmpty():
                continue
            width = item.sizeHint().width()
            if lines[-1] and used + self.gap + width > area.width():
                lines.append([])
                used = 0
            used += width + (self.gap if lines[-1] else 0)
            lines[-1].append(item)
        top = area.top()
        for line in (line for line in lines if line):
            height = max(item.sizeHint().height() for item in line)
            if apply:
                self._place_line(line, area.left(), top, area.width(), height)
            top += height + self.gap
        return max(top - self.gap - area.top(), 0) + margins.top() + margins.bottom()  # noqa: E501

    ############################
    # Publicly Exposed Methods #
    ############################

    def addItem(self, item: Optional[QLayoutItem]) -> None:
        """Add an item after the others (Qt override).

        Args:
            item (Optional[QLayoutItem]): The item.
        """
        if item is not None:
            self.items.append(item)

    def count(self) -> int:
        """Count the items (Qt override).

        Returns:
            int: The number of items.
        """
        return len(self.items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        """Get an item (Qt override).

        Args:
            index (int): Its position.

        Returns:
            Optional[QLayoutItem]: The item, `None` past the last one.
        """
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        """Remove an item (Qt override).

        Args:
            index (int): Its position.

        Returns:
            Optional[QLayoutItem]: The removed item, `None` past the last one.
        """
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self) -> Qt.Orientation:
        """Tell in which directions the layout grows beyond its size hint (Qt override).

        Returns:
            Qt.Orientation: No direction: the lines take their natural height.
        """
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Tell that the height of the layout depends on its width (Qt override).

        Returns:
            bool: `True`, a narrower layout wraps onto more lines.
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """Get the height of the layout for a width (Qt override).

        Args:
            width (int): The width, in pixels.

        Returns:
            int: The height of its lines, in pixels.
        """
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect) -> None:
        """Lay the items out in an area (Qt override).

        Args:
            rect (QRect): The area.
        """
        super().setGeometry(rect)
        self._arrange(rect, True)

    def minimumSize(self) -> QSize:
        """Get the smallest size of the layout: its widest item, on a line of its own (Qt override).

        Returns:
            QSize: The size, margins included.
        """
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())  # noqa: E501

    def sizeHint(self) -> QSize:
        """Get the preferred size of the layout: every item on one line (Qt override).

        Returns:
            QSize: The size, margins included.
        """
        visible = [item for item in self.items if not item.isEmpty()]
        width = sum(item.sizeHint().width() for item in visible) + self.gap * max(len(visible) - 1, 0)
        height = max((item.sizeHint().height() for item in visible), default=0)
        margins = self.contentsMargins()
        self.logger.debug("Flow layout of %d items prefers %d px.", len(visible), width)
        return QSize(width + margins.left() + margins.right(), height + margins.top() + margins.bottom())
