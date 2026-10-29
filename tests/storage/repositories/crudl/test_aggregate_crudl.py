from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

import pytest

from models.cloud.enums import CloudProvider, MarketPlayer
from models.cloud.products.product import CloudProduct
from models.companies.papers.paper_record import PaperRecord
from models.companies.patents.patent_detail import PatentDetail
from models.companies.stored.patents.inventor_profile import InventorProfile
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.storage.records.record_query import RecordQuery
from storage.exception import StorageReadError, StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db

T0 = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)


class TestCompanyAggregates:
    async def test_a_patent_with_its_page(self, storage: Storage) -> None:
        detail = PatentDetail(
            publication_number="US11000000B2",
            title="Neural rendering",
            inventors=["Jan Kautz"],
            cpc=["G06N3/08"],
            source_url="https://patents.google.com/patent/US11000000B2/en",
        )

        created = await storage.patents.create(detail)
        updated = await storage.patents.update(detail.model_copy(update={"inventors": ["Jan Kautz", "Ming-Yu Liu"]}))
        read = await storage.patents.read("us11000000b2")
        page = await storage.patents.list(RecordQuery(text="neural"))

        assert created.inventors == ["Jan Kautz"]
        assert updated is True
        assert read is not None
        assert read.inventors == ["Jan Kautz", "Ming-Yu Liu"]
        assert [item.publication_number for item in page.items] == ["US11000000B2"]
        with pytest.raises(StorageWriteError, match="already exists"):
            await storage.patents.create(detail)
        assert await storage.patents.delete("US11000000B2") is True
        assert await storage.patents.read("US11000000B2") is None
        assert await storage.patents.update(detail) is False

    async def test_a_paper_with_its_authors(self, storage: Storage) -> None:
        paper = PaperRecord(
            openalex_id="W1001",
            company="nvidia",
            publication_year=2019,
            authorships=[{"position": 0, "author_id": "A5001", "name": "Author 1", "company_affiliated": True}],
            source_url="u",
        )

        created = await storage.papers.create(paper)
        assert await storage.papers.update(paper.model_copy(update={"cited_by_count": 9})) is True
        read = await storage.papers.read("W1001")

        assert [author.name for author in created.authors] == ["Author 1"]
        assert read is not None
        assert read.cited_by_count == 9
        assert [item.openalex_id for item in (await storage.papers.list(RecordQuery())).items] == ["W1001"]
        assert await storage.papers.delete("W1001") is True
        assert await storage.papers.read("W1001") is None

    async def test_an_inventor_profile(self, storage: Storage) -> None:
        profile = InventorProfile(name_key="jan kautz", name="Jan Kautz", publications=3, companies=["nvidia"])

        created = await storage.patent_profiles.create(profile)
        assert await storage.patent_profiles.update(profile.model_copy(update={"publications": 4})) is True
        read = await storage.patent_profiles.read("jan kautz")

        assert created.companies == ["nvidia"]
        assert read is not None
        assert read.publications == 4
        assert (await storage.patent_profiles.list(RecordQuery(companies=["nvidia"]))).total == 1
        assert await storage.patent_profiles.delete("jan kautz") is True
        await storage.patent_profiles.create(profile)
        with pytest.raises(StorageWriteError, match="already exists"):
            await storage.patent_profiles.create(profile)


class TestStatistics:
    async def test_the_statistics_of_a_source(self, storage: Storage, make_report: Callable[..., MarketReport]) -> None:
        statistics = MarketStatistics(
            source="Synergy Research Group",
            crawled_at=T0,
            reports=[make_report("2026Q1", [(MarketPlayer.AMAZON, 30.0)])],
        )
        replaced = statistics.model_copy(update={"reports": [make_report("2026Q2", [(MarketPlayer.AMAZON, 29.0)])]})

        assert await storage.statistics.update("synergy", statistics) is None
        await storage.statistics.create("synergy", statistics)
        with pytest.raises(StorageWriteError, match="already stored"):
            await storage.statistics.create("synergy", statistics)
        assert await storage.statistics.update("synergy", replaced) is not None
        read = await storage.statistics.read("synergy")

        assert read is not None
        assert [report.period for report in read.reports] == ["2026Q2"]
        assert [item.source for item in await storage.statistics.list()] == ["Synergy Research Group"]
        assert await storage.statistics.delete("synergy") is True
        assert await storage.statistics.read("synergy") is None
        assert await storage.statistics.delete("synergy") is False


class TestCountedItems:
    async def test_the_trends_and_matrices_reach_the_items(self, storage: Storage) -> None:
        product = CloudProduct(name="Compute", description="VMs", url="https://ovh.example/compute")

        stored = await storage.trends.create(DatasetKind.CATALOGUE, CloudProvider.OVH, product)
        renamed = await storage.matrices.update(
            DatasetKind.CATALOGUE, stored.id, product.model_copy(update={"description": "Virtual machines"})
        )
        read = await storage.trends.read(DatasetKind.CATALOGUE, stored.id)
        page = await storage.matrices.list(DatasetKind.CATALOGUE, ItemQuery())

        assert renamed is not None
        assert read is not None
        assert read.item.description == "Virtual machines"
        assert [item.item.name for item in page.items] == ["Compute"]
        assert await storage.trends.delete(DatasetKind.CATALOGUE, stored.id) is True
        with pytest.raises(StorageWriteError):
            await storage.trends.create(DatasetKind.MARKETPLACE, CloudProvider.OVH, product)
        with pytest.raises(StorageWriteError):
            await storage.trends.create(DatasetKind.STATISTICS, CloudProvider.OVH, product)
        with pytest.raises(StorageReadError):
            await storage.matrices.list(DatasetKind.STATISTICS, ItemQuery())
        assert await storage.trends.read(DatasetKind.STATISTICS, 1) is None
