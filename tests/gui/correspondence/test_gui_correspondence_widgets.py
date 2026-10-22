from __future__ import annotations

from typing import List, Tuple

import pytest
from pydantic import JsonValue
from PyQt6.QtCore import QPointF, Qt
from pytestqt.qtbot import QtBot

from gui.correspondence.coverage.coverage_matrix import CoverageMatrix
from gui.correspondence.details.concept_details import ConceptDetails
from gui.correspondence.diagram.correspondence_diagram import CorrespondenceDiagram
from gui.correspondence.diagram.diagram_header import DiagramHeader
from gui.correspondence.diagram.diagram_layout import DiagramLayout
from gui.correspondence.diagram.diagram_legend import DiagramLegend
from gui.correspondence.diagram.diagram_scroll_area import DiagramScrollArea
from gui.correspondence.diagram.shapes.diagram_group import DiagramGroup
from gui.correspondence.filters.column_picker import ColumnPicker
from gui.correspondence.filters.correspondence_filters import CorrespondenceFilters
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.correspondence.enums import CardinalityClass, CoverageFilter, MatchStrength
from models.correspondence.rows.concept_row import ConceptRow
from models.correspondence.rows.coverage_cell import CoverageCell

AWS, AZURE, GCP = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP
COLUMNS = [AWS, AZURE, GCP]


def member(product_id: int, provider: CloudProvider, name: str, role: str = "equivalent") -> JsonValue:
    return {"product_id": product_id, "provider": provider.value, "name": name, "role": role, "confidence": 70}


def concepts() -> List[ConceptRow]:
    machines = ConceptRow.model_validate(
        {
            "id": 1,
            "name": "Virtual machines",
            "node_slug": "virtual-machines",
            "members": [
                member(1, AWS, "EC2"),
                member(2, AZURE, "Virtual Machines"),
                member(3, AZURE, "Scale Sets", "partial"),
                member(4, GCP, "Compute Engine"),
            ],
        }
    )
    functions = ConceptRow.model_validate(
        {"id": 2, "name": "Serverless functions", "members": [member(5, AWS, "Lambda"), member(6, GCP, "Cloud Run")]}
    )
    return [machines, functions]


def layout(strength: MatchStrength = MatchStrength.ANY) -> DiagramLayout:
    return DiagramLayout([DiagramGroup("Compute", "#e69f00", concepts())], COLUMNS, strength)


class TestDiagramLayout:
    def test_the_rows_stack_the_services_and_join_the_columns(self) -> None:
        placed = layout()

        assert list(placed.rows) == [1, 2]
        assert placed.rows[1].height() == 2 * DiagramLayout.PILL_HEIGHT + DiagramLayout.PILL_GAP
        assert placed.counts == {AWS: 2, AZURE: 2, GCP: 2}
        gaps = [pill for pill in placed.pills if pill.is_gap()]
        assert [(pill.concept_id, pill.provider) for pill in gaps] == [(2, AZURE)]
        kinds: List[Tuple[int, CardinalityClass, bool]] = [
            (edge.concept_id, edge.kind, edge.partial) for edge in placed.edges
        ]
        assert kinds == [
            (1, CardinalityClass.ONE_TO_ONE, False),
            (1, CardinalityClass.TWO_TO_ONE, False),
            (1, CardinalityClass.TWO_TO_ONE, True),
            (1, CardinalityClass.TWO_TO_ONE, False),
            (1, CardinalityClass.TWO_TO_ONE, True),
            (2, CardinalityClass.ONE_TO_ONE, False),
            (2, CardinalityClass.ONE_TO_ONE, False),
        ]

    def test_the_pills_are_found_under_a_point(self) -> None:
        placed = layout(MatchStrength.EQUIVALENT)
        ec2 = next(pill for pill in placed.pills if pill.text == "EC2")

        assert placed.pill_at(ec2.rect.center()) is ec2
        assert placed.concept_at(ec2.rect.center()) == 1
        assert placed.pill_at(QPointF(1, 1)) is None
        assert all(pill.text != "Scale Sets" for pill in placed.pills)
        assert placed.width > DiagramLayout.CONCEPT_WIDTH + 3 * DiagramLayout.COLUMN_WIDTH


def test_two_columns_of_several_services_merge_through_a_junction() -> None:
    both = ConceptRow.model_validate(
        {
            "id": 3,
            "name": "Storage",
            "members": [
                member(1, AWS, "S3"),
                member(2, AWS, "Glacier"),
                member(3, AZURE, "Blob"),
                member(4, AZURE, "Files"),
            ],
        }
    )

    placed = DiagramLayout([DiagramGroup("Storage", "#56b4e9", [both])], [AWS, AZURE])

    hub = placed.edges[-1].start
    assert len(placed.edges) == 2 + 2 + 2
    assert [edge.end for edge in placed.edges[2:4]] == [hub, hub]
    assert all(edge.kind is CardinalityClass.TWO_TO_ONE for edge in placed.edges[2:])


class TestDiagram:
    def test_the_diagram_paints_selects_zooms_and_exports(self, qtbot: QtBot) -> None:
        diagram = CorrespondenceDiagram(Theme())
        qtbot.addWidget(diagram)
        diagram.fit(1600, 400)
        diagram.set_rows([DiagramGroup("Compute", "#e69f00", concepts())], COLUMNS)
        placed = diagram.layout_
        assert placed is not None
        pill = next(pill for pill in placed.pills if pill.text == "Scale Sets")

        assert not diagram.grab().isNull()
        assert diagram.width() == 1600
        assert placed.width == pytest.approx(1600, abs=1)
        with qtbot.waitSignal(diagram.concept_selected) as selected:
            qtbot.mouseClick(diagram, Qt.MouseButton.LeftButton, pos=pill.rect.center().toPoint())
        assert selected.args == [1]
        assert diagram.selected == 1
        assert "Partial" in diagram._tooltip(pill)
        for _ in range(12):
            diagram.widen()
        assert diagram.column_target == CorrespondenceDiagram.COLUMN_RANGE[1]
        assert diagram.width() > 1600
        lines = diagram.csv().splitlines()
        assert lines[0].startswith("Service concept,Domain,Amazon Web Services")
        assert "Scale Sets (partial)" in lines[1]
        diagram.set_message("Reading…")
        assert diagram.csv() == ""

    def test_every_provider_fits_the_width_under_a_sticky_header(self, qtbot: QtBot) -> None:
        diagram, header = CorrespondenceDiagram(Theme()), DiagramHeader(Theme())
        area = DiagramScrollArea(diagram, header)
        qtbot.addWidget(area)
        qtbot.addWidget(header)
        area.resize(1200, 500)
        area.show()
        providers = list(CloudProvider)

        diagram.set_rows([DiagramGroup("Compute", "#e69f00", concepts())], providers)

        placed = diagram.layout_
        assert placed is not None
        assert header.layout_ is placed
        assert placed.column_width >= CorrespondenceDiagram.READABLE_COLUMN - 1
        assert placed.width > area.viewport().width()  # type: ignore[union-attr]
        assert header.height() == int(DiagramLayout.HEADER_HEIGHT)
        diagram.fit_all()
        fitted = diagram.layout_
        assert fitted is not None
        assert fitted.column_width < DiagramLayout.NARROW_COLUMN
        assert fitted.width <= area.viewport().width() + 1  # type: ignore[union-attr]
        assert not header.grab().isNull()
        diagram.readable()
        scroll_bar = area.horizontalScrollBar()
        assert scroll_bar is not None
        scroll_bar.setValue(150)
        assert header.offset == 150

    def test_the_legend_explains_every_class(self, qtbot: QtBot) -> None:
        legend = DiagramLegend(Theme())
        qtbot.addWidget(legend)

        assert legend.sizeHint().width() > 600
        assert not legend.grab().isNull()


def test_a_clicked_cell_compares_two_providers(qtbot: QtBot) -> None:
    matrix = CoverageMatrix(Theme())
    qtbot.addWidget(matrix)
    matrix.set_cells([AWS, AZURE], [CoverageCell(source=AWS, target=AZURE, matched=3, total=4)])
    cell = matrix._cell_rect(0, 1).center().toPoint()

    with qtbot.waitSignal(matrix.pair_selected) as picked:
        qtbot.mouseClick(matrix, Qt.MouseButton.LeftButton, pos=cell)

    assert picked.args == [AWS.value, AZURE.value]
    assert matrix._cell_at(QPointF(matrix._cell_rect(0, 0).center())) is None
    assert not matrix.grab().isNull()


def test_the_columns_move_and_follow_the_presets(qtbot: QtBot) -> None:
    picker = ColumnPicker(Theme(), list(CloudProvider), COLUMNS)
    qtbot.addWidget(picker)
    assert picker.all_button.isChecked()
    assert len(picker.columns()) == len(CloudProvider)
    picker.set_sizes({CloudProvider.BAIDU: 300, AWS: 260, CloudProvider.OVH: 100, CloudProvider.YANDEX_CLOUD: 50})

    assert picker.columns()[:4] == [AWS, CloudProvider.OVH, CloudProvider.BAIDU, CloudProvider.YANDEX_CLOUD]
    with qtbot.waitSignal(picker.changed):
        picker.all_button.setChecked(False)
    assert picker.columns() == COLUMNS
    with qtbot.waitSignal(picker.changed):
        picker._move(GCP, -1)
    assert picker.columns() == [AWS, GCP, AZURE]
    picker._add(CloudProvider.OVH)
    picker._remove(AWS)
    assert picker.columns() == [GCP, AZURE, CloudProvider.OVH]
    presets = picker._presets()
    assert presets["Largest catalogues"][:3] == [CloudProvider.BAIDU, AWS, CloudProvider.OVH]
    assert presets["Leader of each bloc"][:4] == [
        AWS,
        CloudProvider.OVH,
        CloudProvider.BAIDU,
        CloudProvider.YANDEX_CLOUD,
    ]
    picker.set_columns([AWS, AZURE])
    picker._remove(AWS)
    assert picker.columns() == [AWS, AZURE]


def test_the_filters_build_the_query(qtbot: QtBot, offline_loop: StorageLoop) -> None:
    filters = CorrespondenceFilters(Theme(), TaxonomyCache(offline_loop))
    qtbot.addWidget(filters)

    filters.class_buttons[CardinalityClass.TWO_TO_ONE].setChecked(True)
    filters.set_coverage(CoverageFilter.GAPS)
    filters.confidence_box.setValue(60)
    filters.search_box.setText("  kubernetes ")
    query = filters.query(COLUMNS)
    filters.set_class_counts({CardinalityClass.TWO_TO_ONE: 12})

    assert (query.cardinalities, query.coverage, query.min_confidence, query.search) == (
        [CardinalityClass.TWO_TO_ONE],
        CoverageFilter.GAPS,
        60,
        "kubernetes",
    )
    assert filters.class_buttons[CardinalityClass.TWO_TO_ONE].text() == "2:1  12"
    with qtbot.waitSignal(filters.changed):
        filters.reset()
    assert filters.query(COLUMNS).coverage is CoverageFilter.ALL


def test_the_details_list_the_services_and_their_actions(qtbot: QtBot) -> None:
    details = ConceptDetails(Theme())
    qtbot.addWidget(details)
    assert not details.rename_button.isEnabled()

    details.show_concept(concepts()[0], "Compute > Virtual machines")

    assert details.title_label.text() == "Virtual machines"
    assert "3 providers" in details.path_label.text()
    assert "Scale Sets" in details.members_label.text()
    with qtbot.waitSignal(details.unlink_requested) as removed:
        details._on_link("remove:3")
    assert removed.args == [1, 3]
    with qtbot.waitSignal(details.role_requested) as role:
        details._on_link("role:3:equivalent")
    assert role.args == [1, 3, "equivalent"]
    with qtbot.waitSignal(details.rematch_requested) as rematch:
        details.rematch_button.click()
    assert rematch.args == ["virtual-machines"]
