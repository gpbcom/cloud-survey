from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, datetime, time, timedelta
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.layout.flow_layout import FlowLayout
from gui.selection.taxonomy.source_label_picker import SourceLabelPicker
from gui.theme import Theme
from gui.widgets.compact_combo import CompactCombo
from models.cloud.enums import DateCaveat, DateSource, SoftwareAudience
from models.storage.enums import ItemFilter
from models.storage.filters.date_filter import DateFilter
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from models.taxonomy.labels.label_count import LabelCount

SourceChoice = Tuple[Tuple[DateSource, ...], Optional[bool]]
PrecisionChoice = Tuple[Optional[bool], Tuple[DateCaveat, ...]]


class AdvancedSoftwareFilters(QFrame):
    """The filters of the marketplace software on every field not filtered by the main filter row.

    Attributes:
        NO_DATE (ClassVar[QDate]): The date of the date boxes meaning "any date".
        PICKER_ANY (ClassVar[str]): The label of the "any value" entry of the pickers.
        changed (pyqtSignal): Emitted when a filter changes (the text boxes at each keystroke: the view delays them).
        theme (Theme): The application theme.
        software_fields (bool): Whether the software fields (publisher) are filtered: `False` for the catalogue
            products.
        name_box (QLineEdit): Text contained in the software name.
        description_box (QLineEdit): Text contained in the software description.
        url_box (QLineEdit): Text contained in the software page address.
        publisher_box (QComboBox): The publisher, editable with completion among the most frequent ones.
        source_label_box (SourceLabelPicker): The category of the provider, translated (a source label and its
            aliases), for the products and the software.
        audience_box (QComboBox): Who the items are meant for: developer tool only, end-user software only, or both.
        added_after_box, added_before_box (QDateEdit): The range of the added date (`NO_DATE` for no bound).
        added_source_box (QComboBox): Where the added date comes from, or whether it is unknown.
        updated_after_box, updated_before_box (QDateEdit): The range of the updated date.
        updated_source_box (QComboBox): Where the updated date comes from, or whether it is unknown.
        deleted_after_box, deleted_before_box (QDateEdit): The range of the deletion date (a bound shows the deleted
            software).
        precision_box (QComboBox): Whether the dates are approximate, and why.
        reset_button (QPushButton): Clears every filter of the panel.
        logger (Logger): The panel logger.

    Notes:
        The software can be filtered on:
        - their name, description and page address (texts they contain),
        - their publisher (picker counted by the server),
        - the category their provider gives them, translated (a source label and its aliases),
        - who they are meant for (developer tool only, end-user software only, or both),
        - when they were added, updated and deleted (date ranges), where these dates come from, and how precise
          they are.
    """

    NO_DATE: ClassVar[QDate] = QDate(1990, 1, 1)
    PICKER_ANY: ClassVar[str] = "Any"

    changed = pyqtSignal()

    def __init__(self, theme: Theme, logger: Optional[Logger] = None, software_fields: bool = True) -> None:   # noqa: E501
        """Build the panel, every filter cleared.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The panel logger.
            software_fields (bool): Whether the software fields are filtered (`False` for the catalogue products).
        """
        super().__init__()
        self.theme = theme
        self.software_fields = software_fields
        self.logger = logger if logger else getLogger(__name__)
        self.setObjectName("card")
        self.name_box = self._text_box("Name contains…")
        self.description_box = self._text_box("Description contains…")
        self.url_box = self._text_box("Page address contains…")
        self.publisher_box = CompactCombo(14, self.logger)
        self.publisher_box.setEditable(True)
        self.publisher_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.publisher_box.setToolTip("The publisher: type a name, or pick one of the most frequent ones")
        self.source_label_box = SourceLabelPicker(self.logger)
        self.audience_box = self._audience_box()
        self.added_after_box, self.added_before_box = self._date_box(), self._date_box()   # noqa: E501
        self.updated_after_box, self.updated_before_box = self._date_box(), self._date_box()   # noqa: E501
        self.deleted_after_box, self.deleted_before_box = self._date_box(), self._date_box()   # noqa: E501
        self.added_source_box, self.updated_source_box = self._source_box(), self._source_box()   # noqa: E501
        self.precision_box = self._precision_box()
        self.reset_button = QPushButton("Reset")
        self.reset_button.setToolTip("Clear every filter of this panel")
        self._build_layout()
        self.set_pickers(SoftwareFacets())
        for box in (
            self.publisher_box,
            self.source_label_box,
            self.audience_box,
        ):
            box.currentIndexChanged.connect(self.changed.emit)
        for box in (self.added_source_box, self.updated_source_box, self.precision_box):
            box.currentIndexChanged.connect(self.changed.emit)
        publisher_edit = self.publisher_box.lineEdit()
        if publisher_edit is not None:
            publisher_edit.textEdited.connect(self.changed.emit)
        self.reset_button.clicked.connect(self.reset)
        self.logger.debug("Advanced software filters built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _text_box(self, placeholder: str) -> QLineEdit:
        """Build a text filter.

        Args:
            placeholder (str): The hint shown while it is empty.

        Returns:
            QLineEdit: The text box, emitting `changed` at each change.
        """
        box = QLineEdit()
        box.setPlaceholderText(placeholder)
        box.setClearButtonEnabled(True)
        box.textChanged.connect(self.changed.emit)
        self.logger.debug("Text filter %r built.", placeholder)
        return box

    def _date_box(self) -> QDateEdit:
        """Build a date bound, "Any" until a date is chosen.

        Returns:
            QDateEdit: The date box, emitting `changed` when its date changes.
        """
        box = QDateEdit()
        box.setCalendarPopup(True)
        box.setDisplayFormat("yyyy-MM-dd")
        box.setMinimumDate(self.NO_DATE)
        box.setSpecialValueText(self.PICKER_ANY)
        box.setDate(self.NO_DATE)
        box.dateChanged.connect(self.changed.emit)
        self.logger.debug("Date filter built.")
        return box

    def _source_box(self) -> QComboBox:
        """Build the filter of the source of a date.

        Returns:
            QComboBox: The choices, each with its sources
                and whether the date must be known.
        """
        box = CompactCombo(12, self.logger)
        choices: List[Tuple[str, SourceChoice]] = [
            ("Any source", ((), None)),
            ("Published by the website", ((DateSource.WEBSITE,), None)),
            ("Seen by a crawl", ((DateSource.CRAWL,), None)),
            ("Known", ((), True)),
            ("Unknown", ((), False)),
        ]
        for label, choice in choices:
            box.addItem(label, choice)
        self.logger.debug("Date source filter built: %d choices.", len(choices))
        return box

    def _precision_box(self) -> QComboBox:
        """Build the filter of the precision of the dates.

        Returns:
            QComboBox: The choices, each with whether a
                date must be approximate and the accepted caveats.
        """
        box = CompactCombo(12, self.logger)
        box.setToolTip("Whether the added or updated date is approximate, and why")
        choices: List[Tuple[str, PrecisionChoice]] = [
            ("Any precision", (None, ())),
            ("Approximate dates", (True, ())),
            ("Exact dates", (False, ())),
        ]
        choices += [(f"⚠ {self.theme.CAVEAT_LABELS[caveat]}", (None, (caveat,))) for caveat in DateCaveat]
        for label, choice in choices:
            box.addItem(label, choice)
        self.logger.debug("Date precision filter built: %d choices.", len(choices))   # noqa: E501
        return box

    def _audience_box(self) -> QComboBox:
        """Build the filter of who the items are meant for.

        Returns:
            QComboBox: The choices, each with its audiences
                (none for any audience).
        """
        box = CompactCombo(14, self.logger)
        box.setToolTip("Who the items are meant for: developer tools, end-user software, or both at once")
        box.addItem(self.PICKER_ANY, [])
        for audience in SoftwareAudience:
            box.addItem(self.theme.audience_label(audience), [audience])
        self.logger.debug("Audience filter built: %d choices.", box.count())
        return box

    def _group(self, *widgets: QWidget) -> QWidget:
        """Keep a label and its filters together on one line of the panel.

        Args:
            *widgets (QWidget): The label and the filters, left to right.

        Returns:
            QWidget: The group, which the panel lines wrap as a whole.
        """
        group = QWidget()
        row = QHBoxLayout(group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for widget in widgets:
            row.addWidget(widget)
        return group

    def _build_layout(self) -> None:
        """Lay the filters out in lines which wrap when the panel narrows: the texts, the pickers, then the dates.

        Notes:
            Each label stays with its filters (`_group`):
            the panel is no wider than its widest group, so that the
            window holding it can be maximized on any screen.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        texts = FlowLayout(gap=8, logger=self.logger)
        for box in (self.name_box, self.description_box, self.url_box):
            box.setMinimumWidth(160)
            texts.addWidget(box)
        pickers = FlowLayout(gap=12, logger=self.logger)
        if self.software_fields:
            pickers.addWidget(self._group(QLabel("Publisher"), self.publisher_box))   # noqa: E501
        else:
            self.publisher_box.setParent(self)
            self.publisher_box.setVisible(False)
        pickers.addWidget(self._group(QLabel("Source label"), self.source_label_box))   # noqa: E501
        pickers.addWidget(self._group(QLabel("Audience"), self.audience_box)) 
        dates = FlowLayout(gap=12, logger=self.logger)
        for label, after, before, extra in (
            ("Added from", self.added_after_box, self.added_before_box, self.added_source_box),   # noqa: E501
            ("Updated from", self.updated_after_box, self.updated_before_box, self.updated_source_box),
            ("Deleted from", self.deleted_after_box, self.deleted_before_box, self.precision_box),   # noqa: E501
        ):
            dates.addWidget(self._group(QLabel(label), after, QLabel("to"), before, extra))   # noqa: E501
        dates.addWidget(self.reset_button)
        for line in (texts, pickers, dates):
            layout.addLayout(line)
        self.logger.debug("Advanced software filters laid out.")

    def _fill_picker(self, box: QComboBox, entries: List[Tuple[str, List[str]]]) -> None:
        """Fill a picker, keeping its selection.

        Args:
            box (QComboBox): The picker.
            entries (List[Tuple[str, List[str]]]): The label of each entry,
                and the value it filters on.
        """
        selected = box.currentText()
        box.blockSignals(True)
        box.clear()
        box.addItem(self.PICKER_ANY, None)
        for label, value in entries:
            box.addItem(label, value)
        index = box.findText(selected)
        if index >= 0:
            box.setCurrentIndex(index)
        elif box.isEditable():
            box.setEditText(selected if selected != self.PICKER_ANY else "")
        box.blockSignals(False)
        self.logger.debug("Picker filled with %d entries.", len(entries))

    def _bound(self, box: QDateEdit, end_of_day: bool) -> Optional[datetime]:
        """Read a date bound.

        Args:
            box (QDateEdit): The date box.
            end_of_day (bool): Whether the bound is the
                end of the chosen day (the end of a range).

        Returns:
            Optional[datetime]: The bound in UTC (the chosen day in the local timezone),
                `None` for "Any".
        """
        chosen = box.date()
        if chosen == self.NO_DATE:
            return None
        day = datetime.combine(chosen.toPyDate(), time.min).astimezone()
        bound = day + timedelta(days=1) if end_of_day else day
        self.logger.debug("Date bound %s read: %s.", chosen.toString("yyyy-MM-dd"), bound)
        return bound.astimezone(UTC)

    def _date_filter(self, after: QDateEdit, before: QDateEdit, source: Optional[QComboBox]) -> DateFilter:   # noqa: E501
        """Read the filter of a date.

        Args:
            after (QDateEdit): The start of the range.
            before (QDateEdit): The end of the range.
            source (Optional[QComboBox]): The source filter, `None` for the deletion date.

        Returns:
            DateFilter: The filter, the range swapped when it is reversed.
        """
        start, end = self._bound(after, False), self._bound(before, True)
        if start is not None and end is not None and end <= start:
            self.logger.warning("Reversed date range %s - %s: its bounds are swapped.", start, end)
            start, end = end - timedelta(days=1), start + timedelta(days=1)
        sources: Tuple[DateSource, ...] = ()
        known: Optional[bool] = None
        if source is not None:
            sources, known = source.currentData()
        self.logger.debug("Date filter: %s - %s, sources %s, known %s.", start, end, sources, known)
        return DateFilter(after=start, before=end, sources=list(sources), known=known)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_pickers(self, facets: SoftwareFacets) -> None:
        """Fill the publisher picker with the most frequent publishers.

        Args:
            facets (SoftwareFacets): The counts of the listed
                software (see `MarketplaceRepository.facets`).
        """
        publishers = sorted(facets.by_publisher.items(), key=lambda entry: entry[0].casefold())   # noqa: E501
        self._fill_picker(self.publisher_box, [(publisher, [publisher]) for publisher, _ in publishers])
        completer = QCompleter([publisher for publisher, _ in publishers], self.publisher_box)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.publisher_box.setCompleter(completer)
        self.logger.debug("Publisher picker filled: %d publishers.", len(publishers))

    def set_labels(self, counts: List[LabelCount]) -> None:
        """Fill the source label picker with the most frequent labels, with their number of items.

        Args:
            counts (List[LabelCount]): The labels of the listed items (see `ItemRepository.label_counts`).
        """
        self.source_label_box.set_counts(counts)

    def pick(self, item_filter: ItemFilter, value: str) -> bool:
        """Choose a value in the picker of a filter (a chip of the details panel was clicked).

        Args:
            item_filter (ItemFilter): The filter: only the publisher is one of the panel.
            value (str): The value.

        Returns:
            bool: Whether the panel filters on it (`False` for the filters of the main filter row).

        Notes:
            A publisher missing from the picker (not among the most frequent ones) is added to it, so that any chip
            can filter the table.
        """
        if item_filter is not ItemFilter.PUBLISHERS:
            self.logger.debug("The filter %s is not one of the panel.", item_filter.value)   # noqa: E501
            return False
        box = self.publisher_box
        wanted = [value]
        index = box.findData(wanted)
        if index < 0:
            self.logger.debug("Adding %r to the %s picker.", value, item_filter.value)   # noqa: E501
            box.addItem(value, wanted)
            index = box.count() - 1
        box.setCurrentIndex(index)
        self.logger.info("Advanced filter %s set to %r.", item_filter.value, value)   # noqa: E501
        return True

    def active_count(self) -> int:
        """Count the filters of the panel which filter something.

        Returns:
            int: The number of filters set.
        """
        texts = [self.name_box.text(), self.description_box.text(), self.url_box.text()]  # noqa: E501
        boxes = [
            self.audience_box,
            self.added_source_box,
            self.updated_source_box,
            self.precision_box,
        ]
        dates = [
            self.added_after_box,
            self.added_before_box,
            self.updated_after_box,
            self.updated_before_box,
            self.deleted_after_box,
            self.deleted_before_box,
        ]
        publisher = self.publisher_box.currentText().strip() not in ("", self.PICKER_ANY)
        count = sum(bool(text.strip()) for text in texts) + int(publisher) + int(self.source_label_box.is_filtering())
        count += sum(box.currentIndex() > 0 for box in boxes) + sum(box.date() != self.NO_DATE for box in dates)   # noqa: E501
        self.logger.debug("%d advanced filters set.", count)
        return count

    def apply(self, query: ItemQuery) -> ItemQuery:
        """Add the filters of the panel to a query.

        Args:
            query (ItemQuery): The query of the main filters.

        Returns:
            ItemQuery: The query with the filters of the panel.
        """
        publisher = self.publisher_box.currentText().strip()
        audiences: Optional[List[SoftwareAudience]] = self.audience_box.currentData()   # noqa: E501
        approximate, caveats = self.precision_box.currentData()
        filtered = query.model_copy(
            update={
                "name": self.name_box.text().strip() or None,
                "description": self.description_box.text().strip() or None,
                "url": self.url_box.text().strip() or None,
                "publishers": [publisher] if publisher and publisher != self.PICKER_ANY else [],   # noqa: E501
                "source_labels": self.source_label_box.picked(),
                "audiences": list(audiences or []),
                "added": self._date_filter(self.added_after_box, self.added_before_box, self.added_source_box),   # noqa: E501
                "updated": self._date_filter(self.updated_after_box, self.updated_before_box, self.updated_source_box),   # noqa: E501
                "deleted": self._date_filter(self.deleted_after_box, self.deleted_before_box, None),   # noqa: E501
                "approximate": approximate,
                "caveats": list(caveats),
            }
        )
        self.logger.debug("Advanced filters applied: %d set.", self.active_count())   # noqa: E501
        return filtered

    def reset(self) -> None:
        """Clear every filter of the panel, then tell the view once."""
        self.logger.info("Advanced software filters reset.")
        self.blockSignals(True)
        for text_box in (self.name_box, self.description_box, self.url_box):
            text_box.clear()
        self.publisher_box.setCurrentIndex(0)
        self.publisher_box.setEditText("")
        self.source_label_box.reset()
        for box in (
            self.audience_box,
            self.added_source_box,
            self.updated_source_box,
            self.precision_box,
        ):
            box.setCurrentIndex(0)
        for date_box in (
            self.added_after_box,
            self.added_before_box,
            self.updated_after_box,
            self.updated_before_box,
            self.deleted_after_box,
            self.deleted_before_box,
        ):
            date_box.setDate(self.NO_DATE)
        self.blockSignals(False)
        self.changed.emit()
