from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.charts.common.chart_exporter import ChartExporter
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection
from gui.charts.sections.section.sections_toolbar import SectionsToolbar
from gui.correspondence.coverage.coverage_matrix import CoverageMatrix
from gui.correspondence.details.concept_details import ConceptDetails
from gui.correspondence.details.concept_editor import ConceptEditor
from gui.correspondence.diagram.correspondence_diagram import CorrespondenceDiagram
from gui.correspondence.diagram.diagram_header import DiagramHeader
from gui.correspondence.diagram.diagram_legend import DiagramLegend
from gui.correspondence.diagram.diagram_scroll_area import DiagramScrollArea
from gui.correspondence.diagram.shapes.diagram_group import DiagramGroup
from gui.correspondence.filters.column_picker import ColumnPicker
from gui.correspondence.filters.correspondence_filters import CorrespondenceFilters
from gui.layout.flow_layout import FlowLayout
from gui.layout.folding_splitter import FoldingSplitter
from gui.layout.panes.section_stack import SectionStack
from gui.layout.panes.side_pane import SidePane
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from gui.widgets.dashboard.stat_card import StatCard
from llm.exception import LLMConfigurationFileError, LLMError
from llm.settings_loader import LLMSettingsLoader
from llm.tasks.correspondence.service_matcher import ServiceMatcher
from models.cloud.enums import CloudProvider
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.llm_settings import LLMSettings
from models.correspondence.enums import CardinalityClass, CoverageFilter, MemberRole, ViewMode
from models.correspondence.query.correspondence_query import CorrespondenceQuery
from models.correspondence.rows.concept_member import ConceptMember
from models.correspondence.rows.concept_row import ConceptRow
from models.correspondence.rows.correspondence_stats import CorrespondenceStats
from models.correspondence.rows.coverage_cell import CoverageCell
from models.trends.enums import SeriesGrouping
from storage.exception import StorageError
from storage.storage import Storage


class CorrespondenceView(QWidget):
    """The Correspondences tab: the equivalent services of the providers, side by side, as matched by the AI.

    Attributes:
        DEFAULT_COLUMNS (ClassVar[Tuple[CloudProvider, ...]]): The first provider columns.
        SEARCH_DELAY_MS (ClassVar[int]): How long the search text must stay unchanged before it applies.
        UNGROUPED (ClassVar[str]): The title of the concepts without a taxonomy domain.
        theme (Theme): The application theme.
        loop (StorageLoop): The storage thread of the GUI.
        taxonomy (TaxonomyCache): The taxonomy shared with the other views.
        store (ChartStateStore): The store of the section states.
        llm_settings (LLMSettings): The language model settings (`conf/llm.yaml`).
        generation (int): The number of reads requested, so that only the latest results are shown.
        pending (int): The services of the columns waiting for the AI, last read.
        concepts (List[ConceptRow]): The concepts shown.
        columns (ColumnPicker): The provider columns.
        filters (CorrespondenceFilters): The filters of the concepts.
        search_timer (QTimer): Delays the search while the text is typed.
        diagram (CorrespondenceDiagram): The concepts, one row each, filling the room left.
        header (DiagramHeader): The provider columns, kept above the rows while they scroll.
        diagram_area (DiagramScrollArea): Scrolls the rows, the diagram filling its visible area.
        pages (QStackedWidget): The diagram, or the coverage matrix.
        legend (DiagramLegend): What the colours and lines of the diagram mean.
        coverage (CoverageMatrix): The share of the services of each provider matched at each other one.
        details (ConceptDetails): The selected concept.
        editor (ConceptEditor): The dialogs of the changes made by hand.
        exporter (ChartExporter): Saves or copies the diagram.
        concepts_card, matched_card, pending_card, checked_card (StatCard): The figures of the columns.
        configured (bool): Whether a model matches the services (its API key is set).
        mode (ViewMode): What the rows stand for in the last read.
        auto_mode (bool): Whether the first figures still choose the mode (the taxonomy categories while the AI matched
            nothing).
        match_button (QPushButton): Matches the waiting services with the AI (enabled when a model is configured).
        cost_label (QLabel): What the language model calls spent, of the budget.
        status_label (QLabel): What happened last.
        sections (SectionsToolbar): Expands or collapses the sections (the controls fold to give the diagram their
            height).
        logger (Logger): The view logger.

    Notes:
        - A concept (e.g. "Managed Kubernetes") groups the equivalent services of the providers: the diagram shows
          one row per concept, one column per chosen provider, and joins the services of adjacent columns. The colour
          tells how many services of one side match one service of the other (1:1, 2:1, 3:1, n:1).
        - The AI matches the new services after each catalogue crawl, and on demand ("Match with AI"). The changes
          made in the details panel are kept by every later match.
    """

    DEFAULT_COLUMNS: ClassVar[Tuple[CloudProvider, ...]] = (
        CloudProvider.AWS,
        CloudProvider.AZURE,
        CloudProvider.GCP,
        CloudProvider.OVH,
        CloudProvider.ALIBABA,
    )
    SEARCH_DELAY_MS: ClassVar[int] = 300
    UNGROUPED: ClassVar[str] = "Other services"

    def __init__(
        self,
        theme: Theme,
        loop: StorageLoop,
        taxonomy: TaxonomyCache,
        store: Optional[ChartStateStore] = None,
        llm_settings: Optional[LLMSettings] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Build the view, reading nothing until `refresh`.

        Args:
            theme (Theme): The application theme.
            loop (StorageLoop): The storage thread of the GUI.
            taxonomy (TaxonomyCache): The taxonomy shared with the other views.
            store (Optional[ChartStateStore]): The store of the section states, remembered for the session by default.
            llm_settings (Optional[LLMSettings]): The language model settings, read from `conf/llm.yaml` by default.
            logger (Optional[Logger]): The view logger.
        """
        super().__init__()
        self.theme = theme
        self.loop = loop
        self.taxonomy = taxonomy
        self.logger = logger if logger else getLogger(__name__)
        self.store = store if store else ChartStateStore(logger=self.logger)
        if llm_settings is None:
            try:
                llm_settings = LLMSettingsLoader(self.logger).load()
            except LLMConfigurationFileError as e:
                self.logger.warning("The language model settings cannot be read, no model is offered: %s", e)
                llm_settings = LLMSettings()
        self.llm_settings = llm_settings
        self.generation = 0
        self.pending = 0
        self.mode = ViewMode.CONCEPTS
        self.auto_mode = True
        self.concepts: List[ConceptRow] = []
        self.columns = ColumnPicker(theme, list(CloudProvider), self.DEFAULT_COLUMNS)
        self.filters = CorrespondenceFilters(theme, taxonomy)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(self.SEARCH_DELAY_MS)
        self.diagram = CorrespondenceDiagram(theme, self.logger)
        self.header = DiagramHeader(theme, self.logger)
        self.diagram_area = DiagramScrollArea(self.diagram, self.header, self.logger)
        self.pages = QStackedWidget()
        self.legend = DiagramLegend(theme)
        self.coverage = CoverageMatrix(theme)
        self.details = ConceptDetails(theme)
        self.editor = ConceptEditor(theme)
        self.exporter = ChartExporter(self.logger)
        self.concepts_card = StatCard("Concepts")
        self.matched_card = StatCard("Matched services")
        self.pending_card = StatCard("Waiting for the AI")
        self.checked_card = StatCard("Last AI match")
        self.match_button = QPushButton("Match with AI")
        self.match_button.setToolTip("Match the services waiting in every category with the AI (language model)")
        self.configured = llm_settings.is_configured(LLMTask.SERVICE_CORRESPONDENCE)
        self.match_button.setEnabled(self.configured)
        if not self.configured:
            self.match_button.setToolTip(
                "No AI model is configured: set the API key named in src/conf/llm.yaml (ANTHROPIC_API_KEY), then"
                " restart the application to match the services with the AI"
            )
        self.cost_label = QLabel()
        self.cost_label.setObjectName("muted")
        self.cost_label.setVisible(self.configured)
        self.status_label = QLabel()
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.sections = SectionsToolbar(self.logger)
        self._build_layout()
        self._connect()
        self.match_button.clicked.connect(self.match)
        self.logger.debug("Correspondence view built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _export_button(self) -> QToolButton:
        """Build the export button of the diagram.

        Returns:
            QToolButton: The button, its menu saving or copying the picture and the CSV.
        """
        button = QToolButton()
        button.setObjectName("chartTool")
        button.setText("Export ▾")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for label, action in (
            ("Save the picture…", lambda: self.exporter.save_png(self.diagram, "correspondences")),
            ("Copy the picture", lambda: self.exporter.copy_image(self.diagram)),
            ("Save the CSV…", lambda: self.exporter.save_csv(self.diagram, "correspondences", self.diagram.csv())),
            ("Copy the CSV", lambda: self.exporter.copy_text(self.diagram.csv())),
        ):
            entry = menu.addAction(label)
            if entry is not None:
                entry.triggered.connect(action)
        button.setMenu(menu)
        return button

    def _view_switch(self) -> QWidget:
        """Build the switch between the diagram and the coverage matrix, and the export button.

        Returns:
            QWidget: The tools of the section.
        """
        tools = QWidget()
        layout = QHBoxLayout(tools)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(tools)
        for index, (label, tip) in enumerate(
            (
                ("Diagram", "The rows and the services of every column, joined by their correspondences"),
                ("Coverage matrix", "The share of the services of each provider with an equivalent at each other one"),
            )
        ):
            button = QToolButton()
            button.setObjectName("segment")
            button.setText(label)
            button.setToolTip(tip)
            button.setCheckable(True)
            button.setChecked(index == 0)
            group.addButton(button, index)
            layout.addWidget(button)
        group.idClicked.connect(self.pages.setCurrentIndex)
        layout.addSpacing(8)
        for label, tip, action in (
            ("Readable", "Give the provider columns a width where the names are readable", self.diagram.readable),
            (
                "Fit all",
                "Fit every provider column to the width: all at once, the names shortened",
                self.diagram.fit_all,
            ),
        ):
            width_button = QToolButton()
            width_button.setObjectName("chartTool")
            width_button.setText(label)
            width_button.setToolTip(tip)
            width_button.clicked.connect(action)
            layout.addWidget(width_button)
        layout.addSpacing(8)
        layout.addWidget(self._export_button())
        return tools

    def _build_layout(self) -> None:
        """Lay the columns, filters and figures out above the diagram, which takes every pixel left, details right."""
        heading = QLabel("Service correspondences")
        heading.setObjectName("title")
        caption = QLabel(
            "The equivalent services of the cloud providers, grouped into service concepts by the AI. "
            "Each row is a concept, each column a provider: the colour tells how many services of one side "
            "match one service of the next column."
        )
        caption.setObjectName("muted")
        caption.setWordWrap(True)
        header = QHBoxLayout()
        header.addWidget(heading)
        header.addSpacing(16)
        header.addWidget(caption, 1)
        header.addWidget(self.sections)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.columns)
        toolbar.addStretch(1)
        toolbar.addWidget(self.cost_label)
        toolbar.addWidget(self.match_button)
        cards = FlowLayout(gap=16, logger=self.logger)
        for card in (self.concepts_card, self.matched_card, self.pending_card, self.checked_card):
            cards.addWidget(card)
        figures = QWidget()
        figures.setLayout(cards)
        diagram_page = QWidget()
        diagram_layout = QVBoxLayout(diagram_page)
        diagram_layout.setContentsMargins(0, 0, 0, 0)
        diagram_layout.setSpacing(0)
        diagram_layout.addWidget(self.legend)
        diagram_layout.addWidget(self.header)
        diagram_layout.addWidget(self.diagram_area, 1)
        coverage_scroll = QScrollArea()
        coverage_scroll.setWidget(self.coverage)
        coverage_scroll.setWidgetResizable(False)
        coverage_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.pages.addWidget(diagram_page)
        self.pages.addWidget(coverage_scroll)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        controls_layout.addLayout(toolbar)
        controls_layout.addWidget(self.filters)
        controls_layout.addWidget(self.status_label)
        controls_layout.addWidget(figures)
        controls_section = self.sections.add(
            ChartSection(
                "correspondence/controls",
                "Columns, filters and figures",
                controls,
                self.store,
                logger=self.logger,
                detachable=False,
            )
        )
        section = self.sections.add(
            ChartSection("correspondence/diagram", "Equivalent services", self.pages, self.store, self._view_switch())
        )
        stack = SectionStack(scrollable=False, logger=self.logger)
        stack.add_section(controls_section, 0)
        stack.add_section(section, 1)
        main = QWidget()
        column = QVBoxLayout(main)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        column.addLayout(header)
        column.addWidget(stack, 1)
        column.addStretch(0)
        self.details_pane = SidePane("correspondence/details", "Concept details", self.details, self.store, self.logger)
        splitter = FoldingSplitter(Qt.Orientation.Horizontal, self.logger)
        splitter.add_pane(main, 1)
        splitter.add_pane(self.details_pane)
        splitter.setSizes([1100, 360])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        self.logger.debug("Correspondence view laid out.")

    def _groups(self, concepts: Sequence[ConceptRow], columns: Sequence[CloudProvider]) -> List[DiagramGroup]:
        """Group concepts by taxonomy domain, in the order of the taxonomy.

        Args:
            concepts (Sequence[ConceptRow]): The concepts.
            columns (Sequence[CloudProvider]): The provider columns (the concepts offered by most columns first).

        Returns:
            List[DiagramGroup]: One group per domain, the concepts without one last.
        """
        taxonomy = self.taxonomy.taxonomy
        labels = ChartLabels(self.theme, self.logger, taxonomy=taxonomy)
        order = {domain.slug: index for index, domain in enumerate(taxonomy.domains())}
        grouped: Dict[str, List[ConceptRow]] = {}
        for concept in concepts:
            slug = concept.node_slug or ""
            domain = slug if taxonomy.is_domain(slug) else taxonomy.domain_of(slug) or ""
            grouped.setdefault(domain, []).append(concept)
        groups: List[DiagramGroup] = []
        for domain in sorted(grouped, key=lambda slug: (slug == "", order.get(slug, len(order)), slug)):
            node = taxonomy.node(domain) if domain else None
            title = node.name_en if node is not None else self.UNGROUPED
            color = labels.series_color(SeriesGrouping.DOMAIN, domain).name() if domain else self.theme.TEXT_MUTED
            rows = sorted(grouped[domain], key=lambda concept: (-concept.covered(columns), concept.name.casefold()))
            groups.append(DiagramGroup(title, color, rows))
        return groups

    def _query(self) -> CorrespondenceQuery:
        """Build the query of the columns and the filters.

        Returns:
            CorrespondenceQuery: The query.
        """
        return self.filters.query(self.columns.columns())

    def _on_error(self, error: StorageError) -> None:
        """Report a read or a change which failed.

        Args:
            error (StorageError): The error.
        """
        if sip.isdeleted(self):
            return
        self.logger.warning("The correspondences cannot be read or changed: %s", error)
        self.status_label.setText(f"The correspondences cannot be read or changed: {error}")
        self.match_button.setEnabled(self.configured)

    def _on_rows(self, generation: int, query: CorrespondenceQuery, concepts: List[ConceptRow]) -> None:
        """Show the concepts of the latest read in the diagram.

        Args:
            generation (int): The read.
            query (CorrespondenceQuery): Its query.
            concepts (List[ConceptRow]): The concepts.
        """
        if sip.isdeleted(self):
            return
        if generation != self.generation:
            return
        self.concepts = concepts
        message = (
            "No concept matches the filters."
            if not self.pending
            else f"No concept yet: {self.pending:,} services wait for the AI (Match with AI)."
        )
        if query.mode is ViewMode.CATEGORIES:
            message = "No category matches the filters."
        title = "Taxonomy category" if query.mode is ViewMode.CATEGORIES else "Service concept"
        self.diagram.set_rows(self._groups(concepts, query.columns), query.columns, query.strength, message, title)
        self.logger.debug("%d concepts shown.", len(concepts))

    def _on_stats(self, generation: int, query: CorrespondenceQuery, stats: CorrespondenceStats) -> None:
        """Show the figures of the latest read (the first time, the taxonomy categories while the AI matched nothing).

        Args:
            generation (int): The read.
            query (CorrespondenceQuery): Its query.
            stats (CorrespondenceStats): The figures.
        """
        if sip.isdeleted(self):
            return
        if generation != self.generation:
            return
        if self.auto_mode:
            self.auto_mode = False
            if stats.stored == 0 and query.mode is ViewMode.CONCEPTS:
                self.logger.info("No AI concept stored yet: the taxonomy categories are shown.")
                self.status_label.setText("No AI concept yet: the rows are the taxonomy categories.")
                self.filters.set_mode(ViewMode.CATEGORIES)
                return
        self.pending = stats.pending
        categories = query.mode is ViewMode.CATEGORIES
        if not self.concepts and stats.pending and not categories:
            self.diagram.set_message(f"No concept yet: {stats.pending:,} services wait for the AI (Match with AI).")
        self.concepts_card.set_value(f"{stats.concepts:,}", "categories shown" if categories else "AI concepts shown")
        self.matched_card.set_value(
            f"{stats.coverage():.0f}%",
            f"{stats.matched:,} of {stats.services:,} services" + (" share a category" if categories else ""),
        )
        self.pending_card.set_value(f"{stats.pending:,}", "new or changed services")
        checked = stats.last_checked.astimezone().strftime("%d %b %H:%M") if stats.last_checked else "never"
        self.checked_card.set_value(checked, "by the AI")

    def _on_classes(self, generation: int, counts: Dict[CardinalityClass, int]) -> None:
        """Show the number of concepts of each class on the filter buttons.

        Args:
            generation (int): The read.
            counts (Dict[CardinalityClass, int]): The concepts of each class.
        """
        if sip.isdeleted(self):
            return
        if generation == self.generation:
            self.filters.set_class_counts(counts)

    def _on_coverage(self, providers: List[CloudProvider], cells: List[CoverageCell]) -> None:
        """Show the coverage matrix.

        Args:
            providers (List[CloudProvider]): The providers of the matrix.
            cells (List[CoverageCell]): The coverage of each pair.
        """
        if sip.isdeleted(self):
            return
        self.coverage.set_cells(providers, cells)

    def _on_sizes(self, sizes: Dict[CloudProvider, int]) -> None:
        """Know the catalogue sizes, for the column presets.

        Args:
            sizes (Dict[CloudProvider, int]): The listed services of each provider.
        """
        if sip.isdeleted(self):
            return
        self.columns.set_sizes(sizes)

    def _on_category_counts(self, counts: Dict[str, int]) -> None:
        """Show the number of services of each category in the category picker.

        Args:
            counts (Dict[str, int]): The services of each taxonomy node.
        """
        if sip.isdeleted(self):
            return
        self.filters.category_picker.set_counts(counts)

    def _on_spent(self, spent: Decimal) -> None:
        """Show what the language model calls spent.

        Args:
            spent (Decimal): The cost of the recorded calls.
        """
        if sip.isdeleted(self):
            return
        budget = self.llm_settings.llm_budget
        self.cost_label.setText(f"AI: {spent:.2f} of {budget.ceiling:.2f} {budget.currency}")

    def _load(self) -> None:
        """Read the concepts, the figures and the coverage of the columns."""
        self.generation += 1
        generation, query = self.generation, self._query()
        self.mode = query.mode
        columns = list(query.columns)
        self.logger.debug("Reading the correspondences of %d columns.", len(columns))
        self.loop.submit(
            lambda storage: storage.correspondences.stats(query),
            partial(self._on_stats, generation, query),
            self._on_error,
        )
        self.loop.submit(
            lambda storage: storage.correspondences.rows(query),
            partial(self._on_rows, generation, query),
            self._on_error,
        )
        self.loop.submit(
            lambda storage: storage.correspondences.classes(query),
            partial(self._on_classes, generation),
            self._on_error,
        )
        self.loop.submit(
            lambda storage: storage.correspondences.coverage(columns, query.mode),
            partial(self._on_coverage, columns),
            self._on_error,
        )
        self.loop.submit(
            lambda storage: storage.catalogues.category_counts(query.item_query()),
            self._on_category_counts,
            self._on_error,
        )
        if self.configured:
            currency = self.llm_settings.llm_budget.currency
            self.loop.submit(lambda storage: storage.llm_usage.spent(currency), self._on_spent, self._on_error)

    def _on_changed(self) -> None:
        """Read again once the columns or the filters change."""
        self.search_timer.stop()
        self._load()

    def _on_pair_selected(self, source: str, target: str) -> None:
        """Compare two providers picked in the coverage matrix: their concepts missing at one of them.

        Args:
            source (str): The provider of the row.
            target (str): The provider of the column.
        """
        self.logger.info("Comparing the services of %s and %s.", source, target)
        self.filters.set_coverage(CoverageFilter.GAPS)
        self.columns.set_columns([CloudProvider(source), CloudProvider(target)])

    def _on_concept(self, concept: Optional[ConceptRow]) -> None:
        """Show a concept in the details panel.

        Args:
            concept (Optional[ConceptRow]): The concept, `None` when it no longer exists.
        """
        if sip.isdeleted(self):
            return
        path = self.taxonomy.path(concept.node_slug) if concept is not None and concept.node_slug else ""
        self.details.show_concept(concept, path)
        self.diagram.select(concept.id if concept is not None else None)

    def _show(self, concept_id: int) -> None:
        """Read a concept for the details panel.

        Args:
            concept_id (int): The concept.
        """
        self.loop.submit(lambda storage: storage.correspondences.concept(concept_id), self._on_concept, self._on_error)

    def _on_selected(self, row_id: int) -> None:
        """Show the clicked row: a stored concept (read again), or a taxonomy category (read-only).

        Args:
            row_id (int): The identifier of the row.
        """
        if self.mode is ViewMode.CONCEPTS:
            self._show(row_id)
            return
        row = next((concept for concept in self.concepts if concept.id == row_id), None)
        path = self.taxonomy.path(row.node_slug) if row is not None and row.node_slug else ""
        self.details.show_concept(row, path, editable=False)

    def _on_edited(self, concept_id: Optional[int], message: str, _: Optional[int] = None) -> None:
        """Read everything again after a change made by hand.

        Args:
            concept_id (Optional[int]): The concept to show again, `None` to clear the details.
            message (str): What was changed.
            _ (Optional[int]): The result of the change (unused).
        """
        if sip.isdeleted(self):
            return
        self.status_label.setText(message)
        self.logger.info("Correspondence changed by hand: %s", message)
        if concept_id is None:
            self._on_concept(None)
        else:
            self._show(concept_id)
        self._load()

    def _on_rename(self, concept_id: int) -> None:
        """Rename a concept by hand.

        Args:
            concept_id (int): The concept.
        """
        concept = self.details.concept
        if concept is None:
            return
        answer = self.editor.ask_name(self, "Rename the concept", concept.name, concept.description)
        if answer is None:
            return
        name, description = answer
        self.loop.submit(
            lambda storage: storage.correspondences.rename(concept_id, name, description),
            partial(self._on_edited, concept_id, f"Concept renamed {name!r}."),
            self._on_error,
        )

    def _on_merge(self, concept_id: int) -> None:
        """Merge a concept into another one, by hand.

        Args:
            concept_id (int): The concept merged.
        """
        target = self.editor.pick_concept(self, self.concepts, concept_id)
        if target is None:
            return
        self.loop.submit(
            lambda storage: storage.correspondences.merge(target, concept_id),
            partial(self._on_edited, target, "Concepts merged."),
            self._on_error,
        )

    def _on_services(self, concept_id: int, services: List[ConceptMember]) -> None:
        """Ask for a service to file under a concept, among those of its category.

        Args:
            concept_id (int): The concept.
            services (List[ConceptMember]): The services of its category.
        """
        if sip.isdeleted(self):
            return
        picked = self.editor.pick_service(self, services)
        if picked is None:
            return
        product_id, role = picked
        self.loop.submit(
            lambda storage: storage.correspondences.link(concept_id, product_id, role),
            partial(self._on_edited, concept_id, "Service added to the concept."),
            self._on_error,
        )

    def _on_add(self, concept_id: int) -> None:
        """Read the services of the category of a concept, to file one under it.

        Args:
            concept_id (int): The concept.
        """
        concept = self.details.concept
        slug = concept.node_slug if concept is not None else None
        if not slug:
            self.status_label.setText("The concept has no category: its services cannot be listed.")
            return
        self.loop.submit(
            lambda storage: storage.correspondences.services(slug),
            partial(self._on_services, concept_id),
            self._on_error,
        )

    def _on_delete(self, concept_id: int) -> None:
        """Delete a concept, once confirmed.

        Args:
            concept_id (int): The concept.
        """
        if not self.editor.confirm(self, "Delete the concept? Its services are no longer matched through it."):
            return
        self.loop.submit(
            lambda storage: storage.correspondences.delete(concept_id),
            partial(self._on_edited, None, "Concept deleted."),
            self._on_error,
        )

    def _on_rematch(self, slug: str) -> None:
        """Forget the matches of a category: the next AI run matches it again.

        Args:
            slug (str): The category.
        """
        name = self.taxonomy.name(slug)
        self.loop.submit(
            lambda storage: storage.correspondences.invalidate(slug),
            partial(self._on_edited, None, f"{name}: matched again by the next AI run."),
            self._on_error,
        )

    def _on_unlink(self, concept_id: int, product_id: int) -> None:
        """Remove a service from a concept, by hand (never filed there again).

        Args:
            concept_id (int): The concept.
            product_id (int): The service.
        """
        self.loop.submit(
            lambda storage: storage.correspondences.unlink(concept_id, product_id),
            partial(self._on_edited, concept_id, "Service removed from the concept."),
            self._on_error,
        )

    def _on_role(self, concept_id: int, product_id: int, role: str) -> None:
        """Set whether a service of a concept is equivalent or partial, by hand.

        Args:
            concept_id (int): The concept.
            product_id (int): The service.
            role (str): The `MemberRole` value.
        """
        member_role = MemberRole(role)
        self.loop.submit(
            lambda storage: storage.correspondences.link(concept_id, product_id, member_role),
            partial(self._on_edited, concept_id, f"Service marked {member_role.value}."),
            self._on_error,
        )

    async def _match_job(self, storage: Storage) -> str:
        """Match the waiting services with the AI (storage thread).

        Args:
            storage (Storage): The open storage.

        Returns:
            str: What happened, for the status line.
        """
        try:
            matched = await ServiceMatcher(storage, self.llm_settings).run()
        except LLMError as e:
            self.logger.warning("The service matching stopped: %s", e)
            return f"The AI matching stopped: {e}"
        return f"{matched:,} services matched with their equivalents by the AI."

    def _on_matched(self, message: str) -> None:
        """Report the end of an AI matching, and read everything again.

        Args:
            message (str): What happened.
        """
        if sip.isdeleted(self):
            return
        self.match_button.setEnabled(self.configured)
        self.status_label.setText(message)
        self.logger.info("Service matching over: %s", message)
        self._load()

    def _connect(self) -> None:
        """Read again when the columns or the filters change, and bind the selections and the actions."""
        self.columns.changed.connect(self._on_changed)
        self.filters.changed.connect(self._on_changed)
        self.filters.searched.connect(self.search_timer.start)
        self.search_timer.timeout.connect(self._on_changed)
        self.coverage.pair_selected.connect(self._on_pair_selected)
        self.diagram.concept_selected.connect(self._on_selected)
        self.details.rename_requested.connect(self._on_rename)
        self.details.merge_requested.connect(self._on_merge)
        self.details.add_requested.connect(self._on_add)
        self.details.delete_requested.connect(self._on_delete)
        self.details.rematch_requested.connect(self._on_rematch)
        self.details.unlink_requested.connect(self._on_unlink)
        self.details.role_requested.connect(self._on_role)
        self.taxonomy.changed.connect(self._load)

    ############################
    # Publicly Exposed Methods #
    ############################

    def refresh(self) -> None:
        """Read everything again (a catalogue was crawled, or a match made)."""
        self.logger.debug("Refreshing the correspondences.")
        self.loop.submit(lambda storage: storage.correspondences.sizes(), self._on_sizes, self._on_error)
        self._load()

    def match(self) -> None:
        """Match the services waiting in every category with the AI."""
        if not self.llm_settings.is_configured(LLMTask.SERVICE_CORRESPONDENCE):
            self.status_label.setText("No AI model is configured (set the API key named in conf/llm.yaml).")
            return
        self.logger.info("Service matching requested.")
        self.match_button.setEnabled(False)
        self.status_label.setText("Matching the waiting services with the AI…")
        self.loop.submit(self._match_job, self._on_matched, self._on_error)

    def select(self, concept_id: int) -> None:
        """Show a concept in the details panel.

        Args:
            concept_id (int): The concept.
        """
        self._show(concept_id)
