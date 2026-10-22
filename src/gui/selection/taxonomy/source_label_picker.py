from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QCompleter

# First Party Imports.
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.widgets.compact_combo import CompactCombo
from models.taxonomy.labels.label_count import LabelCount


class SourceLabelPicker(CompactCombo):
    """A picker of the categories of the providers (source labels), by their English name, with their count.

    Attributes:
        ANY (ClassVar[str]): The label of the "any label" entry.
        CONTENTS (ClassVar[int]): The number of characters the closed picker shows.
        logger (Logger): The picker logger.

    Notes:
        - A label stands for its aliases too: "Databases" picks the items labelled "DataBases" or "Базы данных".
        - The name can be typed: the completion finds the labels containing it. The tooltip of each entry gives the
          original text and its language.
    """

    ANY: ClassVar[str] = "Any"
    CONTENTS: ClassVar[int] = 18

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Build the picker, with its "any label" entry only.

        Args:
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__(self.CONTENTS, logger)
        self.logger = logger if logger else getLogger(__name__)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setToolTip("A category of the provider (as labelled there, translated): the items under it or an alias")
        self.addItem(self.ANY, None)
        self.logger.debug("Source label picker built.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_counts(self, counts: Sequence[LabelCount]) -> None:
        """Offer the most frequent labels, keeping the selection.

        Args:
            counts (Sequence[LabelCount]): The labels with their number of items (see `ItemRepository.label_counts`).
        """
        selected = self.currentData()
        selected_text = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItem(self.ANY, None)
        ordered = sorted(counts, key=lambda count: count.name.casefold())
        for count in ordered:
            self.addItem(f"{count.name}  ({count.count:,})", count.id)
            tooltip = count.text if count.text == count.name else f"{count.text} ({count.language.value})"
            self.setItemData(self.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
        index = self.findData(selected) if selected is not None else 0
        if index < 0:
            self.addItem(selected_text, selected)
            index = self.count() - 1
        self.setCurrentIndex(index)
        completer = QCompleter([self.itemText(row) for row in range(1, self.count())], self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(completer)
        self.blockSignals(False)
        self.logger.debug("Source label picker filled: %d labels.", len(ordered))

    def picked(self) -> List[int]:
        """Get the picked label.

        Returns:
            List[int]: Its identifier, empty when any label is accepted.
        """
        index = self.findText(self.currentText())
        data = self.itemData(index) if index >= 0 else None
        return [int(data)] if data is not None else []

    def pick(self, label_id: int, cache: TaxonomyCache) -> None:
        """Pick a label (e.g. a chip of the details panel was clicked), adding it when it is not offered.

        Args:
            label_id (int): Its identifier.
            cache (TaxonomyCache): The names of the labels.
        """
        index = self.findData(label_id)
        if index < 0:
            self.addItem(cache.label_name(label_id) or str(label_id), label_id)
            index = self.count() - 1
        self.logger.info("Source label %d picked.", label_id)
        self.setCurrentIndex(index)

    def is_filtering(self) -> bool:
        """Tell whether a label is picked.

        Returns:
            bool: Whether the picker filters the items.
        """
        return bool(self.picked())

    def reset(self) -> None:
        """Accept any label again."""
        self.setCurrentIndex(0)
        self.setEditText(self.ANY)
