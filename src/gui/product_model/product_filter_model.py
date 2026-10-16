from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

# First Party Imports.
from gui.product_model.product_row import ProductRow
from gui.product_model.product_table_model import ModelIndex, ProductTableModel
from models.cloud.enums import CloudProvider, Country


class ProductFilterModel(QSortFilterProxyModel):
    """Search, provider, country and deletion filter of the product table, sortable.

    Attributes:
        table (ProductTableModel): The filtered product table.
        search (str): The case-insensitive text searched in the products name and description.
        provider (Optional[CloudProvider]): The only provider shown, `None` for all of them.
        country (Optional[Country]): The only provider country shown, `None` for all of them.
        show_deleted (bool): Whether the products deleted from their website are shown, hidden by default.
    """

    def __init__(self, source: ProductTableModel) -> None:
        """Initialize the filter of a product table.

        Args:
            source (ProductTableModel): The filtered product table.
        """
        super().__init__()
        self.table = source
        self.setSourceModel(source)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search = ""
        self.provider: Optional[CloudProvider] = None
        self.country: Optional[Country] = None
        self.show_deleted = False

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_search(self, text: str) -> None:
        """Show only the products whose name or description contain a text.

        Args:
            text (str): The searched text, case-insensitive.
                Empty to show every product.
        """
        self.search = text.strip().casefold()
        self.invalidateFilter()

    def set_provider(self, provider: Optional[CloudProvider]) -> None:
        """Show only the products of a cloud provider.

        Args:
            provider (Optional[CloudProvider]): The cloud provider, `None` for all of them.
        """
        self.provider = provider
        self.invalidateFilter()

    def set_country(self, country: Optional[Country]) -> None:
        """Show only the products of the cloud providers of a country.

        Args:
            country (Optional[Country]): The country, `None` for all of them.
        """
        self.country = country
        self.invalidateFilter()

    def set_show_deleted(self, shown: bool) -> None:
        """Show or hide the products deleted from their website.

        Args:
            shown (bool): Whether the deleted products are shown.
        """
        self.show_deleted = shown
        self.invalidateFilter()

    def row_at(self, index: QModelIndex) -> Optional[ProductRow]:
        """Get the product row of a filtered index.

        Args:
            index (QModelIndex): The filtered table index.

        Returns:
            Optional[ProductRow]: The row, `None` for an invalid index.
        """
        return self.table.row_at(self.mapToSource(index))

    def filterAcceptsRow(self, source_row: int, source_parent: ModelIndex) -> bool:
        """Tell whether a product matches the provider, country and deletion filters and the search (Qt override).

        Args:
            source_row (int): The product table row.
            source_parent (ModelIndex): The parent index.

        Returns:
            bool: Whether the product is shown.
        """
        row = self.table.rows[source_row]
        if row.product.is_deleted and not self.show_deleted:
            return False
        if self.provider is not None and row.provider is not self.provider:
            return False
        if self.country is not None and row.provider.country is not self.country:
            return False
        return not self.search or self.search in f"{row.product.name}\n{row.product.description}".casefold()
