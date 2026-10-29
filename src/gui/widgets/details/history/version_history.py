from __future__ import annotations

# Standard Library Imports.
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from analytics.history.version_differ import VersionDiffer
from gui.storage_bridge.storage_loop import StorageLoop
from models.storage.enums import DatasetKind
from models.storage.versions.item_version import ItemVersion
from models.storage.versions.version_change import VersionChange
from storage.exception import StorageError


class VersionHistory(QWidget):
    """The History section of a details panel: one row per stored version of the shown product or software.

    Attributes:
        COLUMNS (ClassVar[Tuple[str, ...]]): The column titles.
        VISIBLE_ROWS (ClassVar[int]): The most rows shown before the table scrolls.
        ARROW (ClassVar[str]): The arrow between a value before and after a change.
        loop (Optional[StorageLoop]): The storage thread of the GUI, `None` to keep the section hidden.
        differ (VersionDiffer): The comparison of the versions.
        item_id (Optional[int]): The storage identifier of the shown item, `None` without item.
        kind (DatasetKind): What the shown item is (a catalogue product or a marketplace software).
        changes (List[VersionChange]): The changes of the shown item, the newest first.
        statuses (Dict[int, Optional[str]]): The status of the crawl of each shown version.
        expanded (bool): Whether the table is shown (kept from an item to the next).
        toggle (QToolButton): The section title, folding the table.
        status_label (QLabel): The loading, empty or error message.
        table (QTableWidget): The versions: date, crawl and changes, the details in the row tooltip.
        logger (Logger): The section logger.

    Notes:
        - The versions are read from the storage thread when an item is shown. An answer for an item no longer shown
          (the selection moved meanwhile) is dropped, and so is an answer reaching a deleted widget.
        - The versions are compared in the GUI thread (a few versions per item, cheap).
    """

    COLUMNS: ClassVar[Tuple[str, ...]] = ("Date", "Crawl", "Changes")
    VISIBLE_ROWS: ClassVar[int] = 8
    ARROW: ClassVar[str] = "→"

    def __init__(self, loop: Optional[StorageLoop] = None, logger: Optional[Logger] = None) -> None:
        """Build the section, hidden until an item is loaded with a storage thread.

        Args:
            loop (Optional[StorageLoop]): The storage thread of the GUI, `None` to keep the section hidden.
            logger (Optional[Logger]): The section logger.
        """
        super().__init__()
        self.loop = loop
        self.logger = logger if logger else getLogger(__name__)
        self.differ = VersionDiffer(self.logger)
        self.item_id: Optional[int] = None
        self.kind = DatasetKind.CATALOGUE
        self.changes: List[VersionChange] = []
        self.statuses: Dict[int, Optional[str]] = {}
        self.expanded = False
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle.clicked.connect(self.set_expanded)
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)  # type: ignore[union-attr]
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # type: ignore[union-attr]
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # type: ignore[union-attr]
        header.setStretchLastSection(True)  # type: ignore[union-attr]
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self.toggle)
        title_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(title_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)
        self.setVisible(False)
        self._show_title("History")

    ############################
    # Internal Helpers Methods #
    ############################

    def _apply(self) -> None:
        """Show or hide the table and the message as the section is folded."""
        self.toggle.setChecked(self.expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if self.expanded else Qt.ArrowType.RightArrow)
        self.toggle.setToolTip("Hide the versions" if self.expanded else "Show the versions crawled")
        self.toggle.setAccessibleName(f"{self.toggle.text()}, {'expanded' if self.expanded else 'collapsed'}")
        self.table.setVisible(self.expanded and bool(self.changes))
        self.status_label.setVisible(self.expanded and bool(self.status_label.text()))

    def _show_title(self, title: str) -> None:
        """Title the section, and fold it as chosen.

        Args:
            title (str): The title, e.g. `History (3 versions)`.
        """
        self.toggle.setText(title)
        self._apply()

    def _crawl(self, change: VersionChange) -> str:
        """Write the crawl of a version.

        Args:
            change (VersionChange): The change of the version.

        Returns:
            str: e.g. `#12 imported`, the status left out when unknown.
        """
        status = self.statuses.get(change.crawl_id)
        return f"#{change.crawl_id} {status}" if status else f"#{change.crawl_id}"

    def _summary(self, change: VersionChange) -> str:
        """Sum up a change in one line.

        Args:
            change (VersionChange): The change of a version.

        Returns:
            str: `First seen`, or the fields changed, added and removed.
        """
        if change.first:
            return "First seen"
        parts: List[str] = []
        if change.changed:
            parts.append("Changed " + ", ".join(field for field, _, _ in change.changed))
        if change.added:
            parts.append("added " + ", ".join(change.added))
        if change.removed:
            parts.append("removed " + ", ".join(change.removed))
        return " · ".join(parts) if parts else "No content change"

    def _tooltip(self, change: VersionChange) -> str:
        """Describe a change in full: the crawl and each field before and after.

        Args:
            change (VersionChange): The change of a version.

        Returns:
            str: One line per field.
        """
        when = change.recorded_at.astimezone().strftime("%d %b %Y at %H:%M")
        lines = [f"Crawl {self._crawl(change)} on {when}"]
        if change.first:
            lines.append("First seen: the content stored then.")
        lines.extend(f"{field}: {before} {self.ARROW} {after}" for field, before, after in change.changed)
        lines.extend(f"Added: {field}" for field in change.added)
        lines.extend(f"Removed: {field}" for field in change.removed)
        return "\n".join(lines)

    def _fill(self) -> None:
        """Write the changes in the table, its height fitted to at most `VISIBLE_ROWS` rows."""
        self.table.setRowCount(len(self.changes))
        for row, change in enumerate(self.changes):
            tooltip = self._tooltip(change)
            texts = (change.recorded_at.astimezone().strftime("%d %b %Y"), self._crawl(change), self._summary(change))
            for column, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                cell.setToolTip(tooltip)
                self.table.setItem(row, column, cell)
        self.table.resizeRowsToContents()
        header = self.table.horizontalHeader()
        shown = min(len(self.changes), self.VISIBLE_ROWS)
        rows = sum(self.table.rowHeight(row) for row in range(shown))
        self.table.setFixedHeight((header.height() if header else 0) + rows + 2 * self.table.frameWidth())

    def _clear(self) -> None:
        """Forget the shown versions."""
        self.changes = []
        self.statuses = {}
        self.table.setRowCount(0)

    def _on_read(self, item_id: int, kind: DatasetKind, versions: List[ItemVersion]) -> None:
        """Show the versions read, unless another item is shown meanwhile.

        Args:
            item_id (int): The item the versions were read for.
            kind (DatasetKind): What the item is.
            versions (List[ItemVersion]): Its versions, the newest first.
        """
        if sip.isdeleted(self):
            self.logger.debug("Versions of the %s item %d read for a closed panel: dropped.", kind.value, item_id)
            return
        if item_id != self.item_id or kind is not self.kind:
            self.logger.debug(
                "Versions of the %s item %d read after the selection moved: dropped.", kind.value, item_id
            )
            return
        self.changes = self.differ.changes(versions)
        self.statuses = {version.crawl_id: version.crawl_status for version in versions}
        count = len(self.changes)
        self.status_label.setText("" if count else "No version stored for this item.")
        self._fill()
        self._show_title(f"History ({count} version{'' if count == 1 else 's'})")
        self.logger.info("%d versions of the %s item %d shown.", count, kind.value, item_id)

    def _on_error(self, item_id: int, kind: DatasetKind, error: StorageError) -> None:
        """Say the versions cannot be read, unless another item is shown meanwhile.

        Args:
            item_id (int): The item the versions were read for.
            kind (DatasetKind): What the item is.
            error (StorageError): Why they cannot be read.
        """
        if sip.isdeleted(self) or item_id != self.item_id or kind is not self.kind:
            self.logger.debug("Read error of the versions of the %s item %d dropped: %s", kind.value, item_id, error)
            return
        self.logger.warning("The versions of the %s item %d cannot be read: %s", kind.value, item_id, error)
        self._clear()
        self.status_label.setText("The versions cannot be read from the storage.")
        self._show_title("History (unavailable)")

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the versions.

        Args:
            expanded (bool): Whether the table is shown.
        """
        self.expanded = expanded
        self.logger.debug("History section %s.", "expanded" if expanded else "collapsed")
        self._apply()

    def load(self, item_id: Optional[int], kind: DatasetKind) -> None:
        """Read the versions of an item, or hide the section without item.

        Args:
            item_id (Optional[int]): The storage identifier of the item, `None` (or 0, an item not stored) for none.
            kind (DatasetKind): What the item is (`catalogue` or `marketplace`).

        Notes:
            The shown versions stay until the answer when the same item is shown again (no flicker).
        """
        if self.loop is None or not item_id:
            self.item_id = None
            self._clear()
            self.setVisible(False)
            return
        if item_id != self.item_id or kind is not self.kind:
            self._clear()
            self.status_label.setText("Reading the versions…")
            self._show_title("History")
        self.item_id, self.kind = item_id, kind
        self.setVisible(True)
        if kind is DatasetKind.MARKETPLACE:
            self.loop.submit(
                lambda storage: storage.marketplaces.versions(item_id),
                partial(self._on_read, item_id, kind),
                partial(self._on_error, item_id, kind),
            )
        else:
            self.loop.submit(
                lambda storage: storage.catalogues.versions(item_id),
                partial(self._on_read, item_id, kind),
                partial(self._on_error, item_id, kind),
            )
        self.logger.debug("Versions of the %s item %d requested.", kind.value, item_id)
