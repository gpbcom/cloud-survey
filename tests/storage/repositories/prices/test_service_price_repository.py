from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import List, Tuple

import pytest

from models.cloud.enums import CloudProvider, PriceOrigin, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.stored_price import StoredPrice
from models.cloud.products.product import CloudProduct
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDER = CloudProvider.AWS.value
SOURCE = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.csv"


def price(sku: str, amount: str = "0.10", region: str = "us-east-1") -> ServicePrice:
    return ServicePrice(
        provider=CloudProvider.AWS,
        sku_key=sku,
        service="Amazon EC2",
        family="Compute Instance",
        region=region,
        vcpu=Decimal(2),
        memory_gib=Decimal(8),
        attributes={"tenancy": "Shared"},
        unit=PriceUnit.HOUR,
        unit_raw="Hrs",
        price=Decimal(amount),
        currency="USD",
        source_url=SOURCE,
        source_kind=PriceSourceKind.API,
    )


async def crawl(storage: Storage, run: str, prices: List[ServicePrice], complete: bool = True) -> Tuple[int, int]:
    await storage.prices.stage(run, prices)
    return await storage.prices.merge(run, PROVIDER, [SOURCE] if complete else [])


class TestMerge:
    async def test_a_first_crawl_inserts_and_a_second_one_unchanged_writes_nothing(self, storage: Storage) -> None:
        prices = [price("a"), price("b"), price("c")]

        first = await crawl(storage, "run-1", prices)
        second = await crawl(storage, "run-2", [price("a"), price("b"), price("c")])

        assert first == (0, 3)
        assert second == (0, 0)
        assert await storage.prices.count({"provider": [PROVIDER]}) == 3

    async def test_a_changed_price_closes_its_row_and_keeps_the_history(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price("a", "0.10")])

        assert await crawl(storage, "run-2", [price("a", "0.12")]) == (1, 1)

        history = await storage.prices.history(PROVIDER, "a")
        assert [row.price for row in history] == [Decimal("0.10"), Decimal("0.12")]
        assert history[0].valid_to is not None
        assert history[1].valid_to is None

    async def test_a_price_missing_from_a_complete_crawl_is_closed_only_then(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price("a"), price("b")])

        assert await crawl(storage, "run-2", [price("a")], complete=False) == (0, 0)
        assert await crawl(storage, "run-3", [price("a")], complete=True) == (1, 0)
        assert [row.sku_key for row in await storage.prices.list({"provider": [PROVIDER]})] == ["a"]

    async def test_a_price_changed_by_a_person_is_never_replaced_by_a_crawl(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price("a", "0.10")])
        (current,) = await storage.prices.list({"provider": [PROVIDER]})

        revised = await storage.prices.revise(current.model_copy(update={"price": Decimal("0.08")}))
        result = await crawl(storage, "run-2", [price("a", "0.11")])

        (kept,) = await storage.prices.list({"provider": [PROVIDER]})
        assert result == (0, 0)
        assert kept.id == revised.id
        assert kept.price == Decimal("0.08")
        assert kept.origin is PriceOrigin.USER
        assert kept.edited
        assert len(await storage.prices.history(PROVIDER, "a")) == 2

    async def test_the_prices_of_a_source_not_read_again_are_kept(self, storage: Storage) -> None:
        other = price("b").model_copy(update={"source_url": "https://pricing.us-east-1.amazonaws.com/other.csv"})
        await crawl(storage, "run-1", [price("a"), other])

        assert await crawl(storage, "run-2", [price("a")]) == (0, 0)
        assert {row.sku_key for row in await storage.prices.list({"provider": [PROVIDER]})} == {"a", "b"}

    async def test_a_failed_crawl_is_discarded(self, storage: Storage) -> None:
        await storage.prices.stage("run-1", [price("a")])

        assert await storage.prices.discard("run-1") == 1
        assert await storage.prices.merge("run-1", PROVIDER, [SOURCE]) == (0, 0)

    async def test_a_duplicate_in_one_crawl_keeps_the_last_staged(self, storage: Storage) -> None:
        assert await crawl(storage, "run-1", [price("a", "0.10"), price("a", "0.20")]) == (0, 1)
        (row,) = await storage.prices.list({"provider": [PROVIDER]})
        assert row.price == Decimal("0.20")

    async def test_a_duplicate_whose_last_staged_row_is_unchanged_keeps_the_current_row(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price("a", "0.20")])

        assert await crawl(storage, "run-2", [price("a", "0.10"), price("a", "0.20")]) == (0, 0)
        assert [row.price for row in await storage.prices.history(PROVIDER, "a")] == [Decimal("0.20")]


class TestCrudl:
    async def test_create_read_update_delete_and_list(self, storage: Storage) -> None:
        fact = price("manual")
        created = await storage.prices.create(
            StoredPrice(**fact.model_dump(), fingerprint="f", origin=PriceOrigin.USER, edited=True)
        )
        assert created.id is not None
        assert created.valid_from is not None

        read = await storage.prices.read(created.id)
        assert read == created
        assert await storage.prices.update(created.model_copy(update={"price": Decimal("0.5")}))
        changed = await storage.prices.read(created.id)
        assert changed is not None
        assert changed.price == Decimal("0.5")
        assert [row.id for row in await storage.prices.list({"origin": ["user"]})] == [created.id]
        assert await storage.prices.delete(created.id)
        assert await storage.prices.read(created.id) is None

    async def test_close_ends_a_price_but_keeps_it_in_the_history(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price("a")])
        (current,) = await storage.prices.list({"provider": [PROVIDER]})
        assert current.id is not None

        assert await storage.prices.close(current.id)
        assert await storage.prices.list({"provider": [PROVIDER]}) == []
        assert len(await storage.prices.list({"provider": [PROVIDER]}, current=False)) == 1
        assert await crawl(storage, "run-2", [price("a")]) == (0, 0), "a price a person closed stays closed"

    async def test_the_list_is_paged(self, storage: Storage) -> None:
        await crawl(storage, "run-1", [price(f"sku-{index:03d}") for index in range(25)])

        page = await storage.prices.list({"provider": [PROVIDER]}, offset=10, limit=5)

        assert [row.sku_key for row in page] == [f"sku-{index:03d}" for index in range(10, 15)]


class TestLinksAndCoverage:
    async def test_linked_prices_cover_their_product_and_the_others_are_missing(self, storage: Storage) -> None:
        async with storage.catalogues.writer(CloudProvider.AWS, datetime(2026, 10, 1, tzinfo=UTC), 60.0) as writer:
            await writer.add(CloudProduct(name="Amazon EC2", description="VMs", url="https://aws.example/ec2"))
            await writer.add(CloudProduct(name="Amazon S3", description="Objects", url="https://aws.example/s3"))
            await writer.finish()
        await crawl(storage, "run-1", [price("a"), price("b")])
        products = await storage.catalogues.live_pages(CloudProvider.AWS)
        ec2 = next(product for product, (name, _) in products.items() if name == "Amazon EC2")

        assert await storage.prices.unlinked_services(PROVIDER) == [("Amazon EC2", SOURCE, "")]
        assert await storage.prices.link_products(PROVIDER, [("Amazon EC2", SOURCE, "", ec2)]) == 2
        assert await storage.prices.unlinked_services(PROVIDER) == []
        assert await storage.prices.coverage(PROVIDER) == [("Amazon EC2", True, False), ("Amazon S3", False, False)]
        assert await storage.prices.unlink_products(PROVIDER) == 2
        assert len(await storage.prices.unlinked_services(PROVIDER)) == 1

    async def test_no_link_writes_nothing(self, storage: Storage) -> None:
        assert await storage.prices.link_products(PROVIDER, []) == 0
