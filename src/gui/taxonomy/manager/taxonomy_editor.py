from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.storage.pages.item_query import ItemQuery
from storage.exception import StorageError
from storage.storage import Storage


class TaxonomyEditor(QWidget):
    """The categories tab of the Categories manager: name, describe, add, hide, move and merge the nodes.

    Attributes:
        edited (pyqtSignal): Emitted once an edit is written and its items categorized again.
        message (pyqtSignal): Emitted with what happened, for the status line of the manager.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        cache (TaxonomyCache): The taxonomy shown, read again after each edit.
        tree (QTreeWidget): The domains and their categories, with their number of items.
        counts (Dict[str, int]): The number of items (products and software) of each node.
        name_en_box, name_ru_box, name_zh_box, description_box (QLineEdit): The names and description of the
            selected node.
        new_box (QLineEdit): The English name of a node to add.
        move_box (QComboBox): The domain to move the selected category to.
        merge_box (QComboBox): The node to merge the selected one into.
        hide_button (QPushButton): Hides the selected node from the pickers, or shows it again.
        buttons (List[QPushButton]): The buttons acting on the selected node.
        logger (Logger): The editor logger.

    Notes:
        - A node is never deleted (the items store its slug): it is hidden,
          or merged into another one (its label links move there, it is hidden).
        - The edited nodes are no longer overwritten by the seed of the project,
          which every edit applies first when it changed (the stored taxonomy is
          then the one shown, even before any crawl).
    """

    edited = pyqtSignal()
    message = pyqtSignal(str)
 
    def __init__(self, theme: Theme, loop: StorageLoop, cache: TaxonomyCache, logger: Optional[Logger] = None) -> None:   # noqa: E501
        """Build the tab from the cached taxonomy.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            cache (TaxonomyCache): The taxonomy shown.
            logger (Optional[Logger]): The editor logger.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.cache = cache
        self.logger = logger if logger else getLogger(__name__)
        self.counts: Dict[str, int] = {}
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Items"])
        self.tree.setColumnWidth(0, 380)
        self.name_en_box, self.name_ru_box, self.name_zh_box = QLineEdit(), QLineEdit(), QLineEdit()  # noqa: E501
        self.description_box = QLineEdit()
        self.description_box.setPlaceholderText("One line: what the items of the node are")
        self.new_box = QLineEdit()
        self.new_box.setPlaceholderText("English name of the new node")
        self.move_box, self.merge_box = QComboBox(), QComboBox()
        self.hide_button = QPushButton("Hide")
        self.buttons: List[QPushButton] = []
        self._build_layout()
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.cache.changed.connect(self._rebuild)
        self._rebuild()
        self.logger.debug("Taxonomy editor built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _load(self) -> None:
        """Read the taxonomy and the number of items of each node again."""
        self.logger.debug("Reading the taxonomy for the editor.")
        self.cache.load()
        self.loop.submit(self._counts_job, self._on_counts, self._on_error)

    def _current(self) -> Optional[str]:
        """Get the selected node.

        Returns:
            Optional[str]: Its slug, `None` without selection.
        """
        item = self.tree.currentItem()
        slug = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None  # noqa: E501
        return str(slug) if slug else None

    def _on_current_changed(self) -> None:
        """Show the names of the selected node, and enable the actions."""
        slug = self._current()
        node = self.cache.taxonomy.node(slug) if slug else None
        for button in self.buttons:
            button.setEnabled(node is not None)
        self.name_en_box.setText(node.name_en if node else "")
        self.name_ru_box.setText(node.name_ru if node else "")
        self.name_zh_box.setText(node.name_zh if node else "")
        self.description_box.setText(node.description_en if node else "")
        self.hide_button.setText("Show" if node is not None and node.hidden else "Hide")  # noqa: E501

    def _rebuild(self) -> None:
        """Show the cached taxonomy, keeping the selected node, and offer its nodes to move and merge into."""
        current = self._current()
        self.tree.blockSignals(True)
        self.tree.clear()
        muted = QColor(self.theme.TEXT_MUTED)
        selected: Optional[QTreeWidgetItem] = None
        taxonomy = self.cache.taxonomy
        for domain in taxonomy.domains():
            domain_item = QTreeWidgetItem(self.tree, [domain.name_en, f"{self.counts.get(domain.slug, 0):,}"])   # noqa: E501
            domain_item.setData(0, Qt.ItemDataRole.UserRole, domain.slug)
            domain_item.setToolTip(0, domain.description_en)
            selected = domain_item if domain.slug == current else selected
            for node in taxonomy.children(domain.slug):
                suffix = "  (hidden)" if node.hidden else ""
                item = QTreeWidgetItem(domain_item, [f"{node.name_en}{suffix}", f"{self.counts.get(node.slug, 0):,}"])
                item.setData(0, Qt.ItemDataRole.UserRole, node.slug)
                item.setToolTip(0, f"{node.description_en}\n{node.slug}")
                if node.hidden:
                    item.setForeground(0, muted)
                selected = item if node.slug == current else selected
        self.tree.blockSignals(False)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.move_box.clear()
        self.merge_box.clear()
        for domain in taxonomy.domains():
            self.move_box.addItem(domain.name_en, domain.slug)
            self.merge_box.addItem(domain.name_en, domain.slug)
            for node in taxonomy.children(domain.slug):
                if not node.hidden:
                    self.merge_box.addItem(self.cache.path(node.slug), node.slug)  # noqa: E501
        self._on_current_changed()
        self.logger.debug("Taxonomy editor shows %d nodes.", len(taxonomy.nodes))  # noqa: E501

    def _on_counts(self, counts: Dict[str, int]) -> None:
        """Show the number of items of each node.

        Args:
            counts (Dict[str, int]): The number of products and software of each node.
        """
        self.counts = counts
        self._rebuild()

    def _on_error(self, error: StorageError) -> None:
        """Report an edit or a read which failed.

        Args:
            error (StorageError): The error.
        """
        self.logger.warning("A taxonomy edit failed: %s", error)
        self.message.emit(f"The taxonomy cannot be changed: {error}")

    def _on_done(self, changed: int) -> None:
        """Read the taxonomy again once an edit is written, and tell the manager.

        Args:
            changed (int): The number of items categorized again.
        """
        self.logger.info("Taxonomy edit written: %d items categorized again.", changed)   # noqa: E501
        self.message.emit(f"Saved: {changed:,} items categorized again.")
        self._load()
        self.edited.emit()

    async def _counts_job(self, storage: Storage) -> Dict[str, int]:
        """Apply the seed when needed, then count the products and software of each node (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            Dict[str, int]: The number of listed items of each node.

        Notes:
            The seed makes the stored taxonomy the one the editor shows before any crawl wrote (one query when it is
            up to date).
        """
        await storage.seeder.seed()
        counts = await storage.catalogues.category_counts(ItemQuery())
        for slug, count in (await storage.marketplaces.category_counts(ItemQuery())).items():   # noqa: E501
            counts[slug] = counts.get(slug, 0) + count
        return counts

    async def _save_job(self, storage: Storage, slug: str, names: List[str]) -> int:
        """Write the names and description of a node (storage thread).

        Args:
            storage (Storage): The open storage.
            slug (str): The node.
            names (List[str]): Its English, Russian and Chinese names, then its description.

        Returns:
            int: The number of items categorized again (none: the items store the slugs).
        """
        await storage.seeder.seed()
        await storage.taxonomy.update(slug, *names)
        return 0

    async def _hide_job(self, storage: Storage, slug: str, hidden: bool) -> int:   # noqa: E501
        """Hide a node or show it again (storage thread).

        Args:
            storage (Storage): The open storage.
            slug (str): The node.
            hidden (bool): Whether it is hidden.

        Returns:
            int: The number of items categorized again (none).
        """
        await storage.seeder.seed()
        await storage.taxonomy.set_hidden(slug, hidden)
        return 0

    async def _move_job(self, storage: Storage, slug: str, parent: str) -> int:
        """Move a category under another domain, then categorize its items again (storage thread).

        Args:
            storage (Storage): The open storage.
            slug (str): The category.
            parent (str): Its new domain.

        Returns:
            int: The number of items categorized again.
        """
        await storage.seeder.seed()
        return await storage.recategorize(node_slugs=await storage.taxonomy.move_node(slug, parent))  # noqa: E501

    async def _merge_job(self, storage: Storage, slug: str, target: str) -> int:  # noqa: E501
        """Merge a node into another one, then categorize their items again (storage thread).

        Args:
            storage (Storage): The open storage.
            slug (str): The merged node.
            target (str): The node it is merged into.

        Returns:
            int: The number of items categorized again.
        """
        await storage.seeder.seed()
        return await storage.recategorize(node_slugs=await storage.taxonomy.merge_node(slug, target))  # noqa: E501

    async def _add_job(self, storage: Storage, name: str, parent: Optional[str]) -> int:  # noqa: E501
        """Add a node (storage thread).

        Args:
            storage (Storage): The open storage.
            name (str): Its English name.
            parent (Optional[str]): Its domain, `None` for a domain.

        Returns:
            int: The number of items categorized again (none: no label links it yet).
        """
        await storage.seeder.seed()
        await storage.taxonomy.create(name, parent)
        return 0

    def _on_save(self) -> None:
        """Write the names and the description of the selected node."""
        slug = self._current()
        boxes = (self.name_en_box, self.name_ru_box, self.name_zh_box, self.description_box)  # noqa: E501
        names = [box.text() for box in boxes]
        if slug is None or not names[0].strip():
            self.message.emit("The English name cannot be empty.")
            return
        self.message.emit("Saving the names…")
        self.loop.submit(lambda storage: self._save_job(storage, slug, names), self._on_done, self._on_error)  # noqa: E501

    def _on_hide(self) -> None:
        """Hide the selected node, or show it again."""
        slug = self._current()
        node = self.cache.taxonomy.node(slug) if slug else None
        if slug is None or node is None:
            return
        hidden = not node.hidden
        self.loop.submit(lambda storage: self._hide_job(storage, slug, hidden), self._on_done, self._on_error)  # noqa: E501

    def _on_move(self) -> None:
        """Move the selected category under the chosen domain."""
        slug, parent = self._current(), self.move_box.currentData()
        if slug is None or not parent or not self.cache.taxonomy.is_category(slug):
            self.message.emit("Choose a category to move under another domain.")     # noqa: E501
            return
        self.message.emit("Moving the category…")
        self.loop.submit(lambda storage: self._move_job(storage, slug, str(parent)), self._on_done, self._on_error)  # noqa: E501

    def _on_merge(self) -> None:
        """Merge the selected node into the chosen one."""
        slug, target = self._current(), self.merge_box.currentData()
        if slug is None or not target or slug == target:
            self.message.emit("Choose another node to merge the selected one into.")   # noqa: E501
            return
        self.message.emit("Merging the nodes…")
        self.loop.submit(lambda storage: self._merge_job(storage, slug, str(target)), self._on_done, self._on_error)  # noqa: E501

    def _on_add(self, category: bool) -> None:
        """Add a node named in the "New node" box: a category under the domain of the selection, or a domain.

        Args:
            category (bool): Whether a category is added (`False`: a domain).
        """
        name = self.new_box.text().strip()
        slug = self._current()
        parent = self.cache.taxonomy.domain_of(slug) if category and slug else None
        if not name or (category and parent is None):
            self.message.emit("Type the English name, and select a domain for a category.")
            return
        self.new_box.clear()
        self.message.emit(f"Adding {name!r}…")
        self.loop.submit(lambda storage: self._add_job(storage, name, parent), self._on_done, self._on_error)

    def _build_layout(self) -> None:
        """Lay the tree out on the left, the form and the actions on the right."""
        save = QPushButton("Save")
        save.setToolTip("Write the names and the description of the selected node")
        move = QPushButton("Move")
        move.setToolTip("Move the selected category under this domain")
        merge = QPushButton("Merge")
        merge.setToolTip("Move the label links of the selected node to this one, and hide it")
        add_category, add_domain = QPushButton("Add category"), QPushButton("Add domain")  # noqa: E501
        add_category.setToolTip("Add a category under the domain of the selected node")
        self.hide_button.setToolTip("Hide the selected node from the pickers (its items keep it), or show it again")
        self.buttons = [save, move, merge, self.hide_button]
        save.clicked.connect(self._on_save)
        move.clicked.connect(self._on_move)
        merge.clicked.connect(self._on_merge)
        self.hide_button.clicked.connect(self._on_hide)
        add_category.clicked.connect(lambda: self._on_add(True))
        add_domain.clicked.connect(lambda: self._on_add(False))
        form = QFormLayout()
        form.addRow("English", self.name_en_box)
        form.addRow("Russian", self.name_ru_box)
        form.addRow("Chinese", self.name_zh_box)
        form.addRow("Description", self.description_box)
        actions = QHBoxLayout()
        actions.addWidget(save)
        actions.addWidget(self.hide_button)
        form.addRow("", actions)
        move_row, merge_row, add_row = QHBoxLayout(), QHBoxLayout(), QHBoxLayout()  # noqa: E501
        move_row.addWidget(self.move_box, 1)
        move_row.addWidget(move)
        merge_row.addWidget(self.merge_box, 1)
        merge_row.addWidget(merge)
        add_row.addWidget(add_category)
        add_row.addWidget(add_domain)
        form.addRow("Move to", move_row)
        form.addRow("Merge into", merge_row)
        form.addRow("New node", self.new_box)
        form.addRow("", add_row)
        box = QGroupBox("Selected node")
        box.setLayout(form)
        box.setMinimumWidth(380)
        layout = QHBoxLayout(self)
        layout.addWidget(self.tree, 1)
        side = QVBoxLayout()
        side.addWidget(box)
        side.addStretch(1)
        layout.addLayout(side)
        self.logger.debug("Taxonomy editor laid out.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Read the taxonomy and the number of items of each node again."""
        self._load()
