from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

# First Party Imports.
from gui.selection.taxonomy.category_tree import CategoryTree
from gui.taxonomy.taxonomy_cache import TaxonomyCache


class CategoryPicker(QToolButton):
    """A drop-down of the unified categories under their domain, to filter on several of them at once.

    Attributes:
        TREE_HEIGHT (ClassVar[int]): The height of the drop-down tree, in pixels.
        TREE_WIDTH (ClassVar[int]): The width of the drop-down tree, in pixels (long names with their count).
        changed (pyqtSignal): Emitted when the picked categories change.
        cache (TaxonomyCache): The taxonomy offered.
        search_box (QLineEdit): Narrows the tree to the categories whose name contains a text.
        tree (CategoryTree): The checkable categories, under their domain.
        clear_button (QPushButton): Unchecks every category (no filter).
        logger (Logger): The picker logger.

    Notes:
        The same picker filters the products and the software: an item matches when it is filed under one of the
        picked categories or domains. The drop-down stays open while categories are checked.
    """

    TREE_HEIGHT: ClassVar[int] = 420
    TREE_WIDTH: ClassVar[int] = 380

    changed = pyqtSignal()

    def __init__(self, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build the picker, nothing picked.

        Args:
            cache (TaxonomyCache): The taxonomy offered.
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.cache = cache
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Find a category…")
        self.search_box.setClearButtonEnabled(True)
        self.tree = CategoryTree(cache, self.logger)
        self.tree.setMinimumHeight(self.TREE_HEIGHT)
        self.tree.setMinimumWidth(self.TREE_WIDTH)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip("Uncheck every category: no category filter")
        expand_button, collapse_button = QPushButton("Expand all"), QPushButton("Collapse all")
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.search_box)
        layout.addWidget(self.tree, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(expand_button)
        buttons.addWidget(collapse_button)
        buttons.addStretch(1)
        buttons.addWidget(self.clear_button)
        layout.addLayout(buttons)
        menu = QMenu(self)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        self.setMenu(menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("Show only the items of some categories or domains (several at once)")
        self.tree.changed.connect(self._on_tree_changed)
        self.search_box.textChanged.connect(self.tree.filter)
        self.clear_button.clicked.connect(self.reset)
        expand_button.clicked.connect(self.tree.expandAll)
        collapse_button.clicked.connect(self.tree.collapseAll)
        self.cache.changed.connect(self._update_text)
        self._update_text()
        self.logger.debug("Category picker built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _update_text(self) -> None:
        """Show what is picked on the button."""
        picked = self.tree.picked()
        if not picked:
            text = "All categories"
        elif len(picked) == 1:
            text = self.cache.name(picked[0])
        else:
            text = f"{len(picked)} categories"
        self.setText(f"{text}  ▾")
        self.setToolTip(
            "\n".join(self.cache.path(slug) for slug in picked)
            if picked
            else "Show only the items of some categories or domains (several at once)"
        )
        self.logger.debug("Category picker shows %r.", text)

    def _on_tree_changed(self) -> None:
        """Show the new pick, and tell it."""
        self._update_text()
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def picked(self) -> List[str]:
        """Get the picked domains and categories.

        Returns:
            List[str]: Their slugs (a fully checked domain as itself), empty when nothing is picked (no filter).
        """
        return self.tree.picked()

    def set_picked(self, slugs: Sequence[str]) -> None:
        """Pick some domains and categories only (e.g. a chip of the details panel was clicked).

        Args:
            slugs (Sequence[str]): Their slugs.
        """
        self.logger.info("Categories picked: %s.", ", ".join(slugs) or "none")
        self.tree.set_picked(slugs)

    def set_counts(self, counts: Dict[str, int]) -> None:
        """Show the number of items of each domain and category in the drop-down.

        Args:
            counts (Dict[str, int]): The number of items of each node.
        """
        self.tree.set_counts(counts)

    def reset(self) -> None:
        """Pick nothing again (no filter), telling once."""
        self.logger.debug("Category picker reset.")
        self.tree.set_picked([])
