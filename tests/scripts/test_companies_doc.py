from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from analytics.companies.companies_doc_renderer import CompaniesDocRenderer
from conf import COMPANIES_DOC_PATH
from models.companies.companies_catalog import CompaniesCatalog
from scripts.docs.render_companies_doc import CompaniesDocWriter


def test_the_guide_prints_the_shipped_catalogue() -> None:
    assert CompaniesDocWriter().parse(["--check"]) == 0


@pytest.mark.parametrize("source", ["SEC EDGAR XBRL", "Google Finance", "Google Patents", "OpenAlex"])
def test_every_source_has_a_row_in_the_sources_table(source: str) -> None:
    sources = COMPANIES_DOC_PATH.read_text(encoding="utf-8").split("## 2.", 1)[0]

    assert f"| [{source}]" in sources


def test_an_out_of_date_guide_fails_the_check(tmp_path: Path) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("<!-- companies:catalogue:start -->\nold\n<!-- companies:catalogue:end -->\n", encoding="utf-8")

    assert CompaniesDocWriter().parse(["--check", "--output", str(guide)]) == 1


def test_the_coverage_prints_the_span_of_each_series(companies_catalog: CompaniesCatalog) -> None:
    spans = {("nvidia", "revenue", "year"): (date(2008, 1, 27), date(2026, 1, 25), 19)}

    block = CompaniesDocRenderer().coverage(companies_catalog, spans, date(2026, 10, 25))

    assert "| `nvidia` | - | 2008-01-27 to 2026-01-25 (19) |" in block
    assert block.startswith("Stored on 2026-10-25")
