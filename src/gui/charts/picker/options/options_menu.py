from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu

TransformOption = Tuple[str, str, Optional[str]]


class OptionsMenu(QMenu):
    """Menu of the secondary chart options: value transform, number of series, forecast, derivative and log axes.

    Attributes:
        TOPS (ClassVar[Tuple[Optional[int], ...]]): The numbers of series which can be shown, `None` for all of them.
        changed (pyqtSignal): Emitted when the user changes an option.
        transform_menu (QMenu): The value transforms.
        top_menu (QMenu): The numbers of series shown.
        forecast_action (QAction): Extrapolates the trends.
        derivative_action (QAction): Draws the rate of change of each line instead of its values.
        log_action (QAction): Makes the bubble chart axes logarithmic.
        transform_group (QActionGroup): The exclusive transform actions.
        top_group (QActionGroup): The exclusive number of series actions.
        transform_actions (Dict[str, QAction]): The action of each transform value.
        top_actions (Dict[Optional[int], QAction]): The action of each number of series, `None` for all of them.
        logger (Logger): The menu logger.
    """

    TOPS: ClassVar[Tuple[Optional[int], ...]] = (None, 5, 8, 12, 20)

    changed = pyqtSignal()

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build the menu.

        Args:
            logger (Optional[Logger]): The menu logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.transform_menu = self.addMenu("Values")
        self.top_menu = self.addMenu("Series shown")
        self.addSeparator()
        self.forecast_action = self.addAction("Forecast the trend")
        self.derivative_action = self.addAction("Rate of change (derivative)")
        self.log_action = self.addAction("Logarithmic axes")
        self.transform_group = QActionGroup(self)
        self.top_group = QActionGroup(self)
        self.transform_actions: Dict[str, QAction] = {}
        self.top_actions: Dict[Optional[int], QAction] = {}
        for action in (self.forecast_action, self.derivative_action, self.log_action):
            if action is not None:
                action.setCheckable(True)
                action.triggered.connect(lambda checked: self.changed.emit())
        if self.top_menu is not None:
            for count in self.TOPS:
                action = self.top_menu.addAction("All series" if count is None else f"The largest {count}")
                if action is not None:
                    action.setCheckable(True)
                    self.top_group.addAction(action)
                    action.triggered.connect(lambda checked: self.changed.emit())
                    self.top_actions[count] = action

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_state(
        self,
        transforms: List[TransformOption],
        transform: str,
        top: Optional[int],
        forecast: bool,
        forecast_reason: Optional[str],
        log_scale: Optional[bool],
        derivative: Optional[bool] = None,
    ) -> None:
        """Show the options of the chart, without emitting a change.

        Args:
            transforms (List[TransformOption]): The value, label and blocking reason of each transform.
            transform (str): The chosen transform value.
            top (Optional[int]): The chosen number of series, `None` for all of them.
            forecast (bool): Whether the trends are extrapolated.
            forecast_reason (Optional[str]): Why there can be no forecast, `None` when there can.
            log_scale (Optional[bool]): Whether the axes are logarithmic, `None` when the chart has no such option.
            derivative (Optional[bool]): Whether the lines draw their rate of change, `None` when the chart has no
                lines.
        """
        self.logger.debug(
            "Chart options: %d transforms, %s chosen, top %s, forecast %s, log scale %s, derivative %s.",
            len(transforms),
            transform,
            top if top is not None else "all",
            forecast,
            log_scale,
            derivative,
        )
        if forecast_reason is not None:
            self.logger.debug("Forecast disabled: %s", forecast_reason)
        if self.transform_menu is not None:
            self.transform_menu.clear()
            self.transform_actions = {}
            for value, label, reason in transforms:
                action = self.transform_menu.addAction(label)
                if action is None:
                    self.logger.warning("The transform %s could not be added to the options menu.", value)
                    continue
                action.setCheckable(True)
                action.setChecked(value == transform)
                action.setEnabled(reason is None)
                action.setToolTip(reason or label)
                self.transform_group.addAction(action)
                action.triggered.connect(lambda checked: self.changed.emit())
                self.transform_actions[value] = action
            menu_action = self.transform_menu.menuAction()
            if menu_action is not None:
                menu_action.setVisible(len(transforms) > 1)
            self.transform_menu.setToolTipsVisible(True)
        counts = [count for count in self.TOPS if count is not None]
        chosen = None if top is None else min(counts, key=lambda count: abs(count - top))
        for count, action in self.top_actions.items():
            action.setChecked(count == chosen)
        if self.forecast_action is not None:
            self.forecast_action.setChecked(forecast)
            self.forecast_action.setEnabled(forecast_reason is None)
            self.forecast_action.setToolTip(forecast_reason or "Extrapolate the trend of each series")
            self.forecast_action.setVisible(forecast_reason is None or log_scale is None)
        if self.derivative_action is not None:
            self.derivative_action.setVisible(derivative is not None)
            self.derivative_action.setChecked(bool(derivative))
            self.derivative_action.setToolTip(
                "Draw the rate of change of each line instead of its values: the change between two consecutive points "
                "divided by the time between them (per year), or by the change of x on a measured x axis. Applied "
                "after the values transform; a gap is never bridged."
            )
        if self.log_action is not None:
            self.log_action.setVisible(log_scale is not None)
            self.log_action.setChecked(bool(log_scale))
        self.setToolTipsVisible(True)
        self.logger.debug("Chart options shown: %d transform actions.", len(self.transform_actions))

    def transform(self) -> str:
        """Get the chosen transform.

        Returns:
            str: Its value, empty without transform.
        """
        return next((value for value, action in self.transform_actions.items() if action.isChecked()), "")

    def top(self) -> Optional[int]:
        """Get the chosen number of series.

        Returns:
            Optional[int]: The number of series shown, `None` for all of them.
        """
        return next((count for count, action in self.top_actions.items() if action.isChecked()), None)

    def forecast(self) -> bool:
        """Tell whether the trends are extrapolated.

        Returns:
            bool: Whether the forecast is checked (and allowed).
        """
        action = self.forecast_action
        return action is not None and action.isChecked() and action.isEnabled()

    def derivative(self) -> bool:
        """Tell whether the lines draw their rate of change.

        Returns:
            bool: Whether the derivative is checked (and offered).
        """
        action = self.derivative_action
        return action is not None and action.isChecked() and action.isVisible()

    def log_scale(self) -> bool:
        """Tell whether the axes are logarithmic.

        Returns:
            bool: Whether the logarithmic axes are checked (and offered).
        """
        action = self.log_action
        return action is not None and action.isChecked() and action.isVisible()
