from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# Third Party Imports.
from pydantic import ValidationError
from PyQt6.QtCore import QSettings

# First Party Imports.
from models.trends.chart_axes import ChartAxes


class ChartStateStore:
    """Remember, per chart, whether its section is expanded and what it shows, from one session to the next.

    Attributes:
        VERSION (ClassVar[int]): The version of the saved axes: those of an earlier version are upgraded when read.
        settings (Optional[QSettings]): The persistent settings, `None` to remember for the session only.
        expanded_states (Dict[str, bool]): The expanded state of each chart key, without persistent settings.
        saved_axes (Dict[str, ChartAxes]): The axes of each chart key, without persistent settings.
        logger (Logger): The store logger.

    Notes:
        - The keys name the tab and the chart, e.g. `marketplace/trends`.
        - Axes saved by a former version of the application which no longer validate are forgotten.
        - Axes saved before version 2 capped the number of series (8 or 20 by default): they show every series once
          read, the user choosing a cap again if needed.
    """

    VERSION: ClassVar[int] = 2

    def __init__(self, settings: Optional[QSettings] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the store.

        Args:
            settings (Optional[QSettings]): The persistent settings, `None` to remember for the session only.
            logger (Optional[Logger]): The store logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.settings = settings
        self.expanded_states: Dict[str, bool] = {}
        self.saved_axes: Dict[str, ChartAxes] = {}

    ############################
    # Publicly Exposed Methods #
    ############################

    def expanded(self, key: str, default: bool = True) -> bool:
        """Tell whether the section of a chart was left expanded.

        Args:
            key (str): The chart key.
            default (bool): The state of a chart never toggled.

        Returns:
            bool: Whether the section is expanded.
        """
        if self.settings is None:
            self.logger.debug("Expanded state of the chart %s read from the session.", key)
            return self.expanded_states.get(key, default)
        value = self.settings.value(f"{key}/expanded", default)
        expanded = value if isinstance(value, bool) else str(value).lower() == "true"
        self.logger.debug("Chart %s left %s.", key, "expanded" if expanded else "collapsed")
        return expanded

    def set_expanded(self, key: str, expanded: bool) -> None:
        """Remember whether the section of a chart is expanded.

        Args:
            key (str): The chart key.
            expanded (bool): Whether the section is expanded.
        """
        self.logger.debug("Chart %s %s.", key, "expanded" if expanded else "collapsed")
        if self.settings is None:
            self.expanded_states[key] = expanded
        else:
            self.settings.setValue(f"{key}/expanded", expanded)

    def axes(self, key: str) -> Optional[ChartAxes]:
        """Get what a chart showed last.

        Args:
            key (str): The chart key.

        Returns:
            Optional[ChartAxes]: The axes, `None` for a chart never configured (or saved by another version).
        """
        if self.settings is None:
            self.logger.debug("Axes of the chart %s read from the session.", key)
            return self.saved_axes.get(key)
        raw = self.settings.value(f"{key}/axes", "")
        if not raw:
            self.logger.debug("No saved axes for the chart %s: its default is shown.", key)
            return None
        try:
            axes = ChartAxes.model_validate_json(str(raw))
        except ValidationError as e:
            self.logger.warning("The saved axes of the chart %s are forgotten: %s", key, e)
            return None
        version = self.settings.value(f"{key}/version", 1)
        if str(version).isdigit() and int(str(version)) >= self.VERSION:
            self.logger.debug("Saved axes of the chart %s restored: a %s chart.", key, axes.chart.value)
            return axes
        self.logger.info("The saved axes of the chart %s are upgraded: every series is shown.", key)
        return axes.model_copy(update={"top": None})

    def set_axes(self, key: str, axes: ChartAxes) -> None:
        """Remember what a chart shows.

        Args:
            key (str): The chart key.
            axes (ChartAxes): The chart axes.
        """
        self.logger.debug("Axes of the chart %s saved: a %s chart of %s.", key, axes.chart.value, axes.y.value)
        if self.settings is None:
            self.saved_axes[key] = axes
        else:
            self.settings.setValue(f"{key}/axes", axes.model_dump_json())
            self.settings.setValue(f"{key}/version", self.VERSION)
