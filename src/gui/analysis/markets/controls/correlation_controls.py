from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

# First Party Imports.
from gui.analysis.markets.notes.markets_tooltips import MarketsTooltips
from gui.widgets.compact_combo import CompactCombo
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import MarketControl


class CorrelationControls(QWidget):
    """The pickers of the "Share vs …" card: the company, what its share is correlated with, and Correlate.

    Attributes:
        company_changed (pyqtSignal): Emitted when another company is picked (its counterparts are read again).
        against_changed (pyqtSignal): Emitted when another counterpart is picked.
        tooltips (MarketsTooltips): Writes the tooltips of the companies, the counterparts and the button.
        company_box (CompactCombo): The company, among those drawn in the share chart.
        against_box (CompactCombo): What its share is correlated with.
        correlate_button (QPushButton): Runs the correlation.
        counterparts (List[Counterpart]): The choices of `against_box`, in its order.
        logger (Logger): The controls logger.
    """

    company_changed = pyqtSignal()
    against_changed = pyqtSignal()

    def __init__(self, tooltips: MarketsTooltips, logger: Optional[Logger] = None) -> None:
        """Build the pickers, empty until the share chart is drawn.

        Args:
            tooltips (MarketsTooltips): The tooltip writer.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.tooltips = tooltips
        self.logger = logger if logger else getLogger(__name__)
        self.counterparts: List[Counterpart] = []
        self.company_box = CompactCombo(18)
        self.company_box.setToolTip(tooltips.control(MarketControl.COMPANY))
        self.against_box = CompactCombo(36)
        self.against_box.setToolTip(tooltips.control(MarketControl.AGAINST))
        self.correlate_button = QPushButton("Correlate")
        self.correlate_button.setToolTip(tooltips.control(MarketControl.CORRELATE))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Company"))
        layout.addWidget(self.company_box)
        layout.addWidget(QLabel("Against"))
        layout.addWidget(self.against_box)
        layout.addWidget(self.correlate_button)
        layout.addStretch(1)
        self.company_box.currentIndexChanged.connect(self.company_changed)
        self.against_box.currentIndexChanged.connect(self.against_changed)
        self.logger.debug("Correlation controls built.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def company(self) -> Optional[str]:
        """Get the company picked.

        Returns:
            Optional[str]: The company, `None` without any.
        """
        data = self.company_box.currentData()
        return str(data) if data else None

    def counterpart(self) -> Optional[Counterpart]:
        """Get what the company's share is correlated with.

        Returns:
            Optional[Counterpart]: The counterpart, `None` without any.
        """
        index = self.against_box.currentIndex()
        return self.counterparts[index] if 0 <= index < len(self.counterparts) else None

    def set_companies(self, companies: Sequence[str], names: Dict[str, str]) -> None:
        """List the companies drawn in the share chart, keeping the one picked when it is still drawn.

        Args:
            companies (Sequence[str]): The companies, in the order of the chart.
            names (Dict[str, str]): Their names.
        """
        current = self.company_box.currentData()
        self.company_box.blockSignals(True)
        self.company_box.clear()
        for key in companies:
            self.company_box.addItem(names.get(key, key), key)
            self.company_box.setItemData(
                self.company_box.count() - 1, self.tooltips.company(key), Qt.ItemDataRole.ToolTipRole
            )
        index = self.company_box.findData(current)
        self.company_box.setCurrentIndex(max(index, 0))
        self.company_box.blockSignals(False)
        self.logger.debug("%d companies offered to the correlation.", len(companies))
        self.company_changed.emit()

    def set_counterparts(self, counterparts: Sequence[Counterpart]) -> None:
        """List what the company's share can be correlated with, keeping the kind picked when it is offered again.

        Args:
            counterparts (Sequence[Counterpart]): The choices, in display order.
        """
        current = self.counterpart()
        self.counterparts = list(counterparts)
        self.against_box.blockSignals(True)
        self.against_box.clear()
        for position, counterpart in enumerate(self.counterparts):
            self.against_box.addItem(counterpart.label, position)
            self.against_box.setItemData(position, self.tooltips.counterpart(counterpart), Qt.ItemDataRole.ToolTipRole)
        same = next(
            (position for position, entry in enumerate(self.counterparts) if current and entry == current), None
        )
        kind = next(
            (position for position, entry in enumerate(self.counterparts) if current and entry.kind is current.kind),
            0,
        )
        self.against_box.setCurrentIndex(same if same is not None else kind)
        self.against_box.blockSignals(False)
        self.logger.debug("%d counterparts offered.", len(self.counterparts))
        self.against_changed.emit()
