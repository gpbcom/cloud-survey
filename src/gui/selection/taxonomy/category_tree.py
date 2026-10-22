from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

# First Party Imports.
from gui.taxonomy.taxonomy_cache import TaxonomyCache


class CategoryTree(QTreeWidget):
    """A tree of checkable categories under their domain: a domain checks or unchecks all its categories.

    Attributes:
        changed (pyqtSignal): Emitted when a category is checked or unchecked.
        cache (TaxonomyCache): The taxonomy shown.
        domain_items (Dict[str, QTreeWidgetItem]): The domain items (tri-state), by slug.
        category_items (Dict[str, QTreeWidgetItem]): The category items, under their domain, by slug.
        counts (Dict[str, int]): The number of items of each node, shown next to its name.
        logger (Logger): The tree logger.

    Notes:
        - Nothing checked means every category (no filter). A fully checked domain is picked as the domain itself,
          so that its items filed in the domain only (a source label telling the domain) are picked too.
        - The hidden categories (e.g. `Other`) are shown only when some item is filed under them.
        - The tree is built again when the taxonomy changes, keeping the checks.
    """

    changed = pyqtSignal()

    def __init__(self, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build the tree, nothing checked.

        Args:
            cache (TaxonomyCache): The taxonomy shown.
            logger (Optional[Logger]): The tree logger.
        """
        super().__init__()
        self.cache = cache
        self.logger = logger if logger else getLogger(__name__)
        self.domain_items: Dict[str, QTreeWidgetItem] = {}
        self.category_items: Dict[str, QTreeWidgetItem] = {}
        self.counts: Dict[str, int] = {}
        self.setHeaderHidden(True)
        self.setMinimumWidth(320)
        self.itemChanged.connect(self._on_item_changed)
        self.cache.changed.connect(self.rebuild)
        self.rebuild()

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, slug: str) -> str:
        """Get the text of a node: its name, with its count once known.

        Args:
            slug (str): The node slug.

        Returns:
            str: e.g. `Relational databases  (1,204)`, `(0)` for a node without items once the counts are read.
        """
        name = self.cache.name(slug)
        return f"{name}  ({self.counts.get(slug, 0):,})" if self.counts else name

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Tell that the checked categories changed, once per category change.

        Args:
            item (QTreeWidgetItem): The changed item.
            column (int): The changed column.
        """
        if item.parent() is not None:
            self.logger.debug("Category %s %s.", item.text(0), "checked" if item.checkState(0) else "unchecked")
            self.changed.emit()

    def _update_visibility(self) -> None:
        """Hide the hidden categories nothing is filed under, and the domains left empty."""
        taxonomy = self.cache.taxonomy
        for slug, item in self.category_items.items():
            node = taxonomy.node(slug)
            item.setHidden(node is not None and node.hidden and not self.counts.get(slug))
        for domain_item in self.domain_items.values():
            children = [domain_item.child(index) for index in range(domain_item.childCount())]
            domain_item.setHidden(all(child is None or child.isHidden() for child in children))

    ############################
    # Publicly Exposed Methods #
    ############################

    def checked(self) -> List[str]:
        """Get the checked categories.

        Returns:
            List[str]: Their slugs, in the order of the taxonomy.
        """
        return [slug for slug, item in self.category_items.items() if item.checkState(0) == Qt.CheckState.Checked]

    def rebuild(self) -> None:
        """Build the tree from the taxonomy, keeping the checked categories."""
        checked = self.checked()
        self.blockSignals(True)
        self.clear()
        self.domain_items.clear()
        self.category_items.clear()
        taxonomy = self.cache.taxonomy
        for domain in taxonomy.domains():
            domain_item = QTreeWidgetItem(self, [self._text(domain.slug)])
            domain_item.setData(0, Qt.ItemDataRole.UserRole, domain.slug)
            domain_item.setToolTip(0, domain.description_en)
            domain_item.setFlags(domain_item.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
            self.domain_items[domain.slug] = domain_item
            for node in taxonomy.children(domain.slug):
                item = QTreeWidgetItem(domain_item, [self._text(node.slug)])
                item.setData(0, Qt.ItemDataRole.UserRole, node.slug)
                item.setToolTip(0, node.description_en)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if node.slug in checked else Qt.CheckState.Unchecked)
                self.category_items[node.slug] = item
        self._update_visibility()
        self.blockSignals(False)
        self.logger.debug(
            "Category tree built: %d domains, %d categories.", len(self.domain_items), len(self.category_items)
        )

    def picked(self) -> List[str]:
        """Get the picked nodes: the fully checked domains, and the checked categories of the others.

        Returns:
            List[str]: The slugs of the picked domains and categories, empty when nothing is checked (no filter).
        """
        picked: List[str] = []
        for slug, domain_item in self.domain_items.items():
            children = [child for index in range(domain_item.childCount()) if (child := domain_item.child(index))]
            states = [child.checkState(0) == Qt.CheckState.Checked for child in children if not child.isHidden()]
            if states and all(states):
                picked.append(slug)
            else:
                picked.extend(
                    str(child.data(0, Qt.ItemDataRole.UserRole))
                    for child in children
                    if child.checkState(0) == Qt.CheckState.Checked
                )
        return picked

    def set_picked(self, slugs: Sequence[str]) -> None:
        """Check some nodes only (a domain checks all its categories), telling once.

        Args:
            slugs (Sequence[str]): The slugs of the domains and categories to check, the others being unchecked.
        """
        chosen = set(slugs)
        self.blockSignals(True)
        for slug, item in self.category_items.items():
            domain = self.cache.taxonomy.domain_of(slug)
            checked = slug in chosen or domain in chosen
            item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.blockSignals(False)
        self.logger.debug("%d taxonomy nodes picked.", len(chosen))
        self.changed.emit()

    def set_counts(self, counts: Dict[str, int]) -> None:
        """Show the number of items of each domain and category next to its name.

        Args:
            counts (Dict[str, int]): The number of items of each node (see `ItemRepository.category_counts`).
        """
        self.counts = dict(counts)
        self.blockSignals(True)
        for slug, item in [*self.domain_items.items(), *self.category_items.items()]:
            item.setText(0, self._text(slug))
        self._update_visibility()
        self.blockSignals(False)
        self.logger.debug("Category counts shown: %d nodes.", len(counts))

    def filter(self, text: str) -> None:
        """Show only the categories (and domains) whose name contains a text, the others hidden.

        Args:
            text (str): The searched text, case-insensitive, empty to show everything.
        """
        wanted = text.strip().casefold()
        if not wanted:
            self._update_visibility()
            self.collapseAll()
            return
        for slug, domain_item in self.domain_items.items():
            domain_matches = wanted in self.cache.name(slug).casefold()
            shown = 0
            for index in range(domain_item.childCount()):
                child = domain_item.child(index)
                if child is None:
                    continue
                child_slug = str(child.data(0, Qt.ItemDataRole.UserRole))
                matches = domain_matches or wanted in self.cache.name(child_slug).casefold()
                child.setHidden(not matches)
                shown += int(matches)
            domain_item.setHidden(shown == 0)
            domain_item.setExpanded(shown > 0)
        self.logger.debug("Category tree filtered on %r.", text)
