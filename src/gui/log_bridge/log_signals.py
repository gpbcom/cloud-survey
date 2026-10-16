from __future__ import annotations

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal


class LogSignals(QObject):
    """Qt signals of the log bridge, emitted from any thread and delivered in the GUI thread.

    Attributes:
        record_emitted (pyqtSignal): Emitted for each log record,
            with its level number, logger name and message.
    """

    record_emitted = pyqtSignal(int, str, str)
