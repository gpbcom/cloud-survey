from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QModelIndex, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

# First Party Imports.
from gui.analysis.financials.tables.latest_values_model import LatestValuesModel


class LatestValuesTable(QTableView):
    """The table of the latest values of the company financials card: a double-click opens the document read.

    Attributes:
        model_ (LatestValuesModel): The rows.
        logger (Logger): The table logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build an empty table.

        Args:
            logger (Optional[Logger]): The table logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.model_ = LatestValuesModel(self, self.logger)
        self.setModel(self.model_)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)
        self.verticalHeader().setVisible(False)  # type: ignore[union-attr]
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)  # type: ignore[union-attr]
        header.setSectionResizeMode(  # type: ignore[union-attr]
            LatestValuesModel.INPUTS_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        self.doubleClicked.connect(self._open)
        self.setToolTip("Double-click a row to open the document its value was read from")

    ############################
    # Internal Helpers Methods #
    ############################

    def _open(self, index: QModelIndex) -> None:
        """Open the document of a row in the browser.

        Args:
            index (QModelIndex): The cell double-clicked.
        """
        address = self.model_.source(index.row())
        if not address.startswith("http"):
            self.logger.info("No document to open for row %d.", index.row())
            return
        if not QDesktopServices.openUrl(QUrl(address)):
            self.logger.warning("The document %s cannot be opened.", address)
