from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
from PyQt6.QtWidgets import QHBoxLayout, QToolButton, QWidget

# First Party Imports.
from gui.charts.sections.section.chart_section import ChartSection


class SectionsToolbar(QWidget):
    """Buttons expanding or collapsing every chart section of a tab at once.

    Attributes:
        sections (List[ChartSection]): The sections of the tab.
        expand_button (QToolButton): Expands every section.
        collapse_button (QToolButton): Collapses every section.
        logger (Logger): The toolbar logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build the toolbar, without sections.

        Args:
            logger (Optional[Logger]): The toolbar logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.sections: List[ChartSection] = []
        self.expand_button = QToolButton()
        self.expand_button.setObjectName("chartTool")
        self.expand_button.setText("Expand all")
        self.expand_button.setToolTip("Show every chart of the tab")
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("chartTool")
        self.collapse_button.setText("Collapse all")
        self.collapse_button.setToolTip("Fold every chart of the tab to its title")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.expand_button)
        layout.addWidget(self.collapse_button)
        self.expand_button.clicked.connect(lambda: self.set_all(True))
        self.collapse_button.clicked.connect(lambda: self.set_all(False))

    ############################
    # Publicly Exposed Methods #
    ############################

    def add(self, section: ChartSection) -> ChartSection:
        """Add a section of the tab.

        Args:
            section (ChartSection): The section.

        Returns:
            ChartSection: The same section, to add it to its layout too.
        """
        self.sections.append(section)
        self.logger.debug("Chart section %s added to the toolbar, %d sections.", section.key, len(self.sections))
        return section

    def set_all(self, expanded: bool) -> None:
        """Expand or collapse every section.

        Args:
            expanded (bool): Whether the sections are expanded.
        """
        self.logger.debug("%s %d chart sections.", "Expanding" if expanded else "Collapsing", len(self.sections))
        changed = 0
        for section in self.sections:
            if section.is_expanded() != expanded:
                section.set_expanded(expanded)
                changed += 1
        self.logger.info("%d chart sections %s.", changed, "expanded" if expanded else "collapsed")
