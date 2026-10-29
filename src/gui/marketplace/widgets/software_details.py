from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gui.marketplace.model.software_row import SoftwareRow
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme

# First Party Imports.
from gui.widgets.details.detail_sheet import Chip, DetailSheet
from gui.widgets.details.history.version_history import VersionHistory
from models.storage.enums import DatasetKind, ItemFilter


class SoftwareDetails(QFrame):
    """Details of the selected marketplace software: every field of its listing, its labels filtering the table.

    Attributes:
        copied (pyqtSignal): Emitted with the copied text when the software is copied to the clipboard.
        filter_requested (pyqtSignal): Emitted with an `ItemFilter` value and the value to filter the table on, when
            a chip (publisher, delivery, audience, type, marketplace category) is clicked.
        theme (Theme): The application theme.
        sheet (DetailSheet): The writer of the rich text fields.
        row (Optional[SoftwareRow]): The shown software.
        name_label (QLabel): The software name.
        provider_label (QLabel): The provider chip.
        flag_label (QLabel): The flag of the provider country.
        country_label (QLabel): The provider country.
        categories_label (QLabel): The unified categories and the source labels, clickable chips.
        facts_label (QLabel): The publisher and the delivery method, clickable chips.
        chips_label (QLabel): The audience and type chips, clickable.
        marketplace_label (QLabel): The categories given by the marketplace (flat labels and taxonomy), clickable.
        description_label (QLabel): The software description.
        link_label (QLabel): The link to the marketplace page.
        history (VersionHistory): The stored versions of the software, one row per crawl which changed it (hidden
            without storage thread).
        history_label (QLabel): When the software was added, updated and deleted, and where the dates come from.
        caveat_label (QLabel): The warnings about the approximate dates, empty when there is none.
        crawled_label (QLabel): The crawl date of the marketplace.
        body (QScrollArea): Scrolls the fields when they do not fit the panel.
        copy_button (QPushButton): Copies the software to the clipboard.
        taxonomy (TaxonomyCache): The names of the categories and of the source labels.
        logger (Logger): The panel logger.

    Notes:
        The rich text fields are selectable,
        their links open (web pages) or
        filter the software table (chips).
    """

    copied = pyqtSignal(str)
    filter_requested = pyqtSignal(str, str)

    def __init__(
        self,
        theme: Theme,
        logger: Optional[Logger] = None,
        taxonomy: Optional[TaxonomyCache] = None,
        loop: Optional[StorageLoop] = None,
    ) -> None:
        """Build the panel, without software.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The panel logger.
            taxonomy (Optional[TaxonomyCache]): The names of the categories, those of the seed by default.
            loop (Optional[StorageLoop]): The storage thread of the GUI, reading the versions of the software
                (`None` hides the History section).
        """
        super().__init__()
        self.setObjectName("details")
        self.setMinimumWidth(240)
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.sheet = DetailSheet(theme, self.logger)
        self.taxonomy = taxonomy if taxonomy else TaxonomyCache(logger=self.logger)
        self.taxonomy.changed.connect(self.refresh_names)
        self.row: Optional[SoftwareRow] = None
        self.name_label = QLabel()
        self.name_label.setObjectName("title")
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.provider_label = QLabel()
        self.flag_label = QLabel()
        self.country_label = QLabel()
        self.country_label.setObjectName("muted")
        self.country_label.setWordWrap(True)
        self.categories_label = self._rich_label()
        self.facts_label = self._rich_label()
        self.chips_label = self._rich_label()
        self.marketplace_label = self._rich_label()
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.link_label = self._rich_label()
        self.history_label = QLabel()
        self.history_label.setObjectName("muted")
        self.history_label.setWordWrap(True)
        self.history = VersionHistory(loop, self.logger)
        self.caveat_label = QLabel()
        self.caveat_label.setObjectName("warning")
        self.caveat_label.setWordWrap(True)
        self.crawled_label = QLabel()
        self.crawled_label.setObjectName("muted")
        self.crawled_label.setWordWrap(True)
        self.copy_button = QPushButton("Copy to clipboard")
        self.copy_button.clicked.connect(self.copy)
        fields = QWidget()
        column = QVBoxLayout(fields)
        column.setContentsMargins(0, 0, 6, 0)
        column.setSpacing(12)
        for label in (
            self.categories_label,
            self.facts_label,
            self.chips_label,
            self.marketplace_label,
            self.description_label,
            self.link_label,
            self.history_label,
            self.history,
            self.caveat_label,
            self.crawled_label,
        ):
            column.addWidget(label)
        column.addStretch(1)
        self.body = QScrollArea()
        self.body.setWidget(fields)
        self.body.setWidgetResizable(True)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        chip_row = QHBoxLayout()
        for widget in (self.provider_label, self.flag_label, self.country_label):
            chip_row.addWidget(widget)
        chip_row.addStretch(1)
        layout.addWidget(self.name_label)
        layout.addLayout(chip_row)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.copy_button)
        self.show_row(None)

    ############################
    # Internal Helpers Methods #
    ############################

    def _rich_label(self) -> QLabel:
        """Build a rich text field, its links handled by the panel.

        Returns:
            QLabel: The label, word wrapped and selectable.
        """
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.linkActivated.connect(self._on_link)
        return label

    def _on_link(self, href: str) -> None:
        """Filter the table on a clicked chip, or open a clicked web page.

        Args:
            href (str): The clicked link.
        """
        parsed = self.sheet.read_href(href)
        if parsed is None:
            self.logger.info("Opening the marketplace page %s.", href)
            if not QDesktopServices.openUrl(QUrl(href)):
                self.logger.warning("The marketplace page %s cannot be opened.", href)
            return
        item_filter, value = parsed
        self.logger.info("Filtering the software on %s %r.", item_filter.value, value)
        self.filter_requested.emit(item_filter.value, value)

    def _facts(self, row: SoftwareRow) -> str:
        """Write the publisher and the delivery method.

        Args:
            row (SoftwareRow): The software row.

        Returns:
            str: The captioned chips, the publisher "Unknown publisher" (not clickable) when the marketplace gives
                none.
        """
        software = row.software
        publisher: Chip = (
            (software.publisher, ItemFilter.PUBLISHERS, software.publisher, None)
            if software.publisher
            else ("Unknown publisher", None, "", None)
        )
        delivery: Chip = (
            self.theme.delivery_label(software.delivery),
            ItemFilter.DELIVERIES,
            software.delivery.value,
            None,
        )
        return self.sheet.field("Publisher · delivery", self.sheet.chips([publisher, delivery]))

    def _chips(self, row: SoftwareRow) -> str:
        """Write the audience chips of a software.

        Args:
            row (SoftwareRow): The software row.

        Returns:
            str: The captioned chips, the audiences coloured.
        """
        chips: List[Chip] = [
            (
                self.theme.category_label(category),
                ItemFilter.CATEGORIES,
                category.value,
                self.theme.CATEGORY_COLORS[category],
            )
            for category in row.software.categories
        ]
        return self.sheet.field("Audience", self.sheet.chips(chips))

    def _marketplace(self, row: SoftwareRow) -> str:
        """Write where the software sits in the taxonomy of its marketplace, when the marketplace has one.

        Args:
            row (SoftwareRow): The software row.

        Returns:
            str: The captioned chips (one per taxonomy path, not filtering: the source labels filter), empty when the
                marketplace gives no path.
        """
        paths = row.software.marketplace_category_paths or []
        chips: List[Chip] = [(category.label(), None, "", None) for category in paths]
        return self.sheet.field("Marketplace taxonomy", self.sheet.chips(chips)) if chips else ""

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_row(self, row: Optional[SoftwareRow]) -> None:
        """Show a software, or the placeholder when no software is selected.

        Args:
            row (Optional[SoftwareRow]): The software to show.
        """
        self.row = row
        self.copy_button.setEnabled(row is not None)
        if row is None:
            self.name_label.setText("No software selected")
            for label in (
                self.provider_label,
                self.country_label,
                self.categories_label,
                self.facts_label,
                self.chips_label,
                self.marketplace_label,
                self.history_label,
                self.caveat_label,
                self.link_label,
                self.crawled_label,
            ):
                label.setText("")
            self.marketplace_label.setToolTip("")
            self.provider_label.setStyleSheet("")
            self.flag_label.clear()
            self.description_label.setText("Select a software in the table to see its details.")
            self.history.load(None, DatasetKind.MARKETPLACE)
            return
        software = row.software
        color = self.theme.PROVIDER_COLORS[row.provider]
        self.name_label.setText(software.name)
        self.provider_label.setText(f"  {self.theme.provider_label(row.provider)}  ")
        self.provider_label.setStyleSheet(
            f"background-color: {color}; color: #11151c; border-radius: 9px; padding: 3px; font-weight: 600;"
        )
        self.flag_label.setPixmap(self.theme.flag_pixmap(row.provider.country, 14))
        self.country_label.setText(self.theme.country_label(row.provider.country))
        self.categories_label.setText(self.sheet.categorization(software, self.taxonomy))
        self.facts_label.setText(self._facts(row))
        self.chips_label.setText(self._chips(row))
        self.marketplace_label.setText(self._marketplace(row))
        paths = software.marketplace_category_paths or []
        self.marketplace_label.setToolTip(
            "\n".join(f"{category.label()} ({category.id})" for category in paths if category.id)
        )
        self.history_label.setText(self.theme.history_text(software))
        self.history.load(row.id, DatasetKind.MARKETPLACE)
        self.caveat_label.setText(self.theme.caveat_text(software))
        self.description_label.setText(software.description)
        page = self.sheet.link(software.url, "Open the marketplace page")
        self.link_label.setText(self.sheet.field("Marketplace page", page))
        self.link_label.setToolTip(software.url or "")
        crawled = row.crawled_at.astimezone().strftime("%d %b %Y at %H:%M") if row.crawled_at else "an unknown date"
        self.crawled_label.setText(f"Marketplace crawled on {crawled}")
        self.logger.debug("Details of the software %r shown.", software.name)

    def refresh_names(self) -> None:
        """Show the shown software again with the category and label names read again."""
        if self.row is not None:
            self.logger.debug("Details of the software shown again with the new category names.")
            self.show_row(self.row)

    def copy(self) -> None:
        """Copy the shown software (provider, name, categories and description) to the clipboard."""
        if self.row is None:
            self.logger.debug("No software shown: nothing to copy.")
            return
        software = self.row.software
        categories = self.taxonomy.names(software.service_categories)
        provider = self.theme.provider_label(self.row.provider)
        text = f"{provider} — {software.name} ({categories}): {software.description}"
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.logger.info("Software %r copied to the clipboard.", software.name)
        else:
            self.logger.warning("No clipboard: the software %r is not copied.", software.name)
        self.copied.emit(text)
