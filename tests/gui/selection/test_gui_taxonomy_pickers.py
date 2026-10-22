from __future__ import annotations

from typing import List

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from gui.selection.taxonomy.category_picker import CategoryPicker
from gui.selection.taxonomy.source_label_picker import SourceLabelPicker
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from models.taxonomy.enums import LabelStatus, Language
from models.taxonomy.labels.label_count import LabelCount
from models.taxonomy.labels.source_label import SourceLabel


@pytest.fixture
def cache(qapp: QApplication) -> TaxonomyCache:
    return TaxonomyCache()


class TestTaxonomyCache:
    def test_the_seed_names_the_categories_before_the_storage_answers(self, cache: TaxonomyCache) -> None:
        assert cache.name("kubernetes") == "Managed Kubernetes"
        assert cache.path("relational-database") == "Databases > Relational databases"
        assert cache.path("databases") == "Databases"
        assert cache.name("nowhere") == "nowhere"
        assert cache.names(["kubernetes", "container-registry"]) == "Managed Kubernetes, Container registries"
        assert cache.description("kubernetes")

    def test_the_labels_are_named_in_english_with_their_original_text(self, cache: TaxonomyCache, qtbot: QtBot) -> None:
        labels = [
            SourceLabel(id=1, text="Базы данных", language=Language.RUSSIAN, name_en="Databases"),
            SourceLabel(id=2, text="数据决策", language=Language.CHINESE, status=LabelStatus.PENDING),
        ]
        with qtbot.waitSignal(cache.changed):
            cache._on_labels(labels)

        assert cache.label_name(1) == "Databases"
        assert cache.label_name(2) == "数据决策"
        assert cache.label_name(3) is None
        assert cache.label_tooltip(1) == "Базы данных (Russian)"
        assert cache.label_tooltip(2) == "数据决策 (Chinese, not translated yet)"
        assert cache.label_names([1, 2, 1]) == "Databases, 数据决策"
        assert cache.label_names([3], ["Raw"]) == "Raw"

    def test_without_storage_the_seed_is_kept(self, cache: TaxonomyCache) -> None:
        cache.load()

        assert cache.taxonomy.is_category("kubernetes")


class TestCategoryPicker:
    def test_nothing_picked_is_no_filter(self, cache: TaxonomyCache) -> None:
        picker = CategoryPicker(cache)

        assert picker.picked() == []
        assert picker.text().startswith("All categories")

    def test_a_full_domain_is_picked_as_itself(self, cache: TaxonomyCache, qtbot: QtBot) -> None:
        picker = CategoryPicker(cache)

        with qtbot.waitSignal(picker.changed):
            picker.set_picked(["databases", "kubernetes"])

        assert picker.picked() == ["kubernetes", "databases"]
        assert picker.text().startswith("2 categories")
        assert "Databases" in picker.toolTip()

    def test_checked_categories_are_picked(self, cache: TaxonomyCache) -> None:
        picker = CategoryPicker(cache)
        picker.tree.category_items["object-storage"].setCheckState(0, Qt.CheckState.Checked)

        assert picker.picked() == ["object-storage"]
        assert picker.text().startswith("Object storage")
        picker.reset()
        assert picker.picked() == []

    def test_counts_are_shown_and_hidden_categories_appear_with_items(self, cache: TaxonomyCache) -> None:
        picker = CategoryPicker(cache)
        other = picker.tree.category_items["other"]
        assert other.isHidden()

        picker.set_counts({"databases": 12, "relational-database": 7, "other": 3})

        assert picker.tree.domain_items["databases"].text(0) == "Databases  (12)"
        assert picker.tree.category_items["relational-database"].text(0) == "Relational databases  (7)"
        assert not other.isHidden()

    def test_the_search_narrows_the_tree(self, cache: TaxonomyCache) -> None:
        picker = CategoryPicker(cache)

        picker.search_box.setText("relational")

        shown: List[str] = [slug for slug, item in picker.tree.category_items.items() if not item.isHidden()]
        assert shown == ["relational-database"]
        picker.search_box.setText("")
        assert not picker.tree.category_items["kubernetes"].isHidden()

    def test_the_picks_survive_a_new_taxonomy(self, cache: TaxonomyCache, qtbot: QtBot) -> None:
        picker = CategoryPicker(cache)
        picker.set_picked(["kubernetes"])

        cache._on_taxonomy(cache.taxonomy)

        assert picker.picked() == ["kubernetes"]


class TestSourceLabelPicker:
    def test_labels_are_offered_with_their_counts_and_original_text(self, qapp: QApplication) -> None:
        picker = SourceLabelPicker()
        counts = [
            LabelCount(id=2, name="Databases", text="Базы данных", language=Language.RUSSIAN, count=12),
            LabelCount(id=1, name="AI agents", text="AI agents", count=3),
        ]

        picker.set_counts(counts)

        assert [picker.itemText(row) for row in range(picker.count())] == ["Any", "AI agents  (3)", "Databases  (12)"]
        assert picker.itemData(2, Qt.ItemDataRole.ToolTipRole) == "Базы данных (ru)"
        assert picker.picked() == []
        picker.setCurrentIndex(2)
        assert (picker.picked(), picker.is_filtering()) == ([2], True)
        picker.set_counts(counts[:1])
        assert picker.picked() == [2], "the selection is kept"
        picker.reset()
        assert picker.picked() == []

    def test_a_label_not_offered_is_added_when_picked(self, cache: TaxonomyCache) -> None:
        picker = SourceLabelPicker()
        cache._on_labels([SourceLabel(id=9, text="Rare", name_en="Rare")])

        picker.pick(9, cache)

        assert picker.picked() == [9]
        assert picker.currentText() == "Rare"
