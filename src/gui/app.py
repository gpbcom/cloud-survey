from __future__ import annotations

# Standard Library Imports.
import os
import sys
from logging import Logger, getLogger
from typing import Final

# Third Party Imports.
from PyQt6.QtWidgets import QApplication

# First Party Imports.
from catalogue.store import CatalogueStore
from gui.main_window import MainWindow
from gui.theme import Theme
from logger import setup_logging

logger: Logger = getLogger(__name__)

# Qt's GTK / desktop portal platform themes read GNOME settings through GLib, which aborts the process when a key
# was removed from the desktop schemas (e.g. `antialiasing` in recent GNOME releases). The application draws its own
# look (Fusion style, palette, stylesheet): Qt's built-in generic theme is enough, unless the user chose another one.
PLATFORM_THEME: Final[str] = "generic"


def main() -> int:
    """GUI entrypoint: explore the catalogues of `output/` and launch crawls.

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
    window = MainWindow(CatalogueStore(), theme=theme)
    window.show()
    code = app.exec()
    logger.info("%s exited with code %d.", MainWindow.TITLE, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
