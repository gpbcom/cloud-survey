from __future__ import annotations

# Standard Library Imports.
import os
import sys
from logging import Logger, getLogger
from typing import Final, Tuple

# Third Party Imports.
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

# First Party Imports.
from crawler.runner import CatalogueRunner
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from gui.window.main_window import MainWindow
from logger import setup_logging
from storage.engine.settings_reader import StorageSettingsReader
from storage.storage import Storage

logger: Logger = getLogger(__name__)

# Qt's GTK / desktop portal platform themes read GNOME settings through GLib, which aborts the process when a key
# was removed from the desktop schemas (e.g. `antialiasing` in recent GNOME releases). The application draws its own
# look (Fusion style, palette, stylesheet): Qt's built-in generic theme is enough, unless the user chose another one.
PLATFORM_THEME: Final[str] = "generic"
# The chart states (expanded sections, chosen axes) are remembered in the user's settings: organization, file name.
CHART_SETTINGS: Final[Tuple[str, str]] = ("poc-crawler", "charts")


def main() -> int:
    """GUI entrypoint: explore the stored catalogues, marketplaces and statistics, and launch crawls.

    The window reads the storage in its own thread (`StorageLoop`), each crawl writing with the storage of the runner
    in the event loop of the crawl: the two never share a connection.

    Returns:
        int: The application exit code.
    """
    setup_logging()
    logger.info("Starting the %s.", MainWindow.TITLE)
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", PLATFORM_THEME)
    logger.debug("Qt platform theme: %s.", os.environ["QT_QPA_PLATFORMTHEME"])
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    app.setApplicationName(MainWindow.TITLE)
    theme = Theme()
    theme.apply(app)
    settings = StorageSettingsReader().read()
    charts = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, CHART_SETTINGS[0], CHART_SETTINGS[1])
    store = ChartStateStore(charts)
    window = MainWindow(
        StorageLoop(Storage(settings)), CatalogueRunner(storage=Storage(settings)), theme=theme, store=store
    )
    window.show()
    code = app.exec()
    logger.info("%s exited with code %d.", MainWindow.TITLE, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
