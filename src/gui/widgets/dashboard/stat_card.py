from __future__ import annotations

# Third Party Imports.
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

# First Party Imports.


class StatCard(QFrame):
    """Card showing a headline figure.

    Attributes:
        value_label (QLabel): The figure label.
        caption_label (QLabel): The caption under the figure.
    """

    def __init__(self, title: str) -> None:
        """Build an empty card.

        Args:
            title (str): The card title.
        """
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        title_label = QLabel(title.upper())
        title_label.setObjectName("muted")
        self.value_label = QLabel("\u2013")
        self.value_label.setObjectName("value")
        self.caption_label = QLabel("")
        self.caption_label.setObjectName("muted")
        for label in (title_label, self.value_label, self.caption_label):
            layout.addWidget(label)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_value(self, value: str, caption: str = "") -> None:
        """Show a figure.

        Args:
            value (str): The figure.
            caption (str): The caption under the figure.
        """
        self.value_label.setText(value)
        self.caption_label.setText(caption)
