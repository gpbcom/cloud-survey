from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

# First Party Imports.
from gui.marketplace.software_row import SoftwareRow
from gui.marketplace.software_table_model import ModelIndex, SoftwareTableModel
from models.cloud.enums import CloudProvider, Country, DeliveryMethod, SoftwareCategory, SoftwareType


class SoftwareFilterModel(QSortFilterProxyModel):
    """Search, provider, country, category, type and delivery filters of the software table, sortable.

    Attributes:
        table (SoftwareTableModel): The filtered software table.
        search (str): The case-insensitive text searched in the software name, description and publisher.
        provider (Optional[CloudProvider]): The only provider shown, `None` for all of them.
        country (Optional[Country]): The only provider country shown, `None` for all of them.
        category (Optional[SoftwareCategory]): The only software category shown, `None` for all of them.
        kind (Optional[SoftwareType]): The only software type shown, `None` for all of them.
        delivery (Optional[DeliveryMethod]): The only delivery method shown, `None` for all of them.
        show_deleted (bool): Whether the software deleted from its marketplace is shown, hidden by default.
    """

    def __init__(self, source: SoftwareTableModel, logger: Optional[Logger] = None) -> None:
        """Initialize the filter of a software table, showing everything.

        Args:
            source (SoftwareTableModel): The filtered software table.
            logger (Optional[Logger]): The model logger.
        """
        super().__init__()
        self.table = source
        self.setSourceModel(source)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.logger = logger if logger else getLogger(__name__)
        self.search = ""
        self.provider: Optional[CloudProvider] = None
        self.country: Optional[Country] = None
        self.category: Optional[SoftwareCategory] = None
        self.kind: Optional[SoftwareType] = None
        self.delivery: Optional[DeliveryMethod] = None
        self.show_deleted = False

    ############################
    # Internal Helpers Methods #
    ############################

    def _accepts(self, row: SoftwareRow) -> bool:
        """Tell whether a software matches every filter.

        Args:
            row (SoftwareRow): The software row.

        Returns:
            bool: Whether the software is shown.
        """
        software = row.software
        return (
            (self.show_deleted or not software.is_deleted)
            and (self.provider is None or row.provider is self.provider)
            and (self.country is None or row.provider.country is self.country)
            and (self.category is None or self.category in software.categories)
            and (self.kind is None or self.kind in software.types)
            and (self.delivery is None or software.delivery is self.delivery)
            and (not self.search or self.search in row.haystack)
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_filters(
        self,
        search: str = "",
        provider: Optional[CloudProvider] = None,
        country: Optional[Country] = None,
        category: Optional[SoftwareCategory] = None,
        kind: Optional[SoftwareType] = None,
        delivery: Optional[DeliveryMethod] = None,
        show_deleted: bool = False,
    ) -> None:
        """Show only the software matching every given filter.

        Args:
            search (str): The text searched in the name, description and publisher, case-insensitive.
            provider (Optional[CloudProvider]): The cloud provider, `None` for all of them.
            country (Optional[Country]): The provider country, `None` for all of them.
            category (Optional[SoftwareCategory]): The software category, `None` for all of them.
            kind (Optional[SoftwareType]): The software type, `None` for all of them.
            delivery (Optional[DeliveryMethod]): The delivery method, `None` for all of them.
            show_deleted (bool): Whether the software deleted from its marketplace is shown.
        """
        self.search = search.strip().casefold()
        self.provider, self.country, self.category = provider, country, category
        self.kind, self.delivery, self.show_deleted = kind, delivery, show_deleted
        self.logger.debug(
            "Marketplace filters: search %r, provider %s, country %s, category %s, type %s, delivery %s, deleted %s.",
            self.search,
            provider,
            country,
            category,
            kind,
            delivery,
            show_deleted,
        )
        self.invalidateFilter()

    def row_at(self, index: QModelIndex) -> Optional[SoftwareRow]:
        """Get the software row of a filtered index.

        Args:
            index (QModelIndex): The filtered table index.

        Returns:
            Optional[SoftwareRow]: The row, `None` for an invalid index.
        """
        return self.table.row_at(self.mapToSource(index))

    def filterAcceptsRow(self, source_row: int, source_parent: ModelIndex) -> bool:
        """Tell whether a software matches the filters (Qt override).

        Args:
            source_row (int): The software table row.
            source_parent (ModelIndex): The parent index.

        Returns:
            bool: Whether the software is shown.
        """
        return self._accepts(self.table.rows[source_row])
