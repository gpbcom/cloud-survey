from __future__ import annotations

# Standard Library Imports.
import html
import logging
from typing import ClassVar, Dict

# Third Party Imports.
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

# First Party Imports.
from gui.theme import Theme


class LogPanel(QWidget):
    """Live, colourized view of the application logs.

    Attributes:
        LEVELS (ClassVar[Dict[str, int]]): The selectable minimum levels.
        MAX_LINES (ClassVar[int]): The number of lines kept.
        theme (Theme): The application theme.
        level_box (QComboBox): The minimum level shown.
        view (QPlainTextEdit): The log lines.
        clear_button (QPushButton): Clears the log lines.
    """

    LEVELS: ClassVar[Dict[str, int]] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    MAX_LINES: ClassVar[int] = 5000

    def __init__(self, theme: Theme) -> None:
        """Build an empty panel, showing the INFO logs and above.

        Args:
            theme (Theme): The application theme.
        """
        super().__init__()
        self.theme = theme
        self.level_box = QComboBox()
        self.level_box.addItems(list(self.LEVELS))
        self.level_box.setCurrentText("INFO")
        self.clear_button = QPushButton("Clear")
        self.view = QPlainTextEdit()
        self.view.setMinimumHeight(60)
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(self.MAX_LINES)
        self.view.setStyleSheet("font-family: monospace; font-size: 12px;")
        self.clear_button.clicked.connect(self.view.clear)
        toolbar = QHBoxLayout()
        level_label = QLabel("Minimum level")
        level_label.setObjectName("muted")
        toolbar.addWidget(level_label)
        toolbar.addWidget(self.level_box)
        toolbar.addStretch(1)
        toolbar.addWidget(self.clear_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(toolbar)
        layout.addWidget(self.view)

    ############################
    # Publicly Exposed Methods #
    ############################

    def minimum_level(self) -> int:
        """Get the minimum level of the shown records.

        Returns:
            int: The minimum log level.
        """
        return self.LEVELS[self.level_box.currentText()]

    def append_record(self, level: int, logger_name: str, message: str) -> None:
        """Show a log record, coloured by level, when its level is high enough.

        Args:
            level (int): The record level number.
            logger_name (str): The record logger name.
            message (str): The formatted record.
        """
        if level < self.minimum_level():
            return
        color = self.theme.level_color(level)
        self.view.appendHtml(
            f'<span style="color:{color}; font-weight:600;">{html.escape(logging.getLevelName(level)):<8}</span> '
            f'<span style="color:{self.theme.TEXT_MUTED};">{html.escape(logger_name)}</span> '
            f'<span style="color:{self.theme.TEXT};">{html.escape(message)}</span>'
        )
