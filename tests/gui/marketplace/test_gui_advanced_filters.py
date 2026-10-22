from __future__ import annotations

from datetime import UTC, datetime, time
from typing import List

import pytest
from PyQt6.QtCore import QDate
from pytestqt.qtbot import QtBot

from gui.marketplace.widgets.advanced_filters import AdvancedSoftwareFilters
from gui.theme import Theme
from models.cloud.enums import DateCaveat, DateSource, SoftwareAudience
from models.storage.enums import ItemFilter
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.software_facets import SoftwareFacets
from models.taxonomy.labels.label_count import LabelCount


def local_midnight(year: int, month: int, day: int) -> datetime:
    return datetime.combine(datetime(year, month, day).date(), time.min).astimezone().astimezone(UTC)


@pytest.fixture
def panel(qtbot: QtBot) -> AdvancedSoftwareFilters:
    widget = AdvancedSoftwareFilters(Theme())
    qtbot.addWidget(widget)
    widget.set_pickers(SoftwareFacets(by_publisher={"Grafana Labs": 2, "Odoo SA": 1}))
    widget.set_labels(
        [
            LabelCount(id=7, name="Monitoring", text="Monitoring", count=1),
            LabelCount(id=3, name="CRM", text="CRM", count=3),
        ]
    )
    return widget


def test_an_untouched_panel_filters_nothing(panel: AdvancedSoftwareFilters) -> None:
    query = panel.apply(ItemQuery())

    assert query == ItemQuery()
    assert panel.active_count() == 0


def test_the_pickers_list_the_counted_values(panel: AdvancedSoftwareFilters) -> None:
    box = panel.source_label_box
    assert [box.itemText(index) for index in range(box.count())] == ["Any", "CRM  (3)", "Monitoring  (1)"]
    assert panel.publisher_box.itemText(1) == "Grafana Labs"
    completer = panel.publisher_box.completer()
    assert completer is not None
    model = completer.model()
    assert model is not None
    assert model.rowCount() == 2


def test_every_filter_reaches_the_query(panel: AdvancedSoftwareFilters, qtbot: QtBot) -> None:
    with qtbot.waitSignal(panel.changed):
        panel.name_box.setText(" graf ")
    panel.description_box.setText("dashboards")
    panel.url_box.setText("example")
    panel.publisher_box.setCurrentIndex(panel.publisher_box.findText("Odoo SA"))
    panel.source_label_box.setCurrentIndex(1)
    panel.added_after_box.setDate(QDate(2026, 1, 1))
    panel.added_before_box.setDate(QDate(2026, 1, 31))
    panel.added_source_box.setCurrentIndex(panel.added_source_box.findText("Published by the website"))
    panel.updated_source_box.setCurrentIndex(panel.updated_source_box.findText("Unknown"))
    panel.deleted_after_box.setDate(QDate(2026, 2, 1))
    panel.precision_box.setCurrentIndex(panel.precision_box.findText("Approximate dates"))

    query = panel.apply(ItemQuery())

    assert (query.name, query.description, query.url) == ("graf", "dashboards", "example")
    assert (query.publishers, query.source_labels) == (["Odoo SA"], [3])
    assert (query.added.after, query.added.before) == (local_midnight(2026, 1, 1), local_midnight(2026, 2, 1))
    assert query.added.sources == [DateSource.WEBSITE]
    assert (query.updated.known, query.updated.sources) == (False, [])
    assert (query.deleted.after, query.deleted.before) == (local_midnight(2026, 2, 1), None)
    assert (query.approximate, query.caveats) == (True, [])
    assert panel.active_count() == 11


def test_a_typed_publisher_and_a_caveat_are_used(panel: AdvancedSoftwareFilters) -> None:
    panel.publisher_box.setEditText("Unknown Vendor")
    panel.precision_box.setCurrentIndex(panel.precision_box.findText(f"⚠ {Theme.CAVEAT_LABELS[DateCaveat.YEAR_ONLY]}"))

    query = panel.apply(ItemQuery())

    assert query.publishers == ["Unknown Vendor"]
    assert (query.approximate, query.caveats) == (None, [DateCaveat.YEAR_ONLY])


def test_a_reversed_range_is_swapped(panel: AdvancedSoftwareFilters, caplog: pytest.LogCaptureFixture) -> None:
    panel.updated_after_box.setDate(QDate(2026, 3, 10))
    panel.updated_before_box.setDate(QDate(2026, 3, 1))

    query = panel.apply(ItemQuery())

    assert (query.updated.after, query.updated.before) == (local_midnight(2026, 3, 1), local_midnight(2026, 3, 11))
    assert any("bounds are swapped" in message for message in caplog.messages)


def test_reset_clears_every_filter_and_tells_once(panel: AdvancedSoftwareFilters, qtbot: QtBot) -> None:
    panel.name_box.setText("graf")
    panel.source_label_box.setCurrentIndex(1)
    panel.deleted_before_box.setDate(QDate(2026, 2, 1))
    signals: List[None] = []
    panel.changed.connect(lambda: signals.append(None))

    panel.reset_button.click()

    assert panel.apply(ItemQuery()) == ItemQuery()
    assert panel.active_count() == 0
    assert len(signals) == 1


def test_refilling_the_pickers_keeps_the_selection(panel: AdvancedSoftwareFilters) -> None:
    panel.source_label_box.setCurrentIndex(panel.source_label_box.findText("Monitoring  (1)"))
    panel.publisher_box.setEditText("Typed Vendor")

    panel.set_pickers(SoftwareFacets(by_publisher={"Odoo SA": 1}))
    panel.set_labels([LabelCount(id=7, name="Monitoring", text="Monitoring", count=1)])

    assert panel.source_label_box.currentText() == "Monitoring  (1)"
    assert panel.publisher_box.currentText() == "Typed Vendor"


def test_a_publisher_chip_picks_its_value_even_when_not_listed(panel: AdvancedSoftwareFilters, qtbot: QtBot) -> None:
    with qtbot.waitSignal(panel.changed):
        assert panel.pick(ItemFilter.PUBLISHERS, "Unlisted Vendor")

    assert panel.apply(ItemQuery()).publishers == ["Unlisted Vendor"]
    assert not panel.pick(ItemFilter.PROVIDERS, "aws")


@pytest.mark.parametrize("software_fields", [True, False])
def test_the_items_are_filtered_on_their_audience(qtbot: QtBot, software_fields: bool) -> None:
    panel = AdvancedSoftwareFilters(Theme(), software_fields=software_fields)
    qtbot.addWidget(panel)
    panel.show()
    signals: List[None] = []
    panel.changed.connect(lambda: signals.append(None))

    assert [panel.audience_box.itemText(index) for index in range(panel.audience_box.count())] == [
        "Any",
        "Developer tool only",
        "End-user software only",
        "Both",
    ]
    assert panel.audience_box.isVisible()
    panel.audience_box.setCurrentIndex(3)

    assert panel.apply(ItemQuery()).audiences == [SoftwareAudience.BOTH]
    assert panel.active_count() == 1
    assert len(signals) == 1
    panel.reset()
    assert panel.apply(ItemQuery()).audiences == []
