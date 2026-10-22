from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Collection, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country


class ProviderTree(QTreeWidget):
    """A tree of checkable cloud providers under their country: a country checks or unchecks all its providers.

    Attributes:
        changed (pyqtSignal): Emitted when a provider is checked or unchecked.
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The cloud providers shown.
        country_items (Dict[Country, QTreeWidgetItem]): The country items (tri-state).
        provider_items (Dict[CloudProvider, QTreeWidgetItem]): The provider items, under their country.
        logger (Logger): The tree logger.
    """

    changed = pyqtSignal()

    def __init__(self, theme: Theme, providers: Sequence[CloudProvider], logger: Optional[Logger] = None) -> None:
        """Build the tree, every provider checked.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The cloud providers shown.
            logger (Optional[Logger]): The tree logger.
        """
        super().__init__()
        self.theme = theme
        self.providers = list(providers)
        self.logger = logger if logger else getLogger(__name__)
        self.country_items: Dict[Country, QTreeWidgetItem] = {}
        self.provider_items: Dict[CloudProvider, QTreeWidgetItem] = {}
        self.setHeaderHidden(True)
        self.setMinimumWidth(240)
        for country in Country:
            members = [provider for provider in self.providers if provider.country is country]
            if not members:
                continue
            country_item = QTreeWidgetItem(self, [theme.country_label(country)])
            country_item.setIcon(0, theme.flag_icon(country, 14))
            country_item.setFlags(
                country_item.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable
            )
            self.country_items[country] = country_item
            for provider in members:
                item = QTreeWidgetItem(country_item, [theme.provider_label(provider)])
                item.setIcon(0, theme.provider_icon(provider))
                item.setData(0, Qt.ItemDataRole.UserRole, provider.value)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked)
                self.provider_items[provider] = item
        self.expandAll()
        self.itemChanged.connect(self._on_item_changed)
        self.logger.debug(
            "Provider tree built: %d providers, %d countries.", len(self.providers), len(self.country_items)
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Tell that the checked providers changed, once per provider change.

        Args:
            item (QTreeWidgetItem): The changed item.
            column (int): The changed column.
        """
        if item.data(0, Qt.ItemDataRole.UserRole):
            self.logger.debug("Provider %s %s.", item.text(0), "checked" if item.checkState(0) else "unchecked")
            self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def checked(self) -> List[CloudProvider]:
        """Get the checked cloud providers.

        Returns:
            List[CloudProvider]: The checked providers, in the order of the tree.
        """
        return [
            provider for provider, item in self.provider_items.items() if item.checkState(0) == Qt.CheckState.Checked
        ]

    def set_checked(self, providers: Sequence[CloudProvider]) -> None:
        """Check some cloud providers only, telling once.

        Args:
            providers (Sequence[CloudProvider]):
                The providers to check, the others being unchecked.
        """
        chosen = set(providers)
        self.blockSignals(True)
        for provider, item in self.provider_items.items():
            item.setCheckState(0, Qt.CheckState.Checked if provider in chosen else Qt.CheckState.Unchecked)
        self.blockSignals(False)
        self.logger.debug("%d of %d providers checked.", len(chosen & set(self.provider_items)), len(self.providers))
        self.changed.emit()

    def check_all(self, checked: bool) -> None:
        """Check or uncheck every cloud provider.

        Args:
            checked (bool): Whether they are checked.
        """
        self.logger.debug("Every provider %s.", "checked" if checked else "unchecked")
        self.set_checked(self.providers if checked else [])

    def set_counts(self, counts: Dict[CloudProvider, int]) -> None:
        """Show the number of items of each provider, and of each country, next to their name.

        Args:
            counts (Dict[CloudProvider, int]): The number of items of each provider (none when missing).
        """
        self.blockSignals(True)
        for country, country_item in self.country_items.items():
            members = [provider for provider in self.providers if provider.country is country]
            total = sum(counts.get(provider, 0) for provider in members)
            country_item.setText(0, f"{self.theme.country_label(country)}  ({total:,})")
            for provider in members:
                label = self.theme.provider_label(provider)
                self.provider_items[provider].setText(0, f"{label}  ({counts.get(provider, 0):,})")
        self.blockSignals(False)
        self.logger.debug("Provider counts shown: %d items.", sum(counts.values()))

    def show_only(self, providers: Collection[CloudProvider]) -> None:
        """Hide the providers outside a set (e.g. of another country) and the countries left empty, keeping their check.

        Args:
            providers (Collection[CloudProvider]): The providers shown.
        """
        shown = set(providers)
        for provider, item in self.provider_items.items():
            item.setHidden(provider not in shown)
        for country, country_item in self.country_items.items():
            country_item.setHidden(not any(provider.country is country for provider in shown))
        self.logger.debug("%d of %d providers shown.", len(shown & set(self.provider_items)), len(self.providers))
