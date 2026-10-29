from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from analytics.compounding.compounding_analysis import CompoundingAnalysis
from analytics.compounding.config_loader import CompoundingConfigLoader
from analytics.compounding.doc.compounding_doc_renderer import CompoundingDocRenderer
from analytics.compounding.help_loader import CompoundingHelpLoader
from conf import COMPOUNDING_DOC_PATH
from models.cloud.enums import CloudProvider
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.data.dated_product import DatedProduct
from models.compounding.data.year_value import YearValue
from models.compounding.enums import CompoundingCard, ValueOrigin
from scripts.docs.render_compounding_doc import CompoundingDocWriter


def test_the_document_is_up_to_date_with_the_configuration() -> None:
    assert CompoundingDocWriter().parse(["--check"]) == 0


def test_every_card_of_the_analysis_tab_has_a_block_in_the_document() -> None:
    text = COMPOUNDING_DOC_PATH.read_text(encoding="utf-8")

    assert CompoundingDocWriter().missing(text) == []
    for card in CompoundingCard:
        assert f"<!-- compounding:{card.value}:start -->" in text


def test_a_document_without_its_markers_fails_the_check(tmp_path: Path) -> None:
    document = tmp_path / "results.md"
    document.write_text("<!-- compounding:scope:start -->\nold\n<!-- compounding:scope:end -->\n", encoding="utf-8")

    assert CompoundingDocWriter().parse(["--check", "--output", str(document)]) == 1


def test_the_renderer_prints_a_table_for_every_card() -> None:
    config = CompoundingConfigLoader().load()
    config = config.model_copy(
        update={"settings": config.settings.model_copy(update={"min_events": 1, "bootstrap": 0, "placebo": 3})}
    )
    products: List[DatedProduct] = [
        DatedProduct(provider=provider, year=2013 + offset + 2 * index, categories=[category])
        for offset, provider in enumerate((CloudProvider.AWS, CloudProvider.AZURE))
        for index, category in enumerate(["virtual-machines", "kubernetes", "object-storage", "data-lake"])
    ]
    data = CompoundingData(
        products=products,
        market=[
            YearValue(year=year, value=10.0 + year - 2010, origin=ValueOrigin.CRAWLED) for year in range(2010, 2026)
        ],
        categories=["virtual-machines", "kubernetes", "object-storage", "data-lake"],
    )
    report = CompoundingAnalysis(config).run(CompoundingQuery(), data)
    renderer = CompoundingDocRenderer(CompoundingHelpLoader().load())

    for card in CompoundingCard:
        assert renderer.card(card, report).strip()
    assert "| `amazon-web-services` |" in renderer.card(CompoundingCard.CONTROLS, report)
    assert renderer.splice("<!-- compounding:run:start -->\n<!-- compounding:run:end -->", "run", "x").count("x") == 1


@pytest.mark.parametrize("name", ["scope", "run", "robustness"])
def test_the_extra_blocks_are_named(name: str) -> None:
    assert name in CompoundingDocRenderer(CompoundingHelpLoader().load()).names()
