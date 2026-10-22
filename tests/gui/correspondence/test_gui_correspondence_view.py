from __future__ import annotations

from typing import Dict

import pytest
from pytestqt.qtbot import QtBot
from sqlalchemy import text

from conftest import build_product, seed_catalogue
from gui.correspondence.correspondence_view import CorrespondenceView
from gui.storage_bridge.storage_loop import StorageLoop
from gui.taxonomy.taxonomy_cache import TaxonomyCache
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.configuration.llm.llm_settings import LLMSettings
from models.correspondence.enums import CoverageFilter, ViewMode
from models.correspondence.llm.concept_answer import ConceptAnswer
from storage.storage import Storage

pytestmark = pytest.mark.db

AWS, AZURE, GCP = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP


async def matched(storage: Storage) -> Dict[str, int]:
    await storage.seeder.seed()
    for provider, names in ((AWS, ["EKS"]), (AZURE, ["AKS"]), (GCP, ["GKE"])):
        await seed_catalogue(storage, provider, [build_product(name) for name in names])
    async with storage.database.connect() as connection, connection.begin():
        await connection.execute(text("UPDATE products SET service_categories = ARRAY['kubernetes']"))
        ids = {
            str(name): int(row_id)
            for row_id, name in (await connection.execute(text("SELECT id, name FROM products"))).all()
        }
    answer = ConceptAnswer.model_validate(
        {"name": "Managed Kubernetes", "members": [{"id": product_id} for product_id in ids.values()]}
    )
    await storage.correspondences.apply_answer("kubernetes", [answer], list(ids.values()))
    return ids


@pytest.fixture
def view(qtbot: QtBot, gui_loop: StorageLoop) -> CorrespondenceView:
    widget = CorrespondenceView(Theme(), gui_loop, TaxonomyCache(gui_loop), llm_settings=LLMSettings())
    qtbot.addWidget(widget)
    return widget


async def test_the_concepts_are_drawn_selected_and_edited(
    storage: Storage, view: CorrespondenceView, qtbot: QtBot
) -> None:
    ids = await matched(storage)
    view.columns.set_columns([AWS, AZURE, GCP])

    view.refresh()

    qtbot.waitUntil(lambda: view.diagram.layout_ is not None and len(view.diagram.layout_.rows) == 1, timeout=10_000)
    qtbot.waitUntil(lambda: view.concepts_card.value_label.text() == "1", timeout=10_000)
    assert view.matched_card.value_label.text() == "100%"
    assert not view.match_button.isEnabled()
    layout = view.diagram.layout_
    assert layout is not None
    assert layout.groups[0].title == "Containers & Kubernetes"
    concept_id = layout.groups[0].concepts[0].id
    view.select(concept_id)
    qtbot.waitUntil(lambda: view.details.concept is not None, timeout=10_000)
    assert view.details.title_label.text() == "Managed Kubernetes"

    view.details.unlink_requested.emit(concept_id, ids["AKS"])

    qtbot.waitUntil(lambda: view.details.concept is not None and len(view.details.concept.members) == 2, timeout=10_000)
    qtbot.waitUntil(lambda: view.matched_card.value_label.text() == "67%", timeout=10_000)


async def test_a_coverage_cell_compares_two_providers(storage: Storage, view: CorrespondenceView, qtbot: QtBot) -> None:
    await matched(storage)
    view.refresh()
    qtbot.waitUntil(lambda: bool(view.coverage.providers), timeout=10_000)

    view.coverage.pair_selected.emit(AWS.value, GCP.value)

    assert view.columns.columns() == [AWS, GCP]
    assert view.filters.query(view.columns.columns()).coverage is CoverageFilter.GAPS
    qtbot.waitUntil(
        lambda: view.diagram.layout_ is not None and view.diagram.layout_.columns == [AWS, GCP], timeout=10_000
    )
    assert view.diagram.layout_ is not None
    assert view.diagram.layout_.rows == {}


async def test_the_categories_are_shown_while_the_ai_matched_nothing(
    storage: Storage, view: CorrespondenceView, qtbot: QtBot
) -> None:
    await storage.seeder.seed()
    for provider, name in ((AWS, "EKS"), (AZURE, "AKS")):
        await seed_catalogue(storage, provider, [build_product(name)])
    async with storage.database.connect() as connection, connection.begin():
        await connection.execute(text("UPDATE products SET service_categories = ARRAY['kubernetes']"))

    view.refresh()

    qtbot.waitUntil(lambda: view.diagram.layout_ is not None and len(view.diagram.layout_.rows) == 1, timeout=10_000)
    assert view.filters.query(view.columns.columns()).mode is ViewMode.CATEGORIES
    assert view.diagram.title == "Taxonomy category"
    assert "taxonomy categories" in view.status_label.text()
    assert not view.match_button.isEnabled()
    layout = view.diagram.layout_
    assert layout is not None
    view.diagram.concept_selected.emit(layout.groups[0].concepts[0].id)
    assert view.details.title_label.text() == "Managed Kubernetes"
    assert not view.details.rename_button.isEnabled()
