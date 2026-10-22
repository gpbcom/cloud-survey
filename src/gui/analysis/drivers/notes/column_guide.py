from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

# First Party Imports.
from gui.theme import Theme
from models.drivers.enums import DriverColumn
from models.drivers.help.driver_help import DriverHelp


class ColumnGuide(QFrame):
    """How to read the table of the driver analysis: an entry per column, next to the table.

    Attributes:
        ENTRIES_PER_ROW (ClassVar[int]): The entries side by side.
        column_picked (pyqtSignal): Emitted with the index of a clicked entry: its column is selected in the table.
        theme (Theme): The application theme.
        help (DriverHelp): The explanation of each column.
        columns (List[DriverColumn]): The columns, in the order of the table.
        entries (List[QLabel]): The entry of each column.
        active (Optional[int]): The entry whose column is selected, if any.
        logger (Logger): The guide logger.

    Notes:
        Each entry says what its column shows. Hovering it tells how to read it (which values matter), clicking it
        selects the column in the table. The column headers carry the same explanation.
    """

    ENTRIES_PER_ROW: ClassVar[int] = 2

    column_picked = pyqtSignal(int)

    def __init__(
        self, theme: Theme, help_: DriverHelp, columns: Sequence[DriverColumn], logger: Optional[Logger] = None
    ) -> None:
        """Build the guide, an entry per column.

        Args:
            theme (Theme): The application theme.
            help_ (DriverHelp): The explanation of each column.
            columns (Sequence[DriverColumn]): The columns, in the order of the table.
            logger (Optional[Logger]): The guide logger.
        """
        super().__init__()
        self.theme, self.help, self.columns = theme, help_, list(columns)
        self.logger = logger if logger else getLogger(__name__)
        self.active: Optional[int] = None
        self.setObjectName("columnGuide")
        title = QLabel("How to read the table")
        title.setObjectName("guideTitle")
        title.setToolTip("Hover an entry for how to read it, click it to select its column")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        self.entries: List[QLabel] = []
        for index, column in enumerate(self.columns):
            entry = QLabel(self._text(column))
            entry.setObjectName("guideEntry")
            entry.setWordWrap(True)
            entry.setTextFormat(Qt.TextFormat.RichText)
            entry.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            entry.setAttribute(Qt.WidgetAttribute.WA_Hover)
            entry.setCursor(Qt.CursorShape.PointingHandCursor)
            entry.setToolTip(self._tooltip(column))
            entry.installEventFilter(self)
            grid.addWidget(entry, index // self.ENTRIES_PER_ROW, index % self.ENTRIES_PER_ROW)
            self.entries.append(entry)
        for position in range(self.ENTRIES_PER_ROW):
            grid.setColumnStretch(position, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addStretch(1)
        self.logger.debug("Column guide built with %d columns.", len(self.entries))

    ############################
    # Internal Helpers Methods #
    ############################

    def _title(self, column: DriverColumn) -> str:
        """Get the header of a column.

        Args:
            column (DriverColumn): The column.

        Returns:
            str: Its title, its key when it has no explanation.
        """
        explained = self.help.column(column)
        return explained.title if explained else column.value

    def _text(self, column: DriverColumn) -> str:
        """Write the entry of a column: its title and what it shows.

        Args:
            column (DriverColumn): The column.

        Returns:
            str: The rich text entry.
        """
        explained = self.help.column(column)
        summary = html.escape(explained.summary) if explained else ""
        return (
            f"<b style='color:{self.theme.ACCENT}'>{html.escape(self._title(column))}</b>"
            f"<br><span style='color:{self.theme.TEXT_MUTED}'>{summary}</span>"
        )

    def _tooltip(self, column: DriverColumn) -> str:
        """Explain a column: what it shows and how to read it.

        Args:
            column (DriverColumn): The column.

        Returns:
            str: The rich text explanation.
        """
        explained = self.help.column(column)
        if explained is None:
            return column.value
        return (
            f"<qt><p style='margin:0'><b style='color:{self.theme.ACCENT}'>{html.escape(explained.title)}</b></p>"
            f"<p>{html.escape(explained.summary)}</p><p><b>How to read it:</b> {html.escape(explained.reading)}</p>"
            "</qt>"
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def title(self, column: DriverColumn) -> str:
        """Get the header of a column, for the table.

        Args:
            column (DriverColumn): The column.

        Returns:
            str: Its title.
        """
        return self._title(column)

    def tooltip(self, column: DriverColumn) -> str:
        """Get the explanation of a column, for its header in the table.

        Args:
            column (DriverColumn): The column.

        Returns:
            str: The rich text explanation.
        """
        return self._tooltip(column)

    def set_active(self, index: Optional[int]) -> None:
        """Mark the entry whose column is selected in the table.

        Args:
            index (Optional[int]): The entry, `None` for none.
        """
        self.active = index
        for position, entry in enumerate(self.entries):
            entry.setProperty("active", position == index)
            style = entry.style()
            if style is not None:
                style.unpolish(entry)
                style.polish(entry)

    def eventFilter(self, watched: Optional[QObject], event: Optional[QEvent]) -> bool:
        """Select the column of a clicked entry (Qt override).

        Args:
            watched (Optional[QObject]): The widget receiving the event.
            event (Optional[QEvent]): The event.

        Returns:
            bool: Whether the event is consumed (never: the entries keep their behaviour).
        """
        if (
            event is not None
            and event.type() is QEvent.Type.MouseButtonRelease
            and isinstance(watched, QLabel)
            and watched in self.entries
        ):
            index = self.entries.index(watched)
            self.set_active(None if self.active == index else index)
            self.logger.debug("Column guide entry %s picked.", self.columns[index].value)
            self.column_picked.emit(-1 if self.active is None else index)
        return super().eventFilter(watched, event)
