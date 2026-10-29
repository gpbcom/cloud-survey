from __future__ import annotations

from decimal import Decimal

import pytest

from models.cloud.enums import CloudProvider, FreeTierKind, PriceOrigin, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.profiles.price_quote import PriceQuote
from models.cloud.prices.profiles.usage_item import UsageItem
from models.cloud.prices.profiles.usage_profile import UsageProfile
from models.cloud.prices.stored.price_source import PriceSource
from storage.storage import Storage

pytestmark = pytest.mark.db

AZURE = CloudProvider.AZURE.value
FREE_PAGE = "https://azure.microsoft.com/en-us/pricing/free-services"


def tier(key: str, quantity: str = "1000000") -> FreeTier:
    return FreeTier(
        provider=CloudProvider.AZURE,
        free_key=key,
        service="Azure Functions",
        kind=FreeTierKind.ALWAYS_FREE,
        quantity=Decimal(quantity),
        unit=PriceUnit.REQUEST,
        period="month",
        source_url=FREE_PAGE,
        source_kind=PriceSourceKind.PAGE,
    )


def profile(name: str = "Web app") -> UsageProfile:
    return UsageProfile(
        name=name,
        description="Two web servers and their storage.",
        items=[
            UsageItem(
                label="Web servers",
                family="Compute Instance",
                unit=PriceUnit.HOUR,
                quantity=Decimal(1460),
                minimums={"vcpu": Decimal(2), "memory_gib": Decimal(8)},
            )
        ],
    )


class TestFreeTiers:
    async def test_a_crawl_merges_and_a_person_revises(self, storage: Storage) -> None:
        await storage.free_tiers.stage("run-1", [tier("functions")])
        assert await storage.free_tiers.merge("run-1", AZURE, [FREE_PAGE]) == (0, 1)
        await storage.free_tiers.stage("run-2", [tier("functions", "2000000")])
        assert await storage.free_tiers.merge("run-2", AZURE, [FREE_PAGE]) == (1, 1)
        (current,) = await storage.free_tiers.list({"provider": [AZURE]})

        revised = await storage.free_tiers.revise(current.model_copy(update={"quantity": Decimal(5)}))

        assert revised.origin is PriceOrigin.USER
        assert len(await storage.free_tiers.list({"provider": [AZURE]}, current=False)) == 3
        assert revised.id is not None
        assert await storage.free_tiers.update(revised.model_copy(update={"conditions": "New accounts."}))
        read = await storage.free_tiers.read(revised.id)
        assert read is not None
        assert read.conditions == "New accounts."
        assert await storage.free_tiers.close(revised.id)
        assert await storage.free_tiers.delete(revised.id)
        assert await storage.free_tiers.read(revised.id) is None


class TestPriceSources:
    async def test_crudl_and_upsert(self, storage: Storage) -> None:
        source = PriceSource(provider=CloudProvider.AWS, source_key="AmazonEC2/us-east-1", version="v1", rows=10)

        created = await storage.price_sources.create(source)
        assert created.fetched_at is not None
        assert (
            await storage.price_sources.upsert(
                [source.model_copy(update={"version": "v2", "status": PriceSourceStatus.UNCHANGED})]
            )
            == 1
        )
        read = await storage.price_sources.read("amazon-web-services", "AmazonEC2/us-east-1")
        assert read is not None
        assert read.version == "v2"
        assert read.status is PriceSourceStatus.UNCHANGED
        assert await storage.price_sources.update(read.model_copy(update={"rows": 11}))
        assert list(await storage.price_sources.versions("amazon-web-services")) == ["AmazonEC2/us-east-1"]
        assert len(await storage.price_sources.list()) == 1
        assert await storage.price_sources.delete("amazon-web-services", "AmazonEC2/us-east-1")
        assert await storage.price_sources.read("amazon-web-services", "AmazonEC2/us-east-1") is None


class TestUsageProfilesAndQuotes:
    async def test_crudl_of_a_profile_and_its_quotes(self, storage: Storage) -> None:
        created = await storage.usage_profiles.create(profile())
        assert created.items[0].minimums == {"vcpu": Decimal(2), "memory_gib": Decimal(8)}
        quote = PriceQuote(
            profile="Web app",
            provider=CloudProvider.GCP,
            region="europe-west1",
            currency="EUR",
            monthly_total=Decimal("182.50"),
            breakdown=[{"label": "Web servers", "cost": "182.50"}],
        )

        stored = await storage.price_quotes.create(quote)
        assert stored.computed_at is not None
        assert await storage.price_quotes.update(quote.model_copy(update={"monthly_total": Decimal(190)}))
        read = await storage.price_quotes.read("Web app", "google-cloud-platform", "europe-west1", "default")
        assert read is not None
        assert read.monthly_total == Decimal(190)
        assert len(await storage.price_quotes.list(["Web app"])) == 1
        assert await storage.usage_profiles.update(created.model_copy(update={"description": "Changed."}))
        assert [item.name for item in await storage.usage_profiles.list()] == ["Web app"]
        assert await storage.usage_profiles.delete("Web app")
        assert await storage.price_quotes.list(["Web app"]) == [], "the quotes go with their profile"
        assert await storage.usage_profiles.read("Web app") is None

    async def test_the_quotes_are_cleared(self, storage: Storage) -> None:
        await storage.usage_profiles.create(profile())
        await storage.price_quotes.create(
            PriceQuote(profile="Web app", provider=CloudProvider.AWS, region="us-east-1", currency="USD")
        )

        assert await storage.price_quotes.clear() == 1
        assert await storage.price_quotes.delete("Web app", "amazon-web-services", "us-east-1", "default") is False
