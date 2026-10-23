from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from PyQt6.QtCore import QObject

# First Party Imports.
from analytics.history.chronology_loader import ChronologyLoader
from analytics.history.chronology_timeline import ChronologyTimeline
from analytics.history.exception import ChronologyFileError
from gui.analysis.history.chronology_table import ChronologyTable
from gui.analysis.history.event_selector import EventSelector
from gui.analysis.history.leadership_chart import LeadershipChart
from gui.theme import Theme
from models.history.chronology import Chronology


class HistoryPanel(QObject):
    """The leaders of digital infrastructure in the Analysis tab: the chart, its event selector and the chronology.

    Attributes:
        theme (Theme): The application theme.
        timeline (ChronologyTimeline): The dated lines of the chronology.
        chronology (Optional[Chronology]): The chronology shown, `None` when it cannot be loaded.
        chart (LeadershipChart): The swimlanes, a band per reign, a dashed marker per event picked.
        selector (EventSelector): Picks the events drawn (the header tool of the chart card).
        table (ChronologyTable): The chronology printed: a line per change of leader and per event.
        logger (Logger): The panel logger.

    Notes:
        The chronology is read from `conf/history/chronology.yaml` once. A band or marker clicked in the chart selects
        its line in the table, and a line clicked in the table highlights its band or marker.
    """

    def __init__(self, theme: Theme, chronology: Optional[Chronology] = None, logger: Optional[Logger] = None) -> None:
        """Build the chart, the selector and the table.

        Args:
            theme (Theme): The application theme.
            chronology (Optional[Chronology]): The chronology, read from `conf/history/chronology.yaml` by default.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.timeline = ChronologyTimeline(self.logger)
        message = ""
        if chronology is None:
            try:
                chronology = ChronologyLoader(self.logger).load()
            except ChronologyFileError as e:
                self.logger.error("The leaders of digital infrastructure cannot be shown: %s", e.message)
                message = e.message
        self.chronology = chronology
        self.chart = LeadershipChart(theme, self.logger)
        self.selector = EventSelector(chronology.events if chronology else [], self.logger)
        self.table = ChronologyTable(theme, self.logger)
        if chronology is not None:
            self.chart.set_chronology(chronology)
            self.table.set_entries(self.timeline.entries(chronology), self.timeline)
            self._on_events(self.selector.selected())
        else:
            self.chart.set_message(message)
        self.selector.changed.connect(self._on_events)
        self.chart.picked.connect(self.table.select_key)
        self.table.picked.connect(self.chart.highlight)
        self.logger.debug("Leaders panel built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_events(self, keys: List[str]) -> None:
        """Draw the events picked.

        Args:
            keys (List[str]): Their keys.
        """
        wanted = set(keys)
        events = [event for event in self.chronology.events if event.key in wanted] if self.chronology else []
        self.chart.set_events(events)
