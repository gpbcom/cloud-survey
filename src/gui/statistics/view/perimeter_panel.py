from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFrame, QGroupBox, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport


class PerimeterPanel(QWidget):
    """Checkboxes selecting the perimeter of the market statistics: regions, segments, players and periods.

    The regions and segments absent from the data are disabled. The players and the periods are those of the data,
    the newest period first.

    Attributes:
        perimeter_changed (pyqtSignal): Emitted when a checkbox is checked or unchecked.
        theme (Theme): The application theme.
        region_boxes (Dict[MarketRegion, QCheckBox]): The checkbox of each region.
        segment_boxes (Dict[MarketSegment, QCheckBox]): The checkbox of each segment.
        player_boxes (Dict[MarketPlayer, QCheckBox]): The checkbox of each player of the data, plus the others.
        period_boxes (Dict[str, QCheckBox]): The checkbox of each period of the data, the newest first.
        latest_button (QPushButton): Checks the newest period only.
        all_button (QPushButton): Checks every period.
    """

    perimeter_changed = pyqtSignal()

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build the panel, without data: only Worldwide and Cloud infrastructure services are checked.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.setMinimumWidth(240)
        self.setMaximumWidth(300)
        self.region_boxes: Dict[MarketRegion, QCheckBox] = {}
        self.segment_boxes: Dict[MarketSegment, QCheckBox] = {}
        self.player_boxes: Dict[MarketPlayer, QCheckBox] = {}
        self.period_boxes: Dict[str, QCheckBox] = {}
        region_group, self.region_layout = self._group("Region")
        for region in MarketRegion:
            self.region_boxes[region] = self._check_box(theme.REGION_LABELS[region], self.region_layout)
        segment_group, self.segment_layout = self._group("Segment")
        for segment in MarketSegment:
            self.segment_boxes[segment] = self._check_box(theme.SEGMENT_LABELS[segment], self.segment_layout)
        self.region_boxes[MarketRegion.WORLDWIDE].setChecked(True)
        self.segment_boxes[MarketSegment.CLOUD_INFRASTRUCTURE].setChecked(True)
        player_group, self.player_layout = self._group("Providers")
        period_group, self.period_layout = self._group("Period")
        self.latest_button = QPushButton("Latest")
        self.all_button = QPushButton("All")
        buttons = QHBoxLayout()
        buttons.addWidget(self.latest_button)
        buttons.addWidget(self.all_button)
        periods = QWidget()
        periods.setLayout(self.period_layout)
        period_area = QScrollArea()
        period_area.setWidget(periods)
        period_area.setWidgetResizable(True)
        period_area.setFrameShape(QFrame.Shape.NoFrame)
        period_box_layout = QVBoxLayout()
        period_box_layout.addLayout(buttons)
        period_box_layout.addWidget(period_area)
        period_group.setLayout(period_box_layout)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for group in (region_group, segment_group, player_group):
            layout.addWidget(group)
        layout.addWidget(period_group, 1)
        self.latest_button.clicked.connect(self.select_latest)
        self.all_button.clicked.connect(self.select_all_periods)

    ############################
    # Internal Helpers Methods #
    ############################

    def _group(self, title: str) -> Tuple[QGroupBox, QVBoxLayout]:
        """Build a titled group of checkboxes.

        Args:
            title (str): The group title.

        Returns:
            Tuple[QGroupBox, QVBoxLayout]: The group and the layout of its checkboxes.
        """
        group = QGroupBox(title)
        layout = QVBoxLayout()
        if title != "Period":
            group.setLayout(layout)
        return group, layout

    def _check_box(self, label: str, layout: QVBoxLayout) -> QCheckBox:
        """Add a checkbox emitting `perimeter_changed` when toggled.

        Args:
            label (str): The checkbox label.
            layout (QVBoxLayout): The layout receiving it.

        Returns:
            QCheckBox: The checkbox.
        """
        box = QCheckBox(label)
        box.toggled.connect(lambda checked: self.perimeter_changed.emit())
        layout.addWidget(box)
        return box

    def _clear(self, boxes: Union[Dict[str, QCheckBox], Dict[MarketPlayer, QCheckBox]]) -> None:
        """Remove checkboxes from the panel.

        Args:
            boxes (Union[Dict[str, QCheckBox], Dict[MarketPlayer, QCheckBox]]): The checkboxes, emptied.
        """
        for box in boxes.values():
            box.setParent(None)
            box.deleteLater()
        boxes.clear()

    def _drop_stretches(self, layout: QVBoxLayout) -> None:
        """Remove the stretches of a layout, so that the checkboxes added again stay at its top.

        Args:
            layout (QVBoxLayout): The layout.
        """
        stretches = [index for index in range(layout.count()) if (item := layout.itemAt(index)) and item.spacerItem()]
        for index in reversed(stretches):
            layout.takeAt(index)
        self.logger.debug("%d stretches removed from a perimeter group.", len(stretches))

    def _set_checked(self, boxes: Sequence[QCheckBox], checked: Set[int]) -> None:
        """Check some checkboxes and uncheck the others, emitting `perimeter_changed` once.

        Args:
            boxes (Sequence[QCheckBox]): The checkboxes.
            checked (Set[int]): The positions of the checked ones.
        """
        for index, box in enumerate(boxes):
            box.blockSignals(True)
            box.setChecked(index in checked)
            box.blockSignals(False)
        self.perimeter_changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_reports(self, reports: Sequence[MarketReport]) -> None:
        """Show the regions, segments, players and periods of the data, keeping the previous choices.

        Args:
            reports (Sequence[MarketReport]): The market reports.
        """
        checked_players = {player for player, box in self.player_boxes.items() if box.isChecked()}
        checked_periods = {period for period, box in self.period_boxes.items() if box.isChecked()}
        first_load = not self.player_boxes and not self.period_boxes
        for region, box in self.region_boxes.items():
            box.setEnabled(any(report.region is region for report in reports))
        for segment, box in self.segment_boxes.items():
            box.setEnabled(any(report.segment is segment for report in reports))
        self._clear(self.player_boxes)
        self._clear(self.period_boxes)
        self._drop_stretches(self.period_layout)
        found = {share.player for report in reports for share in report.shares}
        players = [player for player in MarketPlayer if player in found]
        if players:
            players.append(MarketPlayer.OTHERS)
        for player in players:
            box = self._check_box(self.theme.player_label(player), self.player_layout)
            box.blockSignals(True)
            box.setChecked(first_load or player in checked_players)
            box.blockSignals(False)
            self.player_boxes[player] = box
        keys = {report.period: report.sort_key() for report in reports}
        for period in sorted(keys, key=lambda period: keys[period], reverse=True):
            box = self._check_box(period, self.period_layout)
            box.blockSignals(True)
            box.setChecked(first_load or period in checked_periods)
            box.blockSignals(False)
            self.period_boxes[period] = box
        self.period_layout.addStretch(1)
        self.logger.debug("Perimeter panel: %d players, %d periods.", len(players), len(keys))
        self.perimeter_changed.emit()

    def regions(self) -> List[MarketRegion]:
        """Get the checked regions.

        Returns:
            List[MarketRegion]: The checked and enabled regions, in enum order.
        """
        return [region for region, box in self.region_boxes.items() if box.isChecked() and box.isEnabled()]

    def segments(self) -> List[MarketSegment]:
        """Get the checked segments.

        Returns:
            List[MarketSegment]: The checked and enabled segments, in enum order.
        """
        return [segment for segment, box in self.segment_boxes.items() if box.isChecked() and box.isEnabled()]

    def players(self) -> List[MarketPlayer]:
        """Get the checked players.

        Returns:
            List[MarketPlayer]: The checked players, in enum order.
        """
        return [player for player, box in self.player_boxes.items() if box.isChecked()]

    def periods(self) -> List[str]:
        """Get the checked periods.

        Returns:
            List[str]: The checked periods, the newest first.
        """
        return [period for period, box in self.period_boxes.items() if box.isChecked()]

    def select_latest(self) -> None:
        """Check the newest period only."""
        self._set_checked(list(self.period_boxes.values()), {0})

    def select_all_periods(self) -> None:
        """Check every period."""
        self._set_checked(list(self.period_boxes.values()), set(range(len(self.period_boxes))))
