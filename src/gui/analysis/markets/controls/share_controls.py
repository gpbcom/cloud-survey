from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QCompleter, QHBoxLayout, QLabel, QSpinBox, QWidget

# First Party Imports.
from gui.analysis.markets.notes.markets_tooltips import MarketsTooltips
from gui.widgets.compact_combo import CompactCombo
from models.markets.catalog.market_area import MarketArea
from models.markets.catalog.share_segment import ShareSegment
from models.markets.enums import AreaKind, Device, MarketControl
from models.markets.markets_catalog import MarketsCatalog


class ShareControls(QWidget):
    """The pickers of the market share chart: the segment, the area, the devices and the companies drawn.

    Attributes:
        DEVICE_NAMES (ClassVar[Dict[Device, str]]): The name of each device choice.
        GLOBE (ClassVar[str]): The symbol of the world and the continents in the area list.
        changed (pyqtSignal): Emitted when a picker changes.
        catalog (MarketsCatalog): The segments and the areas.
        segment_box (CompactCombo): The segment.
        area_box (CompactCombo): The area, with its flag, searchable by typing.
        device_box (CompactCombo): The devices, those of the segment.
        top_box (QSpinBox): The companies drawn on their own line.
        derivative_box (QCheckBox): Whether the chart draws the rate of change of each line.
        tooltips (Optional[MarketsTooltips]): Writes the tooltips of the pickers and their choices, `None` until
            `explain`.
        logger (Logger): The controls logger.
    """

    DEVICE_NAMES: ClassVar[Dict[Device, str]] = {
        Device.ALL: "All devices",
        Device.DESKTOP: "Desktop",
        Device.MOBILE: "Mobile",
        Device.TABLET: "Tablet",
    }
    GLOBE: ClassVar[str] = chr(0x1F310)

    changed = pyqtSignal()

    def __init__(self, catalog: MarketsCatalog, logger: Optional[Logger] = None) -> None:
        """Build the pickers on the first segment, worldwide.

        Args:
            catalog (MarketsCatalog): The segments and the areas.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.catalog = catalog
        self.logger = logger if logger else getLogger(__name__)
        self.tooltips: Optional[MarketsTooltips] = None
        self.segment_box = CompactCombo(20)
        self.segment_box.setToolTip("The market followed")
        for segment in catalog.segments:
            self.segment_box.addItem(segment.label, segment.key)
        self.area_box = CompactCombo(20)
        self.area_box.setEditable(True)
        self.area_box.setInsertPolicy(CompactCombo.InsertPolicy.NoInsert)
        self.area_box.setToolTip(
            "The area: worldwide, a continent, the EU-27 (estimated) or a country. Type to search."
        )
        for area in catalog.areas:
            self.area_box.addItem(f"{self._flag(area)} {area.label}", area.key)
        completer = self.area_box.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.device_box = CompactCombo(12)
        self.device_box.setToolTip("The devices the shares are measured on")
        self.top_box = QSpinBox()
        self.top_box.setRange(1, 20)
        self.top_box.setValue(8)
        self.top_box.setPrefix("Top ")
        self.top_box.setToolTip("The companies drawn on their own line, by peak share (the rest is Others)")
        self.derivative_box = QCheckBox("Rate of change")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label, widget in (
            ("Segment", self.segment_box),
            ("Area", self.area_box),
            ("", self.device_box),
            ("", self.top_box),
            ("", self.derivative_box),
        ):
            if label:
                layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        layout.addStretch(1)
        self._fill_devices()
        self.segment_box.currentIndexChanged.connect(self._on_segment)
        self.area_box.currentIndexChanged.connect(self.changed)
        self.device_box.currentIndexChanged.connect(self.changed)
        self.top_box.valueChanged.connect(self.changed)
        self.logger.debug("Share controls built: %d segments, %d areas.", len(catalog.segments), len(catalog.areas))

    ############################
    # Internal Helpers Methods #
    ############################

    def _flag(self, area: MarketArea) -> str:
        """Get the symbol of an area: its flag, or a globe for the world and the continents.

        Args:
            area (MarketArea): The area.

        Returns:
            str: The flag of a country (its two regional indicator letters), the EU flag for a union, else a globe.
        """
        code = area.key if area.kind is AreaKind.COUNTRY else "EU" if area.kind is AreaKind.UNION else ""
        if len(code) != 2:
            return self.GLOBE
        return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code.upper())

    def _segment(self) -> ShareSegment:
        """Get the segment picked.

        Returns:
            ShareSegment: The segment.
        """
        return self.catalog.segment(str(self.segment_box.currentData())) or self.catalog.segments[0]

    def _fill_devices(self, device: Optional[Device] = None) -> None:
        """List the devices of the segment picked, without telling.

        Args:
            device (Optional[Device]): The device to pick, the segment's first by default.
        """
        segment = self._segment()
        self.device_box.blockSignals(True)
        self.device_box.clear()
        for choice in segment.devices:
            self.device_box.addItem(self.DEVICE_NAMES[choice], choice.value)
            if self.tooltips is not None:
                self.device_box.setItemData(
                    self.device_box.count() - 1,
                    self.tooltips.device(choice.value, self.DEVICE_NAMES[choice]),
                    Qt.ItemDataRole.ToolTipRole,
                )
        index = self.device_box.findData(device.value) if device is not None else -1
        self.device_box.setCurrentIndex(max(index, 0))
        self.device_box.blockSignals(False)

    def _on_segment(self) -> None:
        """List the devices of the new segment, then tell."""
        self._fill_devices()
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def explain(self, tooltips: MarketsTooltips) -> None:
        """Write the tooltip of every picker and of every choice of its list.

        Args:
            tooltips (MarketsTooltips): The tooltip writer.
        """
        self.tooltips = tooltips
        for index, segment in enumerate(self.catalog.segments):
            self.segment_box.setItemData(index, tooltips.segment(segment), Qt.ItemDataRole.ToolTipRole)
        for index, area in enumerate(self.catalog.areas):
            self.area_box.setItemData(index, tooltips.area(area), Qt.ItemDataRole.ToolTipRole)
        for box, control in (
            (self.segment_box, MarketControl.SEGMENT),
            (self.area_box, MarketControl.AREA),
            (self.device_box, MarketControl.DEVICE),
        ):
            box.setToolTip(tooltips.control(control))
        self.top_box.setToolTip(tooltips.control(MarketControl.TOP))
        self.derivative_box.setToolTip(tooltips.control(MarketControl.DERIVATIVE))
        device = self.device_box.currentData()
        self._fill_devices(Device(str(device)) if device else None)
        self.logger.debug("Share controls explained.")

    def query(self) -> Tuple[ShareSegment, MarketArea, Device, int]:
        """Get what the chart shows.

        Returns:
            Tuple[ShareSegment, MarketArea, Device, int]: The segment, the area, the devices and the top count.
        """
        area = self.catalog.area(str(self.area_box.currentData())) or self.catalog.areas[0]
        device = Device(str(self.device_box.currentData() or Device.ALL.value))
        return self._segment(), area, device, self.top_box.value()

    def set_segment(self, segment: str, area: Optional[str] = None) -> bool:
        """Pick a segment (and an area), as a click on a leader band does.

        Args:
            segment (str): The segment key.
            area (Optional[str]): The area key, unchanged when `None`.

        Returns:
            bool: Whether the segment exists.
        """
        index = self.segment_box.findData(segment)
        if index < 0:
            return False
        self.segment_box.blockSignals(True)
        self.segment_box.setCurrentIndex(index)
        self.segment_box.blockSignals(False)
        self._fill_devices()
        if area is not None and self.area_box.findData(area) >= 0:
            self.area_box.blockSignals(True)
            self.area_box.setCurrentIndex(self.area_box.findData(area))
            self.area_box.blockSignals(False)
        self.changed.emit()
        return True
