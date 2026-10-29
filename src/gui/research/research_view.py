from __future__ import annotations

# Standard Library Imports.
from datetime import datetime, timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

from pydantic import JsonValue

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from analytics.companies.progress.research_row_reader import ResearchRowReader

# First Party Imports.
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from gui.research.picker.company_picker import CompanyPicker
from gui.research.progress.feed_table import FeedTable
from gui.research.progress.progress_table import ProgressTable
from gui.research.stored.stored_browser import StoredBrowser
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.companies.enums import CompanyFeed
from models.companies.progress.research_coverage import ResearchCoverage
from models.curated.records.catalogue_set import CatalogueSet
from storage.exception import StorageError
from storage.storage import Storage


class ResearchView(QWidget):
    """The Patents & Papers tab: search the patents and the research papers of one company or several.

    Attributes:
        PATENT_SOURCES (ClassVar[List[Tuple[CompanyFeed, str, str, bool]]]): The Google Patents sources, their label,
            their tooltip and whether they are checked at first.
        BUSY_RETRY_MINUTES (ClassVar[int]): The minutes an automatic resume waits again while another crawl runs.
        PANELS (ClassVar[List[Tuple[str, str]]]): The label and the tooltip of each panel of the right side.
        search_requested (pyqtSignal): Emitted with the companies picked and the source values checked.
        stop_requested (pyqtSignal): Emitted when Stop is clicked.
        theme (Theme): The application theme.
        loop (StorageLoop): Runs the database reads off the GUI thread.
        catalogues (Optional[CatalogueSet]): The curated catalogues naming the companies, `None` for the bundle.
        reader (ResearchRowReader): Turns the streamed facts into rows.
        names (Dict[str, str]): The name of each company of the catalogue.
        picker (CompanyPicker): The companies searched.
        sources (Dict[CompanyFeed, QCheckBox]): The Google Patents sources searched.
        resume_box (QCheckBox): Whether a patents search Google Patents refused is resumed by itself later.
        patents_button (QPushButton): Starts the patents search (Google Patents).
        papers_button (QPushButton): Starts the papers search (OpenAlex).
        stop_button (QPushButton): Ends the search gracefully, or cancels an automatic resume.
        resume_minutes (int): The minutes an automatic resume waits after a refusal (the catalogue's
            `patents.resume_minutes`).
        resume_timer (QTimer): Fires the automatic resume.
        resume_search (Optional[Tuple[List[str], List[CompanyFeed]]]): The companies and the sources of the last
            patents search, the one resumed.
        status (QLabel): What the search is doing.
        progress (ProgressTable): The progress of each company.
        feed (FeedTable): The facts as they arrive.
        stored (StoredBrowser): What the database holds of the companies picked, page by page.
        panel_group (QButtonGroup): The switch between the live search and the stored data.
        panels (QStackedWidget): The live search, then the stored data.
        coverage (Dict[str, ResearchCoverage]): What the database holds, by company.
        searching (bool): Whether a search of this tab runs.
        crawling (bool): Whether any crawl of the window runs (Search is then disabled).
        logger (Logger): The view logger.

    Notes:
        - The search runs in the window's crawl thread (one crawl at a time): the facts are written by batches of a
          few dozens and each batch is shown at once, in the progress and in the feed.
        - The patents (Google Patents) and the papers (OpenAlex) are searched apart, each with its own button.
        - Google Patents refuses the searches after a few requests: the search then ends, says so, and the next one
          resumes from the windows already read. When asked to, the tab resumes it by itself once the refusal is
          likely lifted. Stop ends a search the same way, after the requests in flight, or cancels that resume.
        - The Stored data panel shows the companies picked (every company when none is), and is read again when
          the picking changes, when a search ends and when the tab is opened.
    """

    PATENT_SOURCES: ClassVar[List[Tuple[CompanyFeed, str, str, bool]]] = [
        (
            CompanyFeed.GOOGLE_PATENTS,
            "Publications",
            "The publications of the company's assignees on Google Patents, window by window (resumed run after run)",
            True,
        ),
        (
            CompanyFeed.GOOGLE_PATENT_PAGES,
            "Publication pages",
            "The citations, families and classes of the company's publications waiting for their Google Patents page",
            False,
        ),
    ]
    BUSY_RETRY_MINUTES: ClassVar[int] = 5

    PANELS: ClassVar[List[Tuple[str, str]]] = [
        ("Live search", "The progress of the search running, company by company, and the facts as they arrive"),
        ("Stored data", "Every patent, paper, researcher, profile and search window stored for the companies picked"),
    ]

    search_requested = pyqtSignal(list, list)
    stop_requested = pyqtSignal()

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        logger: Optional[Logger] = None,
        catalogues: Optional[CatalogueSet] = None,
    ) -> None:
        """Build the tab.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): Runs the database reads off the GUI thread.
            logger (Optional[Logger]): The view logger.
            catalogues (Optional[CatalogueSet]): The curated catalogues naming the companies, those of the bundle by
                default.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.logger = logger if logger else getLogger(__name__)
        self.catalogues = catalogues
        self.reader = ResearchRowReader()
        self.names = self._names()
        self.picker = CompanyPicker(list(self.names.items()), self.logger)
        self.sources: Dict[CompanyFeed, QCheckBox] = {}
        for feed, label, tooltip, checked in self.PATENT_SOURCES:
            box = QCheckBox(label)
            box.setToolTip(tooltip)
            box.setChecked(checked)
            box.toggled.connect(self._update_buttons)
            self.sources[feed] = box
        self.resume_minutes = self._resume_minutes()
        self.resume_box = QCheckBox("Resume when Google Patents refuses")
        self.resume_box.setChecked(True)
        self.resume_box.setToolTip(
            f"Google Patents refuses this machine after a few searches: resume the search by itself "
            f"{self.resume_minutes} minutes later, from where it stopped"
        )
        self.patents_button = QPushButton("Search patents")
        self.patents_button.setToolTip("Search the publications of the companies picked on Google Patents")
        self.papers_button = QPushButton("Search papers")
        self.papers_button.setToolTip(
            "Search the papers of the companies' institutions on OpenAlex, and the profiles of their researchers"
        )
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip(
            "End the search after the requests in flight (what was read is kept), or cancel an automatic resume"
        )
        self.resume_timer = QTimer(self)
        self.resume_timer.setSingleShot(True)
        self.resume_search: Optional[Tuple[List[str], List[CompanyFeed]]] = None
        self.status = QLabel("Pick one company, or several with Ctrl or Shift, then search its patents or papers.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.progress = ProgressTable(self.names, self.logger)
        self.feed = FeedTable(self.names, self.logger)
        self.stored = StoredBrowser(loop, self.logger)
        self.panel_group = QButtonGroup(self)
        self.panels = QStackedWidget()
        self.coverage: Dict[str, ResearchCoverage] = {}
        self.searching = False
        self.crawling = False
        self.picker.changed.connect(self._update_buttons)
        self.picker.changed.connect(self._show_stored)
        self.patents_button.clicked.connect(self.search_patents)
        self.papers_button.clicked.connect(self.search_papers)
        self.stop_button.clicked.connect(self.stop)
        self.resume_timer.timeout.connect(self._resume)
        self.setLayout(self._layout())
        self.panel_group.idClicked.connect(self._on_panel)
        self._update_buttons()
        self.logger.debug("Patents & Papers tab built with %d companies.", len(self.names))

    ############################
    # Internal Helpers Methods #
    ############################

    def _names(self) -> Dict[str, str]:
        """Get the name of each company of the catalogue.

        Returns:
            Dict[str, str]: The name of each company key, the key itself when the chronology has none.
        """
        if self.catalogues is not None:
            labels = {company.key: company.label for company in self.catalogues.chronology.companies}
            return {entry.key: labels.get(entry.key, entry.key) for entry in self.catalogues.companies.companies}
        bundled = BundleCatalogs(logger=self.logger)
        try:
            catalog = bundled.companies()
        except CuratedError as e:
            self.logger.warning("The companies catalogue cannot be read: %s", e)
            return {}
        try:
            labels = {company.key: company.label for company in bundled.chronology().companies}
        except CuratedError as e:
            self.logger.warning("The chronology cannot be read: the company keys are shown: %s", e)
            labels = {}
        return {entry.key: labels.get(entry.key, entry.key) for entry in catalog.companies}

    def _resume_minutes(self) -> int:
        """Get the pause before a refused patents search is resumed.

        Returns:
            int: The catalogue's `patents.resume_minutes`, an hour when the catalogue cannot be read.
        """
        if self.catalogues is not None:
            return self.catalogues.companies.patents.resume_minutes
        try:
            return BundleCatalogs(logger=self.logger).companies().patents.resume_minutes
        except CuratedError as e:
            self.logger.warning(
                "The companies catalogue cannot be read: a refused search resumes after 60 min: %s",
                e,
            )
            return 60

    def _layout(self) -> QHBoxLayout:
        """Lay out the picker on the left, the progress and the feed on the right.

        Returns:
            QHBoxLayout: The layout of the tab.
        """
        left = QWidget()
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Companies")
        title.setObjectName("title")
        column.addWidget(title)
        column.addWidget(self.picker, 1)
        patents = QGroupBox("Patents · Google Patents")
        patents_column = QVBoxLayout(patents)
        for box in self.sources.values():
            patents_column.addWidget(box)
        patents_column.addWidget(self.resume_box)
        patents_column.addWidget(self.patents_button)
        column.addWidget(patents)
        papers = QGroupBox("Papers · OpenAlex")
        papers_column = QVBoxLayout(papers)
        described = QLabel("Papers of the companies' institutions and their researchers")
        described.setObjectName("muted")
        described.setWordWrap(True)
        papers_column.addWidget(described)
        papers_column.addWidget(self.papers_button)
        column.addWidget(papers)
        column.addWidget(self.stop_button)
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.progress)
        right.addWidget(self.feed)
        right.setStretchFactor(0, 1)
        right.setStretchFactor(1, 2)
        live = QWidget()
        live_column = QVBoxLayout(live)
        live_column.setContentsMargins(0, 0, 0, 0)
        live_column.addWidget(self.status)
        live_column.addWidget(right, 1)
        self.panels.addWidget(live)
        self.panels.addWidget(self.stored)
        switch = QHBoxLayout()
        switch.setSpacing(4)
        for index, (label, tooltip) in enumerate(self.PANELS):
            button = QToolButton()
            button.setObjectName("segment")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.setChecked(index == 0)
            self.panel_group.addButton(button, index)
            switch.addWidget(button)
        switch.addStretch(1)
        panel = QWidget()
        stack = QVBoxLayout(panel)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addLayout(switch)
        stack.addWidget(self.panels, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(panel)
        splitter.setStretchFactor(1, 3)
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        return layout

    def _checked(self) -> List[CompanyFeed]:
        """Get the Google Patents sources checked.

        Returns:
            List[CompanyFeed]: The sources, in the order they run.
        """
        return [feed for feed, box in self.sources.items() if box.isChecked()]

    def _update_buttons(self) -> None:
        """Enable the searches with companies picked while no crawl runs, Stop while a search runs or will resume."""
        picked = len(self.picker.selected())
        scope = "" if picked < 2 else f" ({picked} companies)" if picked < len(self.names) else " (all)"
        self.patents_button.setEnabled(not self.crawling and picked > 0 and bool(self._checked()))
        self.patents_button.setText(f"Search patents{scope}")
        self.papers_button.setEnabled(not self.crawling and picked > 0)
        self.papers_button.setText(f"Search papers{scope}")
        self.stop_button.setEnabled(self.searching or self.resume_timer.isActive())

    def _resume(self) -> None:
        """Resume the refused patents search, or wait again while another crawl runs."""
        if self.resume_search is None:
            return
        if self.crawling:
            self.logger.info("Automatic resume delayed: another crawl runs.")
            self.resume_timer.start(self.BUSY_RETRY_MINUTES * 60_000)
            self.status.setText(f"Another crawl runs: the patents search resumes in {self.BUSY_RETRY_MINUTES} minutes.")
            return
        companies, feeds = self.resume_search
        self.logger.info("Patents search of %d companies resumed after a refusal.", len(companies))
        self.search_requested.emit(list(companies), [feed.value for feed in feeds])

    async def _read_coverage(self, storage: Storage) -> Dict[str, ResearchCoverage]:
        """Read what the database holds of each company.

        Args:
            storage (Storage): The open storage.

        Returns:
            Dict[str, ResearchCoverage]: What is stored, by company.

        Raises:
            StorageError: If the database cannot be read.
        """
        patents = await storage.patents.coverage()
        papers = await storage.papers.coverage()
        coverage: Dict[str, ResearchCoverage] = {}
        for company in sorted({*patents, *papers}):
            found, pages, done, still = patents.get(company, (0, 0, 0, 0))
            written, people = papers.get(company, (0, 0))
            coverage[company] = ResearchCoverage(
                company=company,
                patents=found,
                pages=pages,
                windows_done=done,
                windows_open=still,
                papers=written,
                researchers=people,
            )
        return coverage

    def _on_coverage(self, coverage: Dict[str, ResearchCoverage]) -> None:
        """Show what the database holds.

        Args:
            coverage (Dict[str, ResearchCoverage]): What is stored, by company.
        """
        if sip.isdeleted(self):
            return
        self.coverage = coverage
        self.picker.set_coverage(coverage)
        self.progress.set_coverage(coverage)
        self.logger.debug("Patents & Papers coverage shown for %d companies.", len(coverage))

    def _stored_shown(self) -> bool:
        """Tell whether the Stored data panel is shown.

        Returns:
            bool: Whether it is the current panel.
        """
        return self.panels.currentWidget() is self.stored

    def _show_stored(self) -> None:
        """Show the stored data of the companies picked, when the Stored data panel is shown."""
        if self._stored_shown():
            self.stored.set_companies(self.picker.selected())

    def _on_panel(self, index: int) -> None:
        """Show a panel of the right side.

        Args:
            index (int): The live search (0) or the stored data (1).
        """
        self.logger.info("Patents & Papers panel shown: %s.", self.PANELS[index][0])
        self.panels.setCurrentIndex(index)
        self._show_stored()

    def _on_coverage_error(self, error: StorageError) -> None:
        """Report a storage error of the coverage.

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self):
            return
        self.logger.warning("The patents and papers stored cannot be read: %s", error)
        self.status.setText(f"What is stored cannot be read: {error}")

    ############################
    # Publicly Exposed Methods #
    ############################

    def feeds(self) -> List[CompanyFeed]:
        """Get the sources checked.

        Returns:
            List[CompanyFeed]: The sources, in the order they run.
        """
        return self._checked()

    def refresh(self) -> None:
        """Read again what the database holds of each company, and the stored data shown."""
        self.loop.submit(self._read_coverage, self._on_coverage, self._on_coverage_error)
        if self._stored_shown():
            self.stored.refresh()
        else:
            self.stored.invalidate()

    def show_panel(self, index: int) -> None:
        """Show the live search (0) or the stored data (1), as a click on the switch does.

        Args:
            index (int): The panel.
        """
        button = self.panel_group.button(index)
        if button is not None:
            button.setChecked(True)
        self._on_panel(index)

    def search_patents(self) -> None:
        """Ask the window to search the patents of the companies picked on Google Patents."""
        companies, feeds = self.picker.selected(), self.feeds()
        if not companies or not feeds:
            self.logger.warning("No patents search without a company and a Google Patents source.")
            return
        self.logger.info(
            "Patents search (%s) requested for %d companies.", ", ".join(feed.value for feed in feeds), len(companies)
        )
        self.resume_timer.stop()
        self.resume_search = (list(companies), list(feeds))
        self.search_requested.emit(companies, [feed.value for feed in feeds])

    def search_papers(self) -> None:
        """Ask the window to search the papers of the companies picked on OpenAlex."""
        companies = self.picker.selected()
        if not companies:
            self.logger.warning("No papers search without a company.")
            return
        self.logger.info("Papers search requested for %d companies.", len(companies))
        self.search_requested.emit(companies, [CompanyFeed.OPENALEX.value])

    def stop(self) -> None:
        """Ask the window to end the search gracefully, or cancel an automatic resume."""
        if self.resume_timer.isActive() and not self.searching:
            self.resume_timer.stop()
            self.logger.info("Automatic resume of the patents search cancelled.")
            self.status.setText("Automatic resume cancelled: what was read is kept, Search patents resumes it.")
            self._update_buttons()
            return
        self.status.setText("Stopping after the requests in flight…")
        self.stop_button.setEnabled(False)
        self.stop_requested.emit()

    def start(self, companies: Sequence[str], feeds: Sequence[CompanyFeed]) -> None:
        """Show that a search started.

        Args:
            companies (Sequence[str]): The companies searched, every one of the catalogue when empty.
            feeds (Sequence[CompanyFeed]): The sources searched.
        """
        shown = list(companies) or list(self.names)
        self.searching = True
        self.progress.start(shown, self.coverage)
        self.feed.clear_rows()
        names = ", ".join(self.names.get(company, company) for company in shown[:4])
        more = f" and {len(shown) - 4} others" if len(shown) > 4 else ""
        self.status.setText(f"Searching {', '.join(feed.value for feed in feeds)} for {names}{more}…")
        self._update_buttons()

    def add_batch(self, feed_value: str, items: List[Dict[str, JsonValue]], rows: int) -> None:
        """Show a batch of facts just written.

        Args:
            feed_value (str): The source of the batch.
            items (List[Dict[str, JsonValue]]): The facts, each naming its kind.
            rows (int): The rows written.
        """
        facts = self.reader.read(CompanyFeed(feed_value), items)
        self.progress.add(facts)
        self.feed.add(facts)
        self.status.setText(f"Searching {feed_value}: {self.feed.received:,} facts received, {rows} rows just written…")

    def finish(self, message: str, status: str) -> None:
        """Show the end of a search, and read again what is stored.

        Args:
            message (str): What the crawl says.
            status (str): The final status of the companies (done, stopped, refused or failed): a refused patents
                search is resumed later when asked to.
        """
        self.searching = False
        self.progress.finish(status)
        self.status.setText(message)
        if status == "refused" and self.resume_box.isChecked() and self.resume_search is not None:
            self.resume_timer.start(self.resume_minutes * 60_000)
            at = (datetime.now() + timedelta(minutes=self.resume_minutes)).strftime("%H:%M")
            self.logger.info("Patents search refused: resuming it at %s.", at)
            self.status.setText(f"{message} Resuming the patents search by itself at {at} (Stop cancels it).")
        self._update_buttons()
        self.refresh()

    def set_crawling(self, running: bool) -> None:
        """Disable Search while any crawl of the window runs.

        Args:
            running (bool): Whether a crawl runs.
        """
        self.crawling = running
        self._update_buttons()

    def pick(self, companies: Sequence[str]) -> None:
        """Pick some companies (from elsewhere in the window, or a test).

        Args:
            companies (Sequence[str]): Their keys.
        """
        self.picker.select(companies)
        self._update_buttons()

    def set_feeds(self, feeds: Sequence[CompanyFeed]) -> None:
        """Check some sources, and only them.

        Args:
            feeds (Sequence[CompanyFeed]): The sources.
        """
        wanted = set(feeds)
        for feed, box in self.sources.items():
            box.setChecked(feed in wanted)
        self._update_buttons()
