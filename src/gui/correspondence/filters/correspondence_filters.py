from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QPushButton, QSpinBox, QToolButton, QWidget

# First Party Imports.
from gui.layout.flow_layout import FlowLayout
from gui.selection.taxonomy.category_picker import CategoryPicker
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.cloud.enums import CloudProvider, SoftwareAudience
from models.correspondence.enums import CardinalityClass, ConceptSource, CoverageFilter, MatchStrength, ViewMode
from models.correspondence.query.correspondence_query import CorrespondenceQuery


class CorrespondenceFilters(QWidget):
    """The filters of the Correspondences tab: categories, text, correspondence classes, coverage, strength, source.

    Attributes:
        MODE_LABELS (ClassVar[Dict[ViewMode, str]]): The label of each view mode.
        COVERAGE_LABELS (ClassVar[Dict[CoverageFilter, str]]): The label of each coverage filter.
        STRENGTH_LABELS (ClassVar[Dict[MatchStrength, str]]): The label of each strength filter.
        SOURCE_LABELS (ClassVar[Dict[str, List[ConceptSource]]]): The label of each source filter, and its sources.
        changed (pyqtSignal): Emitted when a filter changes (the search box when it stops changing: see the view).
        searched (pyqtSignal): Emitted at each keystroke of the search box.
        theme (Theme): The application theme.
        mode_box (QComboBox): Whether the rows are the concepts matched by the AI, or the taxonomy categories.
        category_picker (CategoryPicker): Only the services of some taxonomy categories or domains.
        search_box (QLineEdit): Text in a concept or service name.
        class_buttons (Dict[CardinalityClass, QToolButton]): Only the concepts of the checked classes (any when none).
        coverage_box (QComboBox): Which concepts, by the columns holding their services.
        strength_box (QComboBox): Whether the partial services are shown.
        confidence_box (QSpinBox): The smallest confidence of the services filed by the language model.
        source_box (QComboBox): Only the services filed by the language model, or by hand.
        audience_box (QComboBox): Only the services meant for an audience.
        deleted_box (QCheckBox): Shows the services deleted from their catalogue too.
        reset_button (QPushButton): Clears every filter.
        logger (Logger): The filters logger.
    """

    MODE_LABELS: ClassVar[Dict[ViewMode, str]] = {
        ViewMode.CONCEPTS: "Rows: AI concepts",
        ViewMode.CATEGORIES: "Rows: taxonomy categories",
    }
    COVERAGE_LABELS: ClassVar[Dict[CoverageFilter, str]] = {
        CoverageFilter.ALL: "Every concept",
        CoverageFilter.COMPLETE: "Offered by every column",
        CoverageFilter.GAPS: "Missing in a column",
        CoverageFilter.UNIQUE: "Unique to one column",
    }
    STRENGTH_LABELS: ClassVar[Dict[MatchStrength, str]] = {
        MatchStrength.ANY: "Equivalent and partial",
        MatchStrength.EQUIVALENT: "Equivalent only",
    }
    SOURCE_LABELS: ClassVar[Dict[str, List[ConceptSource]]] = {
        "AI and by hand": [],
        "Matched by the AI": [ConceptSource.LLM],
        "Set by hand": [ConceptSource.USER],
    }

    changed = pyqtSignal()
    searched = pyqtSignal()

    def __init__(self, theme: Theme, taxonomy: TaxonomyCache, logger: Optional[Logger] = None) -> None:
        """Build the filters, every one cleared.

        Args:
            theme (Theme): The application theme.
            taxonomy (TaxonomyCache): The taxonomy offered by the category picker.
            logger (Optional[Logger]): The filters logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.category_picker = CategoryPicker(taxonomy, self.logger)
        self.mode_box = CompactCombo(28, self.logger)
        for mode, label in self.MODE_LABELS.items():
            self.mode_box.addItem(label, mode.value)
        self.mode_box.setToolTip(
            "AI concepts: the equivalent services matched by the AI. Taxonomy categories: the services of each provider"
            " filed under the same category, available without the AI."
        )
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search a concept or a service…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(220)
        self.class_buttons: Dict[CardinalityClass, QToolButton] = {}
        for kind in (
            CardinalityClass.ONE_TO_ONE,
            CardinalityClass.TWO_TO_ONE,
            CardinalityClass.THREE_TO_ONE,
            CardinalityClass.MANY_TO_ONE,
        ):
            button = QToolButton()
            button.setCheckable(True)
            button.setText(kind.value)
            button.setToolTip(f"Only the concepts of {theme.CORRESPONDENCE_LABELS[kind]} between the columns")
            fill, ink = theme.CORRESPONDENCE_FILLS[kind], theme.CORRESPONDENCE_INKS[kind]
            button.setStyleSheet(
                f"QToolButton {{ border: 1px solid {theme.CORRESPONDENCE_EDGES[kind]}; border-radius: 9px;"
                f" padding: 2px 10px; }} QToolButton:checked {{ background: {fill}; color: {ink}; font-weight: 600; }}"
            )
            self.class_buttons[kind] = button
        self.coverage_box = self._combo([(label, kind.value) for kind, label in self.COVERAGE_LABELS.items()])
        self.coverage_box.setToolTip("Which concepts are shown, by the columns offering one of their services")
        self.strength_box = self._combo([(label, kind.value) for kind, label in self.STRENGTH_LABELS.items()])
        self.confidence_box = QSpinBox()
        self.confidence_box.setRange(0, 100)
        self.confidence_box.setSingleStep(10)
        self.confidence_box.setPrefix("AI confidence ≥ ")
        self.confidence_box.setSuffix("%")
        self.confidence_box.setToolTip(
            "Hide the services the AI filed with a lower confidence (those set by hand stay)"
        )
        self.source_box = self._combo([(label, label) for label in self.SOURCE_LABELS])
        self.audience_box = self._combo(
            [("All audiences", "")]
            + [(theme.audience_label(audience), audience.value) for audience in SoftwareAudience]
        )
        self.deleted_box = QCheckBox("Show deleted")
        self.deleted_box.setToolTip("Show the services which disappeared from their catalogue, struck through")
        self.reset_button = QPushButton("Reset")
        layout = FlowLayout(gap=8, logger=self.logger)
        layout.addWidget(self.mode_box)
        layout.addWidget(self.search_box)
        layout.addWidget(self.category_picker)
        for button in self.class_buttons.values():
            layout.addWidget(button)
        for widget in (
            self.coverage_box,
            self.strength_box,
            self.confidence_box,
            self.source_box,
            self.audience_box,
            self.deleted_box,
            self.reset_button,
        ):
            layout.addWidget(widget)
        self.setLayout(layout)
        self.search_box.textChanged.connect(self.searched.emit)
        self.category_picker.changed.connect(self.changed.emit)
        for button in self.class_buttons.values():
            button.toggled.connect(self.changed.emit)
        for box in (self.mode_box, self.coverage_box, self.strength_box, self.source_box, self.audience_box):
            box.currentIndexChanged.connect(self.changed.emit)
        self.confidence_box.valueChanged.connect(self.changed.emit)
        self.deleted_box.toggled.connect(self.changed.emit)
        self.reset_button.clicked.connect(self.reset)
        self.logger.debug("Correspondence filters built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _combo(self, entries: List[Tuple[str, str]]) -> QComboBox:
        """Build a combo box.

        Args:
            entries (List[Tuple[str, str]]): The label and value of each entry, the first one selected.

        Returns:
            QComboBox: The combo box.
        """
        box = CompactCombo(logger=self.logger)
        for label, value in entries:
            box.addItem(label, value)
        self.logger.debug("Filter combo box built with %d entries.", len(entries))
        return box

    ############################
    # Publicly Exposed Methods #
    ############################

    def query(self, columns: Sequence[CloudProvider]) -> CorrespondenceQuery:
        """Build the query of the filters.

        Args:
            columns (Sequence[CloudProvider]): The provider columns.

        Returns:
            CorrespondenceQuery: The columns and the filters.
        """
        audience = self.audience_box.currentData() or ""
        self.logger.debug(
            "Correspondence query of %d columns, mode %s, search %r.",
            len(columns),
            self.mode_box.currentData(),
            self.search_box.text(),
        )
        return CorrespondenceQuery(
            columns=list(columns),
            mode=ViewMode(self.mode_box.currentData()),
            service_categories=self.category_picker.picked(),
            search=self.search_box.text(),
            cardinalities=[kind for kind, button in self.class_buttons.items() if button.isChecked()],
            coverage=CoverageFilter(self.coverage_box.currentData()),
            strength=MatchStrength(self.strength_box.currentData()),
            min_confidence=self.confidence_box.value(),
            sources=list(self.SOURCE_LABELS[self.source_box.currentText()]),
            audiences=[SoftwareAudience(audience)] if audience else [],
            include_deleted=self.deleted_box.isChecked(),
        )

    def set_class_counts(self, counts: Dict[CardinalityClass, int]) -> None:
        """Show the number of concepts of each class on its button.

        Args:
            counts (Dict[CardinalityClass, int]): The concepts of each class over the columns.
        """
        for kind, button in self.class_buttons.items():
            button.setText(f"{kind.value}  {counts.get(kind, 0):,}")
        self.logger.debug("Class counts shown: %s.", ", ".join(f"{kind.value} {count}" for kind, count in counts.items()))

    def set_mode(self, mode: ViewMode) -> None:
        """Choose what the rows stand for (e.g. the taxonomy categories while the AI matched nothing yet).

        Args:
            mode (ViewMode): The mode.
        """
        index = self.mode_box.findData(mode.value)
        if index < 0:
            self.logger.warning("The mode %s is not offered: the first mode is chosen.", mode.value)
        self.logger.debug("Correspondence mode set to %s.", mode.value)
        self.mode_box.setCurrentIndex(max(index, 0))

    def set_coverage(self, coverage: CoverageFilter) -> None:
        """Choose the coverage filter (e.g. the gaps of two providers picked in the coverage matrix).

        Args:
            coverage (CoverageFilter): The filter.
        """
        index = self.coverage_box.findData(coverage.value)
        if index < 0:
            self.logger.warning("The coverage filter %s is not offered: the first one is chosen.", coverage.value)
        self.logger.debug("Coverage filter set to %s.", coverage.value)
        self.coverage_box.setCurrentIndex(max(index, 0))

    def reset(self) -> None:
        """Clear every filter, then tell once."""
        self.logger.info("Correspondence filters reset.")
        self.blockSignals(True)
        self.search_box.clear()
        self.category_picker.reset()
        for button in self.class_buttons.values():
            button.setChecked(False)
        for box in (self.coverage_box, self.strength_box, self.source_box, self.audience_box):
            box.setCurrentIndex(0)
        self.confidence_box.setValue(0)
        self.deleted_box.setChecked(False)
        self.blockSignals(False)
        self.changed.emit()
