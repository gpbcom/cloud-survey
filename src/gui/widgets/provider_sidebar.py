from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

# First Party Imports.
from gui.theme import Theme
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider, Country


class ProviderSidebar(QListWidget):
    """List of the cloud providers, grouped by country, with their catalogue state, to filter the products.

    Attributes:
        COUNTRY_ROLE (ClassVar[int]): The item data role holding the country code of a country header.
        provider_changed (pyqtSignal): Emitted with the selected provider value, empty for none.
        country_changed (pyqtSignal): Emitted with the country of the selection (a country header or a provider),
            empty for all of them.
        theme (Theme): The application theme.
        all_item (QListWidgetItem): The "All providers" item.
        country_items (Dict[Country, QListWidgetItem]): The country headers, with their flag.
        provider_items (Dict[CloudProvider, QListWidgetItem]): The provider items, under their country header.
    """

    COUNTRY_ROLE: ClassVar[int] = Qt.ItemDataRole.UserRole + 1

    provider_changed = pyqtSignal(str)
    country_changed = pyqtSignal(str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build the list, "All providers" selected.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The widget logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.setIconSize(QSize(18, 14))
        self.setMinimumWidth(250)
        self.all_item = QListWidgetItem(theme.dot_icon(QColor(theme.ACCENT)), "All providers")
        self.addItem(self.all_item)
        self.country_items: Dict[Country, QListWidgetItem] = {}
        self.provider_items: Dict[CloudProvider, QListWidgetItem] = {}
        header_font = QFont()
        header_font.setBold(True)
        for country in Country:
            header = QListWidgetItem(theme.flag_icon(country, 14), theme.country_label(country))
            header.setData(self.COUNTRY_ROLE, country.value)
            header.setFont(header_font)
            self.country_items[country] = header
            self.addItem(header)
            for provider in CloudProvider:
                if provider.country is not country:
                    continue
                item = QListWidgetItem(theme.provider_icon(provider), theme.provider_label(provider))
                item.setData(Qt.ItemDataRole.UserRole, provider.value)
                self.provider_items[provider] = item
                self.addItem(item)
        self.currentItemChanged.connect(self._on_current_item_changed)
        self.setCurrentItem(self.all_item)

    ############################
    # Internal Helpers Methods #
    ############################

    def _item_provider(self, item: Optional[QListWidgetItem]) -> Optional[CloudProvider]:
        """Get the cloud provider of an item.

        Args:
            item (Optional[QListWidgetItem]): The item.

        Returns:
            Optional[CloudProvider]: The provider, `None` for "All providers" and the country headers.
        """
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return CloudProvider(value) if value else None

    def _item_country(self, item: Optional[QListWidgetItem]) -> Optional[Country]:
        """Get the country of an item.

        Args:
            item (Optional[QListWidgetItem]): The item.

        Returns:
            Optional[Country]: The country of a header, or of a provider. `None` for "All providers".
        """
        if provider := self._item_provider(item):
            return provider.country
        value = item.data(self.COUNTRY_ROLE) if item else None
        return Country(value) if value else None

    def _on_current_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        """Emit the country and the provider of the new selection.

        Args:
            current (Optional[QListWidgetItem]): The selected item.
            previous (Optional[QListWidgetItem]): The previously selected item.
        """
        provider, country = self._item_provider(current), self._item_country(current)
        self.logger.debug(
            "Sidebar selection changed to %s.",
            provider.value if provider else country.value if country else "all providers",
        )
        self.country_changed.emit(country.value if country else "")
        self.provider_changed.emit(provider.value if provider else "")

    def _update_country(self, country: Country, catalogues: Dict[CloudProvider, CloudCatalogue]) -> None:
        """Show the catalogue state of a country header.

        Args:
            country (Country): The country.
            catalogues (Dict[CloudProvider, CloudCatalogue]): The loaded catalogues, by cloud provider.
        """
        providers = [provider for provider in CloudProvider if provider.country is country]
        loaded = [catalogues[provider] for provider in providers if provider in catalogues]
        total = sum(catalogue.size for catalogue in loaded)
        label = self.theme.country_label(country)
        self.country_items[country].setText(f"{label}\n{total} products · {len(loaded)}/{len(providers)} crawled")

    ############################
    # Publicly Exposed Methods #
    ############################

    def selected_provider(self) -> Optional[CloudProvider]:
        """Get the selected cloud provider.

        Returns:
            Optional[CloudProvider]: The selected provider, `None` when "All providers" or a country is selected.
        """
        return self._item_provider(self.currentItem())

    def selected_country(self) -> Optional[Country]:
        """Get the country of the selection.

        Returns:
            Optional[Country]: The selected country, or the country of the selected provider. `None` when "All
                providers" is selected.
        """
        return self._item_country(self.currentItem())

    def select_country(self, country: Optional[Country]) -> None:
        """Select a country header, unless the selected provider already belongs to that country.

        Args:
            country (Optional[Country]): The country, `None` for all of them: a selected country header is then
                replaced by "All providers", a selected provider is kept.
        """
        provider = self.selected_provider()
        if country is None:
            if provider is None:
                self.setCurrentItem(self.all_item)
            return
        if provider is None or provider.country is not country:
            self.setCurrentItem(self.country_items[country])

    def update_catalogues(
        self, catalogues: Dict[CloudProvider, CloudCatalogue], errors: Dict[CloudProvider, str]
    ) -> None:
        """Show the catalogue state of each country and provider.

        Args:
            catalogues (Dict[CloudProvider, CloudCatalogue]): The loaded catalogues, by cloud provider.
            errors (Dict[CloudProvider, str]): Why the unusable catalogue files could not be loaded.
        """
        total = sum(catalogue.size for catalogue in catalogues.values())
        self.all_item.setText(f"All providers\n{total} products · {len(catalogues)}/{len(CloudProvider)} crawled")
        for country in Country:
            self._update_country(country, catalogues)
        for provider, item in self.provider_items.items():
            label = self.theme.provider_label(provider)
            if provider in errors:
                item.setText(f"{label}\n⚠ Unusable catalogue file")
                item.setToolTip(errors[provider])
                item.setForeground(QColor(self.theme.LEVEL_COLORS[40]))
            elif catalogue := catalogues.get(provider):
                crawled = catalogue.crawled_at.astimezone().strftime("%d %b %Y %H:%M")
                progress = " · crawling…" if catalogue.in_progress else ""
                item.setText(f"{label}\n{catalogue.size} products · {crawled}{progress}")
                item.setToolTip(f"Crawled on {crawled}")
                item.setForeground(QColor(self.theme.TEXT))
            else:
                item.setText(f"{label}\nNot crawled yet")
                item.setToolTip("Launch a crawl to fetch this catalogue.")
                item.setForeground(QColor(self.theme.TEXT_MUTED))
