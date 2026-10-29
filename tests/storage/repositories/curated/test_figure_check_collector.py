from __future__ import annotations

import pytest

from analytics.companies.checks.figure_check_collector import FigureCheckCollector
from models.companies.checks.document_numbers import DocumentNumbers
from models.curated.enums import FigureCheck
from storage.storage import Storage

pytestmark = pytest.mark.db


async def test_a_year_is_marked_without_changing_its_figures(storage: Storage) -> None:
    await storage.curated_seeder.seed()
    figures = await storage.catalogs.figures()
    entry = figures.of("ibm")
    assert entry is not None
    year = next(item for item in entry.years if item.fiscal_year == 1980)
    before = await storage.reported_years.read("ibm", 1980)
    collector = FigureCheckCollector(storage)
    numbers = sorted(abs(value) for value in year.figures.values())
    full = DocumentNumbers(company="ibm", fiscal_years=[1980], source_url=year.source, numbers=numbers)
    partial = DocumentNumbers(company="ibm", fiscal_years=[1980], source_url=year.source, numbers=numbers[1:])

    assert await collector.write([full]) == 1
    matched = await storage.reported_years.read("ibm", 1980)
    assert await collector.write([partial]) == 1
    mismatched = await storage.reported_years.read("ibm", 1980)

    assert before is not None
    assert matched is not None
    assert matched.check_status is FigureCheck.MATCH
    assert matched.check_note is None
    assert matched.body == before.body
    assert matched.edited == before.edited
    assert mismatched is not None
    assert mismatched.check_status is FigureCheck.MISMATCH
    assert (mismatched.check_note or "").startswith("not found: ")
    assert await storage.catalogs.figures() == figures


async def test_a_document_no_longer_cited_is_left_out(storage: Storage) -> None:
    await storage.curated_seeder.seed()
    other = DocumentNumbers(
        company="ibm", fiscal_years=[1980], source_url="https://www.sec.gov/other.txt", numbers=[1.0]
    )

    assert await FigureCheckCollector(storage).write([other]) == 0
    unchecked = await storage.reported_years.read("ibm", 1980)
    assert unchecked is not None
    assert unchecked.check_status is FigureCheck.UNCHECKED
