from __future__ import annotations

from typing import List

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from gui.marketplace.widgets.advanced_filters import AdvancedSoftwareFilters
from gui.selection.pickers.provider_picker import ProviderPicker
from gui.selection.pickers.provider_tree import ProviderTree
from gui.selection.pickers.value_checklist import ValueChecklist
from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country
from models.storage.pages.item_query import ItemQuery

PROVIDERS = [CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.OVH, CloudProvider.SCALEWAY]


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    return Theme()


class TestProviderTree:
    def test_providers_are_grouped_under_their_country_and_checked(self, theme: Theme) -> None:
        tree = ProviderTree(theme, PROVIDERS)

        assert set(tree.country_items) == {Country.UNITED_STATES, Country.FRANCE}
        assert tree.country_items[Country.FRANCE].childCount() == 2
        assert tree.checked() == PROVIDERS
        assert tree.country_items[Country.FRANCE].checkState(0) == Qt.CheckState.Checked

    def test_a_country_checks_or_unchecks_its_providers(self, theme: Theme, qtbot: QtBot) -> None:
        tree = ProviderTree(theme, PROVIDERS)

        with qtbot.waitSignal(tree.changed):
            tree.country_items[Country.FRANCE].setCheckState(0, Qt.CheckState.Unchecked)

        assert tree.checked() == [CloudProvider.AWS, CloudProvider.AZURE]

    def test_some_providers_are_checked_at_once(self, theme: Theme, qtbot: QtBot) -> None:
        tree = ProviderTree(theme, PROVIDERS)
        emitted: List[None] = []
        tree.changed.connect(lambda: emitted.append(None))

        tree.set_checked([CloudProvider.SCALEWAY, CloudProvider.ALIBABA])

        assert tree.checked() == [CloudProvider.SCALEWAY]
        assert len(emitted) == 1, "told once"
        assert tree.country_items[Country.FRANCE].checkState(0) == Qt.CheckState.PartiallyChecked
        tree.check_all(False)
        assert tree.checked() == []
        tree.check_all(True)
        assert tree.checked() == PROVIDERS


class TestProviderPicker:
    def test_the_picked_providers_are_the_checked_shown_ones(self, theme: Theme, qtbot: QtBot) -> None:
        picker = ProviderPicker(theme, PROVIDERS)
        assert picker.picked() is None, "every provider: no filter"
        assert picker.text().startswith("All providers")

        with qtbot.waitSignal(picker.changed):
            picker.tree.provider_items[CloudProvider.AZURE].setCheckState(0, Qt.CheckState.Unchecked)

        assert picker.picked() == [CloudProvider.AWS, CloudProvider.OVH, CloudProvider.SCALEWAY]
        assert picker.text().startswith("3 providers")
        picker.show_only([CloudProvider.AWS, CloudProvider.AZURE])
        assert picker.picked() == [CloudProvider.AWS]
        assert picker.text().startswith("Amazon")
        assert picker.tree.country_items[Country.FRANCE].isHidden()
        picker.none_button.click()
        assert picker.picked() == []
        assert picker.text().startswith("No provider")
        picker.show_only(PROVIDERS)
        assert picker.picked() == [CloudProvider.OVH, CloudProvider.SCALEWAY], "the hidden ones kept their check"
        picker.reset()
        assert picker.picked() is None

    def test_the_counts_are_shown_by_provider_and_country(self, theme: Theme, qtbot: QtBot) -> None:
        picker = ProviderPicker(theme, PROVIDERS)

        with qtbot.assertNotEmitted(picker.changed):
            picker.set_counts({CloudProvider.OVH: 3, CloudProvider.SCALEWAY: 1200})

        assert picker.tree.provider_items[CloudProvider.SCALEWAY].text(0).endswith("(1,200)")
        assert picker.tree.country_items[Country.FRANCE].text(0).endswith("(1,203)")
        assert picker.tree.provider_items[CloudProvider.AWS].text(0).endswith("(0)")


class TestValueChecklist:
    def test_values_are_checked_and_read(self, qapp: QApplication, qtbot: QtBot) -> None:
        checklist = ValueChecklist({"a": "Alpha", "b": "Beta", "c": "Gamma"})
        assert checklist.checked() == []

        with qtbot.waitSignal(checklist.changed):
            checklist.set_checked(["c", "a"])

        assert checklist.checked() == ["a", "c"]
        item = checklist.item(1)
        assert item is not None
        with qtbot.waitSignal(checklist.changed):
            item.setCheckState(Qt.CheckState.Checked)
        assert checklist.checked() == ["a", "b", "c"]


class TestProductFilters:
    def test_the_software_fields_are_left_out_for_products(self, theme: Theme) -> None:
        panel = AdvancedSoftwareFilters(theme, software_fields=False)
        panel.name_box.setText("storage")

        query = panel.apply(ItemQuery())

        assert not panel.software_fields
        assert panel.publisher_box.isHidden()
        assert (query.name, query.publishers, query.source_labels) == ("storage", [], [])
        assert panel.active_count() == 1
