from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from pytestqt.qtbot import QtBot

from gui.log_bridge.qt_log_handler import QtLogHandler


def test_forwards_the_records(qtbot: QtBot) -> None:
    handler = QtLogHandler()
    logger = logging.getLogger("tests.log_bridge")
    logger.addHandler(handler)
    try:
        with qtbot.waitSignal(handler.signals.record_emitted) as signal:
            logger.warning("Rate limited on %s", "scaleway")
    finally:
        logger.removeHandler(handler)

    level, name, message = signal.args
    assert (level, name) == (logging.WARNING, "tests.log_bridge")
    assert message.endswith("  Rate limited on scaleway")


def test_level(qtbot: QtBot) -> None:
    assert QtLogHandler().level == logging.DEBUG
    assert QtLogHandler(logging.ERROR).level == logging.ERROR


def test_broken_records_do_not_break_the_application(qtbot: QtBot) -> None:
    handler = QtLogHandler()
    record = logging.LogRecord("tests", logging.INFO, __file__, 1, "%d products", ("many",), None)

    with patch.object(handler, "handleError") as handle_error, qtbot.assertNotEmitted(handler.signals.record_emitted):
        handler.emit(record)

    handle_error.assert_called_once_with(record)


def test_deleted_bridge_is_ignored() -> None:
    handler = QtLogHandler()
    handler.signals = MagicMock()
    handler.signals.record_emitted.emit.side_effect = RuntimeError("wrapped C/C++ object has been deleted")

    handler.emit(logging.LogRecord("tests", logging.INFO, __file__, 1, "message", None, None))

    handler.signals.record_emitted.emit.assert_called_once()
