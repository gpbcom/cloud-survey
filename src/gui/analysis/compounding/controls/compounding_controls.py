from __future__ import annotations

# Standard Library Imports.
from functools import partial
from logging import Logger, getLogger
from typing import List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

# First Party Imports.
from gui.selection.pickers.provider_picker import ProviderPicker
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.cloud.enums import CloudProvider
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.enums import CompoundingControl, FoundationSource, Specification
from models.compounding.help.compounding_help import CompoundingHelp


class CompoundingControls(QWidget):
    """The pickers and buttons of the Service compounding section.

    Attributes:
        run_requested (pyqtSignal): Emitted when Run is clicked.
        export_requested (pyqtSignal): Emitted when Export CSV is clicked.
        crawl_requested (pyqtSignal): Emitted with `history` or `all` when a crawl button is clicked.
        help (CompoundingHelp): The explanations shown in the tooltips.
        providers (ProviderPicker): The providers fitted.
        specification_box (CompactCombo): The controls held constant.
        lag_box (QSpinBox): The years the foundations are held before the entry.
        source_box (CompactCombo): Where the foundations come from.
        run_button (QPushButton): Runs the analysis.
        export_button (QPushButton): Exports the summary table.
        history_button (QPushButton): Crawls the Synergy market history.
        crawl_button (QPushButton): Crawls every source of the analysis.
        logger (Logger): The controls logger.

    Notes:
        Every tooltip comes from the `compounding` block of `conf/help.yaml`.
    """

    run_requested = pyqtSignal()
    export_requested = pyqtSignal()
    crawl_requested = pyqtSignal(str)

    def __init__(
        self,
        theme: Theme,
        providers: Sequence[CloudProvider],
        help_texts: CompoundingHelp,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the controls.

        Args:
            theme (Theme): The application theme.
            providers (Sequence[CloudProvider]): The providers offered, every one picked.
            help_texts (CompoundingHelp): The explanations shown in the tooltips.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.help = help_texts
        self.logger = logger if logger else getLogger(__name__)
        self.providers = ProviderPicker(theme, providers, self.logger)
        self.specification_box = CompactCombo(18, self.logger)
        for specification in Specification:
            self.specification_box.addItem(help_texts.title("choices", specification.value), specification.value)
        self.lag_box = QSpinBox()
        self.lag_box.setRange(1, 5)
        self.lag_box.setSuffix(" y lag")
        self.source_box = CompactCombo(14, self.logger)
        for source in FoundationSource:
            self.source_box.addItem(help_texts.title("choices", source.value), source.value)
        self.run_button = QPushButton(help_texts.title("controls", CompoundingControl.RUN.value))
        self.export_button = QPushButton(help_texts.title("controls", CompoundingControl.EXPORT.value))
        self.history_button = QPushButton(help_texts.title("controls", CompoundingControl.CRAWL_HISTORY.value))
        self.crawl_button = QPushButton(help_texts.title("controls", CompoundingControl.CRAWL_ALL.value))
        self.run_button.clicked.connect(self.run_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.history_button.clicked.connect(partial(self.crawl_requested.emit, "history"))
        self.crawl_button.clicked.connect(partial(self.crawl_requested.emit, "all"))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, widget in (
            (CompoundingControl.PROVIDERS, self.providers),
            (CompoundingControl.SPECIFICATION, self.specification_box),
            (CompoundingControl.LAG, self.lag_box),
            (CompoundingControl.FOUNDATIONS, self.source_box),
        ):
            caption = QLabel(help_texts.title("controls", label.value))
            caption.setObjectName("muted")
            layout.addWidget(caption)
            layout.addWidget(widget)
        layout.addStretch(1)
        for button in (self.run_button, self.export_button, self.history_button, self.crawl_button):
            layout.addWidget(button)
        self._tooltips()
        self.logger.debug("Compounding controls built for %d providers.", len(providers))

    ############################
    # Internal Helpers Methods #
    ############################

    def _tooltips(self) -> None:
        """Explain every control and every choice in its tooltip."""
        for control, widget in (
            (CompoundingControl.PROVIDERS, self.providers),
            (CompoundingControl.SPECIFICATION, self.specification_box),
            (CompoundingControl.LAG, self.lag_box),
            (CompoundingControl.FOUNDATIONS, self.source_box),
            (CompoundingControl.RUN, self.run_button),
            (CompoundingControl.EXPORT, self.export_button),
            (CompoundingControl.CRAWL_HISTORY, self.history_button),
            (CompoundingControl.CRAWL_ALL, self.crawl_button),
        ):
            widget.setToolTip(self.help.text("controls", control.value))
        for box in (self.specification_box, self.source_box):
            for index in range(box.count()):
                box.setItemData(index, self.help.text("choices", str(box.itemData(index))), Qt.ItemDataRole.ToolTipRole)

    ############################
    # Publicly Exposed Methods #
    ############################

    def query(self) -> CompoundingQuery:
        """Get what the controls ask for.

        Returns:
            CompoundingQuery: The providers, the controls, the lag and the foundations picked.
        """
        picked: Optional[List[CloudProvider]] = self.providers.picked()
        return CompoundingQuery(
            providers=picked or [],
            specification=Specification(str(self.specification_box.currentData())),
            lag=self.lag_box.value(),
            source=FoundationSource(str(self.source_box.currentData())),
        )

    def set_busy(self, busy: bool) -> None:
        """Disable the buttons while the analysis runs.

        Args:
            busy (bool): Whether the analysis runs.
        """
        for button in (self.run_button, self.history_button, self.crawl_button):
            button.setEnabled(not busy)
