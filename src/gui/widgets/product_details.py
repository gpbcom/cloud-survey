from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

# First Party Imports.
from gui.product_model.product_row import ProductRow
from gui.theme import Theme


class ProductDetails(QFrame):
    """Details of the selected product.

    Attributes:
        copied (pyqtSignal): Emitted with the copied text when the product is copied to the clipboard.
        theme (Theme): The application theme.
        row (Optional[ProductRow]): The shown product.
        name_label (QLabel): The product name.
        provider_label (QLabel): The provider chip.
        flag_label (QLabel): The flag of the provider country.
        country_label (QLabel): The provider country.
        crawled_label (QLabel): The crawl date.
        history_label (QLabel): When the product was added, updated and deleted, and where the dates come from.
        description_label (QLabel): The product description.
        copy_button (QPushButton): Copies the product to the clipboard.
    """

    copied = pyqtSignal(str)

    def __init__(self, theme: Theme) -> None:
        """Build the panel, without product.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.setObjectName("details")
        self.setMinimumWidth(300)
        self.theme = theme
        self.row: Optional[ProductRow] = None
        self.name_label = QLabel()
        self.name_label.setObjectName("title")
        self.name_label.setWordWrap(True)
        self.provider_label = QLabel()
        self.flag_label = QLabel()
        self.country_label = QLabel()
        self.country_label.setObjectName("muted")
        self.crawled_label = QLabel()
        self.crawled_label.setObjectName("muted")
        self.history_label = QLabel()
        self.history_label.setObjectName("muted")
        self.history_label.setWordWrap(True)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_button = QPushButton("Copy to clipboard")
        self.copy_button.clicked.connect(self.copy)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        chip_row = QHBoxLayout()
        chip_row.addWidget(self.provider_label)
        chip_row.addSpacing(8)
        chip_row.addWidget(self.flag_label)
        chip_row.addWidget(self.country_label)
        chip_row.addStretch(1)
        layout.addWidget(self.name_label)
        layout.addLayout(chip_row)
        for widget in (self.crawled_label, self.history_label, self.description_label):
            layout.addWidget(widget)
        layout.addStretch(1)
        layout.addWidget(self.copy_button)
        self.show_row(None)

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_row(self, row: Optional[ProductRow]) -> None:
        """Show a product, or the placeholder when no product is selected.

        Args:
            row (Optional[ProductRow]): The product to show.
        """
        self.row = row
        self.copy_button.setEnabled(row is not None)
        if row is None:
            self.name_label.setText("No product selected")
            self.provider_label.setText("")
            self.provider_label.setStyleSheet("")
            self.flag_label.clear()
            self.country_label.setText("")
            self.crawled_label.setText("")
            self.history_label.setText("")
            self.description_label.setText("Select a product in the table to see its details.")
            return
        color = self.theme.PROVIDER_COLORS[row.provider]
        self.name_label.setText(row.product.name)
        self.provider_label.setText(f"  {self.theme.provider_label(row.provider)}  ")
        self.provider_label.setStyleSheet(
            f"background-color: {color}; color: #11151c; border-radius: 9px; padding: 3px; font-weight: 600;"
        )
        self.flag_label.setPixmap(self.theme.flag_pixmap(row.provider.country, 14))
        self.country_label.setText(self.theme.country_label(row.provider.country))
        self.crawled_label.setText(f"Crawled on {row.crawled_at.astimezone().strftime('%d %b %Y at %H:%M')}")
        self.history_label.setText(self.theme.history_text(row.product))
        self.description_label.setText(row.product.description)

    def copy(self) -> None:
        """Copy the shown product (provider, name and description) to the clipboard."""
        if self.row is None:
            return
        provider = self.theme.provider_label(self.row.provider)
        text = f"{provider} \u2014 {self.row.product.name}: {self.row.product.description}"
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.copied.emit(text)
