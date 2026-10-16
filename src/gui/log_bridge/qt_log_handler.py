from __future__ import annotations

# Standard Library Imports.
import logging

# First Party Imports.
from gui.log_bridge.log_signals import LogSignals


class QtLogHandler(logging.Handler):
    """Logging handler forwarding the application log records to the GUI.

    Attributes:
        signals (LogSignals): The signals the records are emitted through.
    """

    def __init__(self, level: int = logging.DEBUG) -> None:
        """Initialize the handler.

        Args:
            level (int): The minimum level of the forwarded records.
        """
        super().__init__(level)
        self.signals = LogSignals()
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    ############################
    # Publicly Exposed Methods #
    ############################

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a log record to the GUI (logging override).

        Args:
            record (logging.LogRecord): The log record.
        """
        try:
            message = self.format(record)
        except Exception:  # The logging contract: a broken record must not break the application.
            self.handleError(record)
            return
        try:
            self.signals.record_emitted.emit(record.levelno, record.name, message)
        except RuntimeError:  # The Qt side is already deleted (application shutting down): nothing to show.
            return
