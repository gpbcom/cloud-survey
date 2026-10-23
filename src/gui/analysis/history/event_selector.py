from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QToolButton

# First Party Imports.
from analytics.history.chronology_timeline import ChronologyTimeline
from models.history.enums import EventKind
from models.history.timeline.notable_event import NotableEvent


class EventSelector(QToolButton):
    """Pick the notable events drawn on the leaders chart, as the "Policy shocks" button of mega-trends does.

    Attributes:
        KIND_PREFIX (ClassVar[str]): The data of a "Show all <kind>" entry, before the kind.
        SHOW_ALL (ClassVar[str]): The data of the "Show all" entry.
        HIDE_ALL (ClassVar[str]): The data of the "Hide all" entry.
        changed (pyqtSignal): Emitted with the keys of the events picked, in date order.
        events (List[NotableEvent]): Every event, in date order.
        timeline (ChronologyTimeline): Names the kinds.
        logger (Logger): The selector logger.

    Notes:
        The menu holds a section per kind of event: a "Show all <kind>" entry, then a checkable `YYYY — label` entry
        per event (the mega-trends policy-shock entries), then "Show all" and "Hide all". The events marked
        `default` in the chronology are picked at first, so the chart is meaningful on first look. An ampersand of a
        label is doubled, else the menu reads it as a shortcut (AT&T would show as ATT).
    """

    KIND_PREFIX: ClassVar[str] = "kind:"
    SHOW_ALL: ClassVar[str] = "all:show"
    HIDE_ALL: ClassVar[str] = "all:hide"

    changed = pyqtSignal(list)

    def __init__(self, events: List[NotableEvent], logger: Optional[Logger] = None) -> None:
        """Build the button and its menu.

        Args:
            events (List[NotableEvent]): Every event.
            logger (Optional[Logger]): The selector logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.timeline = ChronologyTimeline(self.logger)
        self.events = sorted(events, key=lambda event: event.when())
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip(
            "Dashed markers of the notable events (regulation, deals, bankruptcies, listings, launches), drawn the way "
            "mega-trends draws its policy shocks"
        )
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for kind in EventKind:
            chosen = [event for event in self.events if event.kind is kind]
            if not chosen:
                continue
            menu.addSection(self.timeline.name(kind))
            every = menu.addAction(f"Show all {self.timeline.name(kind).lower()}")
            if every is not None:
                every.setData(f"{self.KIND_PREFIX}{kind.value}")
            for event in chosen:
                action = menu.addAction(f"{event.year()} \u2014 {event.label}".replace("&", "&&"))
                if action is None:
                    continue
                action.setCheckable(True)
                action.setChecked(event.default)
                action.setData(event.key)
                action.setToolTip(event.description)
        menu.addSeparator()
        for text, data in (("Show all", self.SHOW_ALL), ("Hide all", self.HIDE_ALL)):
            action = menu.addAction(text)
            if action is not None:
                action.setData(data)
        menu.triggered.connect(self._on_action)
        self.setMenu(menu)
        self._label()

    ############################
    # Internal Helpers Methods #
    ############################

    def _actions(self) -> List[QAction]:
        """Get the event entries.

        Returns:
            List[QAction]: The checkable entries, one per event.
        """
        menu = self.menu()
        return [action for action in menu.actions() if action.isCheckable()] if menu is not None else []

    def _label(self) -> None:
        """Write the number of events picked on the button."""
        self.setText(f"Notable events ({sum(action.isChecked() for action in self._actions())}) \u25be")

    def _emit(self) -> None:
        """Tell which events are picked."""
        self._label()
        keys = [str(action.data()) for action in self._actions() if action.isChecked()]
        self.logger.debug("%d notable events picked.", len(keys))
        self.changed.emit(keys)

    def _on_action(self, action: QAction) -> None:
        """Apply a menu entry: an event toggled, a kind or every event shown, every event hidden.

        Args:
            action (QAction): The entry triggered.
        """
        data = str(action.data())
        kinds = {event.key: event.kind.value for event in self.events}
        if data.startswith(self.KIND_PREFIX):
            kind = data[len(self.KIND_PREFIX) :]
            for entry in self._actions():
                if kinds.get(str(entry.data())) == kind:
                    entry.setChecked(True)
        elif data in (self.SHOW_ALL, self.HIDE_ALL):
            for entry in self._actions():
                entry.setChecked(data == self.SHOW_ALL)
        self._emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def selected(self) -> List[str]:
        """Get the events picked.

        Returns:
            List[str]: Their keys, in date order.
        """
        return [str(action.data()) for action in self._actions() if action.isChecked()]

    def set_selected(self, keys: List[str]) -> None:
        """Pick events, the others left out.

        Args:
            keys (List[str]): The keys of the events to show.
        """
        wanted = set(keys)
        for action in self._actions():
            action.setChecked(str(action.data()) in wanted)
        self._emit()
