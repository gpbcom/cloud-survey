from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout

# First Party Imports.
from gui.catalogues.catalogue_tab import CatalogueTab
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.curated.enums import CuratedFile


class CataloguesManager(QDialog):
    """The window editing the curated catalogues: chronology, markets, companies, researched figures, launch dates.

    Attributes:
        MINIMUM_SIZE (ClassVar[Tuple[int, int]]): The smallest size of the window, in pixels.
        TITLES (ClassVar[Dict[CuratedFile, str]]): The title of the tab of each catalogue.
        edited (pyqtSignal): Emitted once an edit is written.
        tabs (QTabWidget): A tab per catalogue.
        editors (List[CatalogueTab]): The tabs, in the order of the catalogues.
        status_label (QLabel): What happened last.
        logger (Logger): The manager logger.

    Notes:
        - The window is not modal: the views stay usable while it is open.
        - The catalogues are read from the database and every edit is written there, checked first: the crawls use
          it at once, the Analysis and Patents & Papers tabs at the next start. Run `uv run curated export` to keep
          the edits in the bundle (`data/curated`), which seeds the other databases.
    """

    MINIMUM_SIZE: ClassVar[Tuple[int, int]] = (1100, 640)
    TITLES: ClassVar[Dict[CuratedFile, str]] = {
        CuratedFile.CHRONOLOGY: "Chronology",
        CuratedFile.MARKETS: "Markets",
        CuratedFile.COMPANIES: "Companies",
        CuratedFile.FIGURES: "Researched figures",
        CuratedFile.LAUNCHES: "Launch dates",
    }

    edited = pyqtSignal()

    def __init__(self, theme: Theme, loop: StorageLoop, logger: Optional[Logger] = None) -> None:
        """Build the window, read when shown.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            logger (Optional[Logger]): The manager logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.setWindowTitle("Curated catalogues")
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.tabs = QTabWidget()
        self.editors: List[CatalogueTab] = [CatalogueTab(theme, loop, file, self.logger) for file in CuratedFile]
        self.status_label = QLabel("Edits are written to the database: `uv run curated export` keeps them in git.")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        close = QPushButton("Close")
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(footer)
        for editor in self.editors:
            self.tabs.addTab(editor, self.TITLES[editor.file])
            editor.message.connect(self.status_label.setText)
            editor.edited.connect(self.edited.emit)
        close.clicked.connect(self.close)
        self.logger.debug("Catalogues manager built (%d catalogues).", len(self.editors))

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> None:
        """Read every catalogue."""
        self.logger.debug("Reading the curated catalogues for the manager.")
        for editor in self.editors:
            editor.load()

    def open_on(self, file: CuratedFile = CuratedFile.CHRONOLOGY) -> None:
        """Show the window on a catalogue, reading them.

        Args:
            file (CuratedFile): The catalogue shown.
        """
        self.logger.info("Catalogues manager opened on the %s.", file.value)
        self.tabs.setCurrentIndex(list(CuratedFile).index(file))
        self.load()
        self.show()
        self.raise_()
        self.activateWindow()
