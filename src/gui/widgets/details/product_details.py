from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gui.product_model.product_row import ProductRow
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme

# First Party Imports.
from gui.widgets.details.detail_sheet import DetailSheet
from models.cloud.enums import PricingPolicy


class ProductDetails(QFrame):
    """Details of the selected product: everything its catalogue tells, its categories filtering the table.

    Attributes:
        PRICING_UNITS (ClassVar[Dict[PricingPolicy, str]]): What each pricing policy bills.
        copied (pyqtSignal): Emitted with the copied text when the product is copied to the clipboard.
        filter_requested (pyqtSignal): Emitted with an `ItemFilter` value and the value to filter the table on, when
            a category chip is clicked.
        theme (Theme): The application theme.
        sheet (DetailSheet): The writer of the rich text fields.
        row (Optional[ProductRow]): The shown product.
        name_label (QLabel): The product name.
        provider_label (QLabel): The provider chip.
        flag_label (QLabel): The flag of the provider country.
        country_label (QLabel): The provider country.
        categories_label (QLabel): The unified categories and the categories of the catalogue of the provider
            (source labels), clickable chips.
        taxonomy (TaxonomyCache): The names of the categories and of the source labels.
        description_label (QLabel): The product description.
        pricing_label (QLabel): The pricing policies, empty when the catalogue gives none.
        link_label (QLabel): The link to the product page, empty without page.
        history_label (QLabel): When the product was added, updated and deleted, and where the dates come from.
        caveat_label (QLabel): The warnings about the approximate dates, empty when there is none.
        crawled_label (QLabel): The crawl date.
        body (QScrollArea): Scrolls the fields when they do not fit the panel.
        copy_button (QPushButton): Copies the product to the clipboard.
        logger (Logger): The panel logger.

    Notes:
        - The rich text fields are selectable, their links open (web pages) or filter the product table (chips).
        - A product the catalogue files under no category says so, rather than hiding the field.
    """

    PRICING_UNITS: ClassVar[Dict[PricingPolicy, str]] = {
        PricingPolicy.BY_ARTIFACT: "per artifact",
        PricingPolicy.BY_RESOURCE: "per resource",
    }

    copied = pyqtSignal(str)
    filter_requested = pyqtSignal(str, str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None, taxonomy: Optional[TaxonomyCache] = None) -> None:
        """Build the panel, without product.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The panel logger.
            taxonomy (Optional[TaxonomyCache]): The names of the categories, those of the seed by default.
        """
        super().__init__()
        self.setObjectName("details")
        self.setMinimumWidth(240)
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.sheet = DetailSheet(theme, self.logger)
        self.taxonomy = taxonomy if taxonomy else TaxonomyCache(logger=self.logger)
        self.taxonomy.changed.connect(self.refresh_names)
        self.row: Optional[ProductRow] = None
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
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pricing_label = self._rich_label()
        self.link_label = self._rich_label()
        self.history_label = QLabel()
        self.history_label.setObjectName("muted")
        self.history_label.setWordWrap(True)
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
            self.description_label,
            self.pricing_label,
            self.link_label,
            self.history_label,
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
        chip_row.addWidget(self.provider_label)
        chip_row.addSpacing(8)
        chip_row.addWidget(self.flag_label)
        chip_row.addWidget(self.country_label)
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
            self.logger.info("Opening the product page %s.", href)
            if not QDesktopServices.openUrl(QUrl(href)):
                self.logger.warning("The product page %s cannot be opened.", href)
            return
        item_filter, value = parsed
        self.logger.info("Filtering the products on %s %r.", item_filter.value, value)
        self.filter_requested.emit(item_filter.value, value)

    def _categories(self, row: ProductRow) -> str:
        """Write the unified categories of the product and the categories of the catalogue of the provider.

        Args:
            row (ProductRow): The product row.

        Returns:
            str: The captioned chips, or notes when the product is not categorized or not filed under a category.
        """
        written = self.sheet.categorization(row.product, self.taxonomy)
        if row.product.catalogue_categories:
            return written
        muted = f'<span style="color:{self.theme.TEXT_MUTED};">Not given by the catalogue</span>'
        return written + self.sheet.field("Source labels", muted)

    def _pricing(self, row: ProductRow) -> str:
        """Write the pricing policies of a product.

        Args:
            row (ProductRow): The product row.

        Returns:
            str: One line per pricing policy, empty when the catalogue gives none.
        """
        lines = [
            f"{policy.amount:g} {policy.currency} {self.PRICING_UNITS[policy.pricing_policy]}"
            + (f", above {policy.free_limit:g} free" if policy.free_limit else "")
            for policy in row.product.pricing_policy
        ]
        return self.sheet.field("Pricing", self.sheet.lines("\n".join(lines)))

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
            for label in (
                self.provider_label,
                self.country_label,
                self.categories_label,
                self.pricing_label,
                self.link_label,
                self.crawled_label,
                self.history_label,
                self.caveat_label,
            ):
                label.setText("")
            self.provider_label.setStyleSheet("")
            self.flag_label.clear()
            self.description_label.setText("Select a product in the table to see its details.")
            return
        product = row.product
        color = self.theme.PROVIDER_COLORS[row.provider]
        self.name_label.setText(product.name)
        self.provider_label.setText(f"  {self.theme.provider_label(row.provider)}  ")
        self.provider_label.setStyleSheet(
            f"background-color: {color}; color: #11151c; border-radius: 9px; padding: 3px; font-weight: 600;"
        )
        self.flag_label.setPixmap(self.theme.flag_pixmap(row.provider.country, 14))
        self.country_label.setText(self.theme.country_label(row.provider.country))
        self.categories_label.setText(self._categories(row))
        self.description_label.setText(product.description)
        self.pricing_label.setText(self._pricing(row))
        page = self.sheet.link(product.url, "Open the product page")
        self.link_label.setText(self.sheet.field("Product page", page))
        self.link_label.setToolTip(product.url or "")
        crawled = row.crawled_at.astimezone().strftime("%d %b %Y at %H:%M") if row.crawled_at else "an unknown date"
        self.crawled_label.setText(f"Crawled on {crawled}")
        self.history_label.setText(self.theme.history_text(product))
        self.caveat_label.setText(self.theme.caveat_text(product))
        self.logger.debug("Details of the product %r shown.", product.name)

    def refresh_names(self) -> None:
        """Show the shown product again with the category and label names read again."""
        if self.row is not None:
            self.logger.debug("Details of the product shown again with the new category names.")
            self.show_row(self.row)

    def copy(self) -> None:
        """Copy the shown product (provider, name, categories and description) to the clipboard."""
        if self.row is None:
            return
        product = self.row.product
        provider = self.theme.provider_label(self.row.provider)
        categories = f" ({', '.join(product.catalogue_categories)})" if product.catalogue_categories else ""
        text = f"{provider} — {product.name}{categories}: {product.description}"
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.copied.emit(text)
