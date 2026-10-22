from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider, GeoBloc
from models.correspondence.query.correspondence_query import CorrespondenceQuery


class ColumnPicker(QWidget):
    """The provider columns of the correspondence diagram, in their order, added one by one or from a preset.

    Attributes:
        PRESET_SIZE (ClassVar[int]): The number of columns of a preset.
        MANUAL_LIMIT (ClassVar[int]): The largest number of columns picked one by one.
        changed (pyqtSignal): Emitted when the columns change.
        theme (Theme): The application theme.
        providers (List[CloudProvider]): The providers offered.
        chosen (List[CloudProvider]): The columns, in their order.
        sizes (Dict[CloudProvider, int]): The listed services of each provider (the presets take the largest).
        chips (QHBoxLayout): The buttons of the columns.
        add_button (QToolButton): Adds a column, the providers grouped by bloc.
        preset_button (QToolButton): Replaces the columns with a preset.
        all_button (QToolButton): Shows every provider holding a catalogue (checked by default).
        logger (Logger): The picker logger.

    Notes:
        - "All providers" (the default) shows every provider holding a catalogue, grouped by bloc, the largest
          catalogues first in each bloc.
        - Otherwise a column button opens a menu moving it left or right, or removing it: 2 to 8 columns, added one
          by one or from a preset.
    """

    PRESET_SIZE: ClassVar[int] = 5
    MANUAL_LIMIT: ClassVar[int] = 8

    changed = pyqtSignal()

    def __init__(
        self,
        theme: Theme,
        providers: Sequence[CloudProvider],
        columns: Sequence[CloudProvider],
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the picker.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The providers offered.
            columns (Sequence[CloudProvider]): The first columns.
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.providers = list(providers)
        self.chosen = list(dict.fromkeys(columns))
        self.sizes: Dict[CloudProvider, int] = {}
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        self.add_button = QToolButton()
        self.add_button.setText("+ Provider")
        self.add_button.setToolTip("Add a provider column")
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.preset_button = QToolButton()
        self.preset_button.setText("Presets ▾")
        self.preset_button.setToolTip("Compare the largest providers of a bloc, or the leaders of every bloc")
        self.preset_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.all_button = QToolButton()
        self.all_button.setCheckable(True)
        self.all_button.setChecked(True)
        self.all_button.setText("All providers")
        self.all_button.setToolTip("Show the catalogue of every provider at once, grouped by bloc")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Columns"))
        layout.addWidget(self.all_button)
        layout.addLayout(self.chips)
        layout.addWidget(self.add_button)
        layout.addWidget(self.preset_button)
        self._rebuild()
        self.all_button.toggled.connect(self._on_all)
        self.logger.debug("Column picker built with %d columns.", len(self.chosen))

    ############################
    # Internal Helpers Methods #
    ############################

    def _ranked(self, providers: Sequence[CloudProvider]) -> List[CloudProvider]:
        """Order providers by catalogue size, the largest first.

        Args:
            providers (Sequence[CloudProvider]): The providers.

        Returns:
            List[CloudProvider]: The providers, the largest catalogues first (in their declared order when unknown).
        """
        order = {provider: index for index, provider in enumerate(self.providers)}
        return sorted(providers, key=lambda provider: (-self.sizes.get(provider, 0), order.get(provider, 0)))

    def _everyone(self) -> List[CloudProvider]:
        """List every provider holding a catalogue, grouped by bloc, the largest catalogues first in each bloc.

        Returns:
            List[CloudProvider]: The providers (all of them until the catalogue sizes are read, two at least).
        """
        held = [provider for provider in self.providers if self.sizes.get(provider, 0) > 0] if self.sizes else []
        held = held or list(self.providers)
        missing = CorrespondenceQuery.MIN_COLUMNS - len(held)
        if missing > 0:
            held += [provider for provider in self.providers if provider not in held][:missing]
        ranked = self._ranked(held)
        return [provider for bloc in GeoBloc for provider in ranked if provider.bloc is bloc]

    def _presets(self) -> Dict[str, List[CloudProvider]]:
        """Build the presets.

        Returns:
            Dict[str, List[CloudProvider]]: The columns of each preset, by label.
        """
        ranked = self._ranked(self.providers)
        presets = {"Largest catalogues": ranked[: self.PRESET_SIZE]}
        leaders = [next((provider for provider in ranked if provider.bloc is bloc), None) for bloc in GeoBloc]
        presets["Leader of each bloc"] = [provider for provider in leaders if provider is not None][: self.PRESET_SIZE]
        for bloc in GeoBloc:
            members = [provider for provider in ranked if provider.bloc is bloc][: self.PRESET_SIZE]
            if len(members) >= CorrespondenceQuery.MIN_COLUMNS:
                presets[f"{self.theme.bloc_label(bloc)}: largest"] = members
        return presets

    def _chip(self, index: int, provider: CloudProvider) -> QToolButton:
        """Build the button of a column.

        Args:
            index (int): Its position.
            provider (CloudProvider): Its provider.

        Returns:
            QToolButton: The button, with its menu (move left or right, remove).
        """
        chip = QToolButton()
        chip.setIcon(self.theme.provider_icon(provider))
        chip.setText(self.theme.PROVIDER_SHORT_LABELS[provider])
        chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        chip.setToolTip(f"{self.theme.provider_label(provider)}: column {index + 1}")
        menu = QMenu(chip)
        for label, step, enabled in (
            ("◀  Move left", -1, index > 0),
            ("Move right  ▶", 1, index < len(self.chosen) - 1),
            ("✕  Remove", 0, len(self.chosen) > CorrespondenceQuery.MIN_COLUMNS),
        ):
            action = menu.addAction(label)
            if action is not None:
                action.setEnabled(enabled)
                action.setData((provider.value, step))
        menu.triggered.connect(self._on_chip_action)
        chip.setMenu(menu)
        return chip

    def _rebuild(self) -> None:
        """Rebuild the column buttons and the menus."""
        while self.chips.count():
            item = self.chips.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        showing_all = self.all_button.isChecked()
        for index, provider in enumerate([] if showing_all else self.chosen):
            self.chips.addWidget(self._chip(index, provider))
        listed = len(self._everyone())
        self.all_button.setText(f"All providers ({listed})" if showing_all else "All providers")
        add_menu = QMenu(self.add_button)
        for bloc in GeoBloc:
            offered = [provider for provider in self._ranked(self.providers) if provider.bloc is bloc]
            submenu = add_menu.addMenu(self.theme.bloc_label(bloc)) if offered else None
            if submenu is None:
                continue
            for provider in offered:
                size = self.sizes.get(provider)
                label = self.theme.provider_label(provider) + (f"  ({size:,})" if size else "")
                action = submenu.addAction(self.theme.flag_icon(provider.country), label)
                if action is not None:
                    action.setEnabled(provider not in self.chosen)
                    action.setData(provider.value)
        add_menu.triggered.connect(self._on_add_action)
        self.add_button.setMenu(add_menu)
        self.add_button.setEnabled(len(self.chosen) < self.MANUAL_LIMIT)
        preset_menu = QMenu(self.preset_button)
        for label, columns in self._presets().items():
            action = preset_menu.addAction(label)
            if action is not None:
                action.setToolTip(", ".join(self.theme.PROVIDER_SHORT_LABELS[provider] for provider in columns))
                action.setData([provider.value for provider in columns])
        preset_menu.triggered.connect(self._on_preset)
        self.preset_button.setMenu(preset_menu)

    def _set(self, columns: List[CloudProvider]) -> None:
        """Replace the columns, then tell.

        Args:
            columns (List[CloudProvider]): The new columns.
        """
        self.chosen = list(dict.fromkeys(columns))[: self.MANUAL_LIMIT]
        self.all_button.blockSignals(True)
        self.all_button.setChecked(False)
        self.all_button.blockSignals(False)
        self._rebuild()
        self.logger.info("Correspondence columns: %s.", ", ".join(provider.value for provider in self.chosen))
        self.changed.emit()

    def _move(self, provider: CloudProvider, step: int) -> None:
        """Move a column left or right.

        Args:
            provider (CloudProvider): The column.
            step (int): -1 to move it left, 1 to move it right.
        """
        index = self.chosen.index(provider)
        target = index + step
        if not 0 <= target < len(self.chosen):
            return
        columns = list(self.chosen)
        columns[index], columns[target] = columns[target], columns[index]
        self._set(columns)

    def _remove(self, provider: CloudProvider) -> None:
        """Remove a column, unless only two are left.

        Args:
            provider (CloudProvider): The column.
        """
        if len(self.chosen) <= CorrespondenceQuery.MIN_COLUMNS:
            return
        self._set([column for column in self.chosen if column is not provider])

    def _add(self, provider: CloudProvider) -> None:
        """Add a column at the end, unless six are shown.

        Args:
            provider (CloudProvider): The provider.
        """
        if provider in self.chosen or len(self.chosen) >= self.MANUAL_LIMIT:
            return
        self._set([*self.chosen, provider])

    def _on_chip_action(self, action: QAction) -> None:
        """Move or remove a column, from the menu of its button.

        Args:
            action (QAction): The chosen entry, its data the provider and the step (0 to remove).
        """
        value, step = action.data()
        provider = CloudProvider(value)
        if step:
            self._move(provider, int(step))
        else:
            self._remove(provider)

    def _on_add_action(self, action: QAction) -> None:
        """Add the provider chosen in the menu of the add button.

        Args:
            action (QAction): The chosen entry, its data the provider.
        """
        if action.data():
            self._add(CloudProvider(action.data()))

    def _on_preset(self, action: QAction) -> None:
        """Replace the columns with the chosen preset.

        Args:
            action (QAction): The chosen entry, its data the providers of the preset.
        """
        self._set([CloudProvider(value) for value in action.data()])

    def _on_all(self, checked: bool) -> None:
        """Show every provider, or the columns picked one by one again.

        Args:
            checked (bool): Whether every provider is shown.
        """
        self._rebuild()
        self.logger.info("Correspondence columns: %s.", "every provider" if checked else "picked one by one")
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def columns(self) -> List[CloudProvider]:
        """Get the columns.

        Returns:
            List[CloudProvider]: Every provider holding a catalogue when "All providers" is checked, else the picked
                providers, in their order.
        """
        return self._everyone() if self.all_button.isChecked() else list(self.chosen)

    def set_columns(self, columns: Sequence[CloudProvider]) -> None:
        """Replace the columns, then tell.

        Args:
            columns (Sequence[CloudProvider]): The providers, in their order (2 to 6).
        """
        self._set(list(columns))

    def set_sizes(self, sizes: Dict[CloudProvider, int]) -> None:
        """Know the catalogue sizes, for the presets and the menu of the providers.

        Args:
            sizes (Dict[CloudProvider, int]): The listed services of each provider.
        """
        self.sizes = dict(sizes)
        self._rebuild()
