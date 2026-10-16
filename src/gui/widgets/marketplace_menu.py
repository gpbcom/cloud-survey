from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget, QWidgetAction

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country


class MarketplaceMenu(QMenu):
    """Menu choosing the marketplaces to extract the software from, grouped under their country flag.

    Each marketplace has a checkable entry. The menu stays open while marketplaces are checked, the extraction action
    closes it.

    Attributes:
        extract_requested (pyqtSignal): Emitted with the values of the checked marketplaces' cloud providers when their
            extraction is requested.
        theme (Theme): The application theme.
        provider_actions (Dict[CloudProvider, QAction]): The checkable entry of each marketplace.
        select_all_action (QAction): Checks every marketplace.
        select_none_action (QAction): Unchecks every marketplace.
        extract_action (QAction): Requests the extraction of the checked marketplaces.
    """

    extract_requested = pyqtSignal(list)

    def __init__(
        self,
        theme: Theme,
        providers: Sequence[CloudProvider],
        parent: Optional[QWidget] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the menu, no marketplace checked.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The cloud providers having a marketplace, in display order.
            parent (Optional[QWidget]): The parent widget.
            logger (Optional[Logger]): The menu logger.
        """
        super().__init__("&Marketplaces", parent)
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.setToolTipsVisible(True)
        self.select_all_action = self._add_action("Select all")
        self.select_none_action = self._add_action("Select none")
        self.provider_actions: Dict[CloudProvider, QAction] = {}
        for country in dict.fromkeys(provider.country for provider in providers):
            self.addSeparator()
            self._add_header(country)
            for provider in providers:
                if provider.country is not country:
                    continue
                action = self._add_action(theme.provider_label(provider))
                action.setCheckable(True)
                action.setData(provider.value)
                action.toggled.connect(self._update_extract_action)
                self.provider_actions[provider] = action
        self.addSeparator()
        self.extract_action = self._add_action("")
        self.select_all_action.triggered.connect(lambda: self.select(list(self.provider_actions)))
        self.select_none_action.triggered.connect(lambda: self.select([]))
        self.extract_action.triggered.connect(self._on_extract)
        self._update_extract_action()

    ############################
    # Internal Helpers Methods #
    ############################

    def _add_action(self, text: str, icon: Optional[QIcon] = None) -> QAction:
        """Add an entry to the menu.

        Args:
            text (str): The entry text.
            icon (Optional[QIcon]): The entry icon.

        Returns:
            QAction: The added entry.
        """
        action = QAction(icon, text, self) if icon is not None else QAction(text, self)
        self.addAction(action)
        return action

    def _add_header(self, country: Country) -> None:
        """Add the header of the marketplaces of a country: its flag and its name, not selectable.

        Args:
            country (Country): The country.
        """
        flag = QLabel()
        flag.setPixmap(self.theme.flag_pixmap(country, 12))
        name = QLabel(self.theme.country_label(country))
        name.setObjectName("muted")
        font = name.font()
        font.setBold(True)
        name.setFont(font)
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 6, 10, 2)
        layout.setSpacing(6)
        layout.addWidget(flag)
        layout.addWidget(name)
        layout.addStretch(1)
        action = QWidgetAction(self)
        action.setDefaultWidget(header)
        action.setText(self.theme.country_label(country))
        self.addAction(action)

    def _checked(self) -> List[CloudProvider]:
        """Get the cloud providers of the checked marketplaces.

        Returns:
            List[CloudProvider]: The checked marketplaces' cloud providers, in menu order.
        """
        return [provider for provider, action in self.provider_actions.items() if action.isChecked()]

    def _update_extract_action(self) -> None:
        """Show how many marketplaces the extraction action extracts, and disable it when none is checked."""
        count = len(self._checked())
        noun = "marketplace" if count == 1 else "marketplaces"
        self.extract_action.setText(f"\u25b6  Extract the {count} selected {noun}")
        self.extract_action.setEnabled(count > 0)

    def _on_extract(self) -> None:
        """Request the extraction of the checked marketplaces."""
        providers = self._checked()
        self.logger.info("Extraction of the marketplaces requested: %s.", ", ".join(p.value for p in providers))
        self.extract_requested.emit([provider.value for provider in providers])

    ############################
    # Publicly Exposed Methods #
    ############################

    def selected_providers(self) -> List[CloudProvider]:
        """Get the cloud providers of the checked marketplaces.

        Returns:
            List[CloudProvider]: The checked marketplaces' cloud providers, in menu order.
        """
        return self._checked()

    def select(self, providers: Sequence[CloudProvider]) -> None:
        """Check exactly some marketplaces.

        Args:
            providers (Sequence[CloudProvider]): The cloud providers whose marketplaces are checked, the other ones
                are unchecked.
        """
        for provider, action in self.provider_actions.items():
            action.blockSignals(True)
            action.setChecked(provider in providers)
            action.blockSignals(False)
        self._update_extract_action()

    def set_counts(self, counts: Dict[CloudProvider, int]) -> None:
        """Show the number of software of each crawled marketplace next to its name.

        Args:
            counts (Dict[CloudProvider, int]): The number of software, by cloud provider of a crawled marketplace.
        """
        for provider, action in self.provider_actions.items():
            label = self.theme.provider_label(provider)
            if provider in counts:
                action.setText(f"{label}  ({counts[provider]:,})")
                action.setToolTip(f"{counts[provider]:,} software in the last extraction")
            else:
                action.setText(label)
                action.setToolTip("Not extracted yet")

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:
        """Toggle a marketplace without closing the menu, trigger the other actions normally (Qt override).

        Args:
            event (Optional[QMouseEvent]): The mouse event.
        """
        action = self.actionAt(event.position().toPoint()) if event is not None else None
        if action is not None and action.isCheckable() and action.isEnabled():
            action.toggle()
            return
        super().mouseReleaseEvent(event)
