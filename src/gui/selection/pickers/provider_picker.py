from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Collection, Dict, List, Optional, Sequence, Set

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget, QWidgetAction

# First Party Imports.
from gui.selection.pickers.provider_tree import ProviderTree
from gui.theme import Theme
from models.cloud.enums import CloudProvider


class ProviderPicker(QToolButton):
    """A drop-down of checkable cloud providers under their country, to filter on several providers at once.

    Attributes:
        TREE_HEIGHT (ClassVar[int]): The height of the drop-down tree, in pixels.
        TREE_WIDTH (ClassVar[int]): The width of the drop-down tree, in pixels (long names with their count).
        changed (pyqtSignal): Emitted when the picked providers change.
        theme (Theme): The application theme.
        tree (ProviderTree): The checkable providers, under their country.
        all_button, none_button (QPushButton): Check or uncheck every shown provider.
        shown (Set[CloudProvider]): The providers offered (e.g. of the chosen bloc and country), the others hidden.
        logger (Logger): The picker logger.

    Notes:
        The drop-down stays open while providers are checked. A provider hidden by `show_only` keeps its check, and
        is not picked while hidden: the picked providers are the checked ones among the shown ones.
    """

    TREE_HEIGHT: ClassVar[int] = 360
    TREE_WIDTH: ClassVar[int] = 340

    changed = pyqtSignal()

    def __init__(self, theme: Theme, providers: Sequence[CloudProvider], logger: Optional[Logger] = None) -> None:
        """Build the picker, every provider checked.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The providers offered.
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.theme = theme
        self.shown: Set[CloudProvider] = set(providers)
        self.tree = ProviderTree(theme, providers, self.logger)
        self.tree.setMinimumHeight(self.TREE_HEIGHT)
        self.tree.setMinimumWidth(self.TREE_WIDTH)
        self.all_button, self.none_button = QPushButton("All"), QPushButton("None")
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.tree, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.all_button)
        buttons.addWidget(self.none_button)
        layout.addLayout(buttons)
        menu = QMenu(self)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        self.setMenu(menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("Show only the software of some cloud providers (several at once)")
        self.tree.changed.connect(self._on_tree_changed)
        self.all_button.clicked.connect(lambda: self._check_shown(True))
        self.none_button.clicked.connect(lambda: self._check_shown(False))
        self._update_text()
        self.logger.debug("Provider picker built: %d providers.", len(self.shown))

    ############################
    # Internal Helpers Methods #
    ############################

    def _picked(self) -> List[CloudProvider]:
        """Get the checked providers among the shown ones.

        Returns:
            List[CloudProvider]: The picked providers, in the order of the tree.
        """
        return [provider for provider in self.tree.checked() if provider in self.shown]

    def _is_filtering(self) -> bool:
        """Tell whether the picker leaves some shown provider out.

        Returns:
            bool: Whether a shown provider is unchecked.
        """
        return len(self._picked()) < len(self.shown & set(self.tree.provider_items))

    def _update_text(self) -> None:
        """Show what is picked on the button."""
        picked = self._picked()
        if not self._is_filtering():
            text = "All providers"
        elif not picked:
            text = "No provider"
        elif len(picked) == 1:
            text = self.theme.provider_label(picked[0])
        else:
            text = f"{len(picked)} providers"
        self.setText(f"{text}  ▾")
        self.logger.debug("Provider picker shows %r.", text)

    def _on_tree_changed(self) -> None:
        """Show the new pick, and tell it."""
        self._update_text()
        self.changed.emit()

    def _check_shown(self, checked: bool) -> None:
        """Check or uncheck every shown provider, the hidden ones keeping their check.

        Args:
            checked (bool): Whether they are checked.
        """
        hidden = [provider for provider in self.tree.checked() if provider not in self.shown]
        self.logger.debug("Every shown provider %s.", "checked" if checked else "unchecked")
        self.tree.set_checked([*hidden, *(self.shown if checked else [])])

    ############################
    # Publicly Exposed Methods #
    ############################

    def picked(self) -> Optional[List[CloudProvider]]:
        """Get the picked providers.

        Returns:
            Optional[List[CloudProvider]]: The checked providers among the shown ones (empty when none is), `None`
                when every shown provider is checked (no filter).
        """
        return self._picked() if self._is_filtering() else None

    def show_only(self, providers: Collection[CloudProvider]) -> None:
        """Offer some providers only (e.g. of the chosen bloc and country), the others keeping their check.

        Args:
            providers (Collection[CloudProvider]): The providers offered.
        """
        self.shown = set(providers)
        self.tree.show_only(self.shown)
        self._update_text()
        self.logger.debug("Provider picker offers %d providers.", len(self.shown))

    def set_counts(self, counts: Dict[CloudProvider, int]) -> None:
        """Show the number of items of each provider and country in the drop-down.

        Args:
            counts (Dict[CloudProvider, int]): The number of items of each provider.
        """
        self.tree.set_counts(counts)

    def reset(self) -> None:
        """Check every provider again, telling once."""
        self.logger.debug("Provider picker reset.")
        self.tree.check_all(True)
