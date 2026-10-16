from __future__ import annotations

# Standard Library Imports.
import html
from typing import List, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

# First Party Imports.
from gui.marketplace.software_row import SoftwareRow
from gui.theme import Theme


class SoftwareDetails(QFrame):
    """Details of the selected marketplace software.

    Attributes:
        copied (pyqtSignal): Emitted with the copied text when the software is copied to the clipboard.
        theme (Theme): The application theme.
        row (Optional[SoftwareRow]): The shown software.
        name_label (QLabel): The software name.
        provider_label (QLabel): The provider chip.
        flag_label (QLabel): The flag of the provider country.
        country_label (QLabel): The provider country.
        facts_label (QLabel): The publisher and the delivery method.
        chips_label (QLabel): The category and type chips.
        marketplace_label (QLabel): The categories given by the marketplace.
        history_label (QLabel): When the software was added, updated and deleted, and where the dates come from.
        description_label (QLabel): The software description.
        link_label (QLabel): The link to the marketplace page.
        copy_button (QPushButton): Copies the software to the clipboard.
    """

    copied = pyqtSignal(str)

    def __init__(self, theme: Theme) -> None:
        """Build the panel, without software.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.setObjectName("details")
        self.setMinimumWidth(300)
        self.theme = theme
        self.row: Optional[SoftwareRow] = None
        self.name_label = QLabel()
        self.name_label.setObjectName("title")
        self.name_label.setWordWrap(True)
        self.provider_label = QLabel()
        self.flag_label = QLabel()
        self.country_label = QLabel()
        self.country_label.setObjectName("muted")
        self.facts_label = QLabel()
        self.facts_label.setObjectName("muted")
        self.facts_label.setWordWrap(True)
        self.chips_label = QLabel()
        self.chips_label.setWordWrap(True)
        self.chips_label.setTextFormat(Qt.TextFormat.RichText)
        self.marketplace_label = QLabel()
        self.marketplace_label.setObjectName("muted")
        self.marketplace_label.setWordWrap(True)
        self.history_label = QLabel()
        self.history_label.setObjectName("muted")
        self.history_label.setWordWrap(True)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.link_label = QLabel()
        self.link_label.setTextFormat(Qt.TextFormat.RichText)
        self.link_label.setOpenExternalLinks(True)
        self.copy_button = QPushButton("Copy to clipboard")
        self.copy_button.clicked.connect(self.copy)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        chip_row = QHBoxLayout()
        for widget in (self.provider_label, self.flag_label, self.country_label):
            chip_row.addWidget(widget)
        chip_row.addStretch(1)
        layout.addWidget(self.name_label)
        layout.addLayout(chip_row)
        labels = (self.facts_label, self.chips_label, self.marketplace_label, self.history_label)
        for label in (*labels, self.description_label):
            layout.addWidget(label)
        layout.addWidget(self.link_label)
        layout.addStretch(1)
        layout.addWidget(self.copy_button)
        self.show_row(None)

    ############################
    # Internal Helpers Methods #
    ############################

    def _chips(self, row: SoftwareRow) -> str:
        """Render the category and type chips of a software.

        Args:
            row (SoftwareRow): The software row.

        Returns:
            str: The rich text chips, the categories coloured.
        """
        chips: List[str] = []
        for category in row.software.categories:
            color = self.theme.CATEGORY_COLORS[category]
            chips.append(
                f'<span style="background-color:{color}; color:#11151c; font-weight:600;">&nbsp;'
                f"{html.escape(self.theme.category_label(category))}&nbsp;</span>"
            )
        for kind in row.software.types:
            chips.append(
                f'<span style="background-color:{self.theme.SURFACE_ALT};">&nbsp;'
                f"{html.escape(self.theme.type_label(kind))}&nbsp;</span>"
            )
        return " ".join(chips)

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
            for label in (self.provider_label, self.country_label, self.facts_label, self.chips_label):
                label.setText("")
            self.provider_label.setStyleSheet("")
            self.flag_label.clear()
            self.marketplace_label.setText("")
            self.history_label.setText("")
            self.link_label.setText("")
            self.description_label.setText("Select a software in the table to see its details.")
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
        publisher = software.publisher or "Unknown publisher"
        self.facts_label.setText(f"{publisher} \u00b7 {self.theme.delivery_label(software.delivery)}")
        self.chips_label.setText(self._chips(row))
        listed = ", ".join(software.marketplace_categories)
        self.marketplace_label.setText(f"Marketplace categories: {listed}" if listed else "")
        self.history_label.setText(self.theme.history_text(software))
        self.description_label.setText(software.description)
        url = html.escape(software.url or "", quote=True)
        self.link_label.setText(f'<a href="{url}">Open the marketplace page</a>' if software.url else "")

    def copy(self) -> None:
        """Copy the shown software (provider, name, types and description) to the clipboard."""
        if self.row is None:
            return
        software = self.row.software
        types = ", ".join(self.theme.type_label(kind) for kind in software.types)
        provider = self.theme.provider_label(self.row.provider)
        text = f"{provider} \u2014 {software.name} ({types}): {software.description}"
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.copied.emit(text)
