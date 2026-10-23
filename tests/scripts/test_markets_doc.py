from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from analytics.markets.markets_doc_renderer import MarketsDocRenderer
from conf import MARKETS_DOC_PATH
from scripts.docs.render_markets_doc import MarketsDocWriter


def test_the_guide_prints_the_shipped_catalogue() -> None:
    assert MarketsDocWriter().parse(["--check"]) == 0


@pytest.mark.parametrize(
    "source",
    [
        "StatCounter Global Stats",
        "Synergy Research Group",
        "Google Finance",
        "FRED",
        "World Bank API",
        "TrendForce press center",
        "IDC press releases",
        "Source dossier",
    ],
)
def test_every_source_has_a_row_in_the_sources_table(source: str) -> None:
    sources = MARKETS_DOC_PATH.read_text(encoding="utf-8").split("## 2.", 1)[0]

    assert f"| [{source}]" in sources


def test_an_out_of_date_guide_fails_the_check(tmp_path: Path) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("<!-- markets:catalogue:start -->\nold\n<!-- markets:catalogue:end -->\n", encoding="utf-8")

    assert MarketsDocWriter().parse(["--check", "--output", str(guide)]) == 1
    assert MarketsDocWriter().parse(["--output", str(guide)]) == 0
    assert "### Listings" in guide.read_text(encoding="utf-8")


def test_the_coverage_says_which_series_can_be_correlated() -> None:
    long = [date(2009 + index // 12, index % 12 + 1, 1) for index in range(214)]

    block = MarketsDocRenderer().coverage(
        {("search", "US", "all"): long, ("ai-chatbots", "US", "all"): long[-19:]},
        {"NYSE:IBM": long},
        date(2026, 10, 23),
        {("pcs", "ww", "idc"): long[::3][-21:], ("foundry", "ww", "trendforce"): long[::3][-4:]},
    )

    assert "| search | US | all | 2009-01 | 2026-10 | 214 | 0 | yes |" in block
    assert "| ai-chatbots | US | all | 2025-04 | 2026-10 | 19 | 0 | no |" in block
    assert "| NYSE:IBM | 2009-01 | 2026-10 | 214 | 0 | yes |" in block
    assert "| pcs | ww | idc | 2021Q4 | 2026Q4 | 21 | 0 | yes |" in block
    assert "| foundry | ww | trendforce | 2026Q1 | 2026Q4 | 4 | 0 | no |" in block


def test_a_guide_without_markers_is_left_as_is() -> None:
    assert MarketsDocRenderer().splice("no markers", "catalogue", "block") == "no markers"
