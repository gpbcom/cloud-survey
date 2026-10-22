from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Tuple

import pytest
from sqlalchemy import text

from classifier.software_classifier import SoftwareClassifier
from models.cloud.enums import CloudProvider, DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.storage.storage_settings import StorageSettings
from models.storage.enums import DatasetKind, ItemField
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.page import Page
from models.taxonomy.enums import CategorySource, LabelStatus, Language
from storage.exception import StorageWriteError
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDER = CloudProvider.CIVO
T0 = datetime(2026, 1, 1, tzinfo=UTC)
DATABASES = "label_id = (SELECT id FROM source_labels WHERE key = 'database')"


def software(
    name: str, labels: Tuple[str, ...] = (), description: str = "Zz", delivery: DeliveryMethod = DeliveryMethod.SAAS
) -> MarketplaceSoftware:
    return MarketplaceSoftware(
        name=name,
        description=description,
        url=f"https://marketplace.example.com/{name.casefold().replace(' ', '-')}",
        publisher="ACME",
        delivery=delivery,
        categories=["developer-tool"],
        marketplace_categories=list(labels),
    )


async def crawl(storage: Storage, items: List[MarketplaceSoftware], day: int = 0) -> None:
    async with storage.marketplaces.writer(PROVIDER, T0 + timedelta(days=day), 0.0) as writer:
        for item in items:
            await writer.add(item)
        await writer.finish()


async def by_name(storage: Storage) -> Dict[str, MarketplaceSoftware]:
    marketplace = await storage.marketplaces.load(PROVIDER)
    assert marketplace is not None
    return {item.name: item for item in marketplace.software}


async def rows(storage: Storage, sql: str, **parameters: str) -> List[Tuple[str, ...]]:
    async with storage.database.connect() as connection:
        return [tuple(row) for row in (await connection.execute(text(sql), parameters)).all()]


def storage_query(**fields: List[str]) -> ItemQuery:
    return ItemQuery.model_validate(fields)


async def execute(storage: Storage, sql: str) -> None:
    async with storage.database.connect() as connection, connection.begin():
        for statement in sql.split(";"):
            await connection.execute(text(statement))


class TestSeed:
    async def test_the_seed_is_applied_once(self, storage: Storage) -> None:
        assert await storage.seeder.seed()
        assert not await storage.seeder.seed()

        nodes = await rows(storage, "SELECT count(*), count(*) FILTER (WHERE parent_slug IS NULL) FROM taxonomy_nodes")
        taxonomy = await storage.taxonomy.read()
        assert nodes[0][0] == len(taxonomy.nodes) >= 200
        assert nodes[0][1] == len(taxonomy.domains())
        assert taxonomy.is_category("kubernetes")

    async def test_the_seed_keeps_the_edits_and_hides_the_nodes_it_lost(self, storage: Storage) -> None:
        await storage.seeder.seed()
        await execute(storage, "UPDATE taxonomy_nodes SET name_en = 'K8s', edited = true WHERE slug = 'kubernetes'")
        await execute(
            storage,
            "INSERT INTO taxonomy_nodes (slug, parent_slug, name_en, origin) "
            "VALUES ('gone', 'compute', 'Gone', 'seed')",
        )

        assert await storage.seeder.seed(force=True)

        assert await rows(storage, "SELECT name_en FROM taxonomy_nodes WHERE slug = 'kubernetes'") == [("K8s",)]
        assert await rows(storage, "SELECT hidden FROM taxonomy_nodes WHERE slug = 'gone'") == [(True,)]

    async def test_the_revision_follows_the_seeds(self, storage: Storage) -> None:
        await storage.seeder.seed()
        async with storage.database.connect() as connection, connection.begin():
            revision, largest = await storage.taxonomy.revision(connection)
            assert revision is not None
            assert largest == (await rows(storage, "SELECT max(id) FROM source_labels"))[0][0]
            assert await storage.taxonomy.bump(connection) == revision + 1


class TestCrawls:
    async def test_the_labels_are_stored_once_and_file_the_items(self, storage: Storage) -> None:
        await crawl(
            storage,
            [
                software("Acme DB", ("Databases",), "A managed PostgreSQL service"),
                software("Acme Base", ("DataBases", "Базы знаний")),
                software("Acme Other", ("Продукты",)),
            ],
        )

        labels = await rows(
            storage,
            "SELECT key, language, status FROM source_labels "
            "WHERE key IN ('database', 'базызнаний', 'продукты') ORDER BY key",
        )
        assert labels == [
            ("database", Language.ENGLISH.value, LabelStatus.TRANSLATED.value),
            ("базызнаний", Language.RUSSIAN.value, LabelStatus.PENDING.value),
            ("продукты", Language.RUSSIAN.value, LabelStatus.NOISE.value),
        ]
        items = await by_name(storage)
        assert items["Acme DB"].service_categories == ["relational-database"]
        assert items["Acme Base"].service_categories == ["database"]
        assert items["Acme Base"].service_domains == ["databases"]
        assert len(items["Acme Base"].source_label_ids) == 2
        assert items["Acme Other"].service_categories == ["other"]
        assert {item.categories_source for item in items.values()} == {CategorySource.RULES}
        sightings = await rows(storage, "SELECT DISTINCT kind, provider FROM label_sightings")
        assert sightings == [(DatasetKind.MARKETPLACE.value, PROVIDER.value)]

    async def test_a_new_categorization_updates_the_item_without_a_version(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",))])
        await execute(storage, "UPDATE software SET service_categories = '{}'")

        await crawl(storage, [software("Acme", ("Databases",))], day=1)

        assert (await by_name(storage))["Acme"].service_categories == ["database"]
        assert await rows(storage, "SELECT count(*) FROM software_versions") == [(1,)]

    async def test_a_taxonomy_edit_during_a_crawl_recategorizes_its_items(self, storage: Storage) -> None:
        async with storage.marketplaces.writer(PROVIDER, T0, 0.0) as writer:
            await writer.add(software("Acme", ("Databases",)))
            await execute(
                storage,
                f"UPDATE label_links SET excluded = true, source = 'user' WHERE {DATABASES}; "
                "UPDATE taxonomy_state SET revision = revision + 1",
            )
            await writer.finish()

        assert (await by_name(storage))["Acme"].service_categories == ["other"]

    async def test_parallel_crawls_of_a_process_share_the_caches_safely(self, storage: Storage) -> None:
        labels = tuple(f"Label {index}" for index in range(20))

        async def write(provider: CloudProvider) -> None:
            async with storage.marketplaces.writer(provider, T0, 0.0) as writer:
                for index in range(8):
                    await writer.add(software(f"{provider.value} {index}", labels[index:] + labels[:index]))
                await writer.finish()

        async def edit() -> None:
            for _ in range(5):
                await execute(storage, "UPDATE taxonomy_state SET revision = revision + 1")
                storage.categorizer.invalidate()
                await asyncio.sleep(0)

        await asyncio.gather(write(PROVIDER), write(CloudProvider.OVH), write(CloudProvider.SCALEWAY), edit())

        stored = await rows(storage, "SELECT count(*) FROM software WHERE cardinality(source_label_ids) = 20")
        assert stored == [(24,)]
        assert storage.categorizer.registry.resolved, "the cache is kept while it is read again"

    async def test_concurrent_writers_store_each_new_label_once(
        self, storage: Storage, storage_settings: StorageSettings
    ) -> None:
        labels = tuple(f"Label {index}" for index in range(30))
        other = CloudProvider.OVH

        async def write(opened: Storage, provider: CloudProvider) -> None:
            async with opened.marketplaces.writer(provider, T0, 0.0) as writer:
                for index in range(6):
                    await writer.add(software(f"{provider.value} {index}", labels[index:] + labels[:index]))
                await writer.finish()

        async with Storage(storage_settings) as second:
            await asyncio.gather(write(storage, PROVIDER), write(second, other))

        created = "SELECT count(*), count(DISTINCT key) FROM source_labels WHERE key LIKE 'label%'"
        assert await rows(storage, created) == [(30, 30)]
        assert await rows(storage, "SELECT count(DISTINCT provider) FROM label_sightings") == [(2,)]


class TestLinks:
    async def test_aliases_share_their_links(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Базы данных",)), software("Other", ("Databases",))])
        await execute(
            storage,
            "UPDATE source_labels SET name_en = 'Databases', name_key = 'database', status = 'translated' "
            "WHERE key = 'базыданных'; DELETE FROM label_links WHERE label_id = "
            "(SELECT id FROM source_labels WHERE key = 'базыданных'); "
            "UPDATE taxonomy_state SET revision = revision + 1",
        )

        assert await storage.marketplaces.recategorize(PROVIDER) is not None

        assert (await by_name(storage))["Acme"].service_categories == ["database"]

    async def test_a_user_exclusion_survives_the_rules(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",))])
        await execute(
            storage,
            "UPDATE label_links SET excluded = true, source = 'user' WHERE node_slug = 'database'; "
            "UPDATE taxonomy_state SET revision = revision + 1",
        )

        await storage.labels.recompute_rule_links(SoftwareClassifier())
        await storage.marketplaces.recategorize(PROVIDER)

        assert await rows(
            storage,
            f"SELECT source, excluded FROM label_links WHERE {DATABASES}",
        ) == [("user", True)]
        assert (await by_name(storage))["Acme"].service_categories == ["other"]

    async def test_the_rule_recompute_is_idempotent_beside_the_seed(self, storage: Storage) -> None:
        await storage.seeder.seed()

        assert await storage.labels.recompute_rule_links(SoftwareClassifier()) == 0
        seeded = await rows(storage, "SELECT DISTINCT source FROM label_links ORDER BY source")
        assert seeded == [("rule",), ("seed",)]

    async def test_a_rule_recompute_relinks_the_labels(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",))])
        await execute(storage, f"DELETE FROM label_links WHERE {DATABASES}")

        assert await storage.labels.recompute_rule_links(SoftwareClassifier()) == 1
        assert await storage.labels.recompute_rule_links(SoftwareClassifier()) == 0
        assert await rows(
            storage,
            f"SELECT node_slug, source FROM label_links WHERE {DATABASES}",
        ) == [("database", "rule")]


class TestPinnedAndLlm:
    async def test_categories_set_by_hand_are_pinned(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",))])
        item_id = (await storage.marketplaces.item_ids(storage_query(), 0, 10))[0]

        assert await storage.marketplaces.update_many([item_id], {ItemField.SERVICE_CATEGORIES: ["crm", "erp"]}) == 1
        await crawl(storage, [software("Acme", ("Databases",), "Changed")], day=1)
        await storage.marketplaces.recategorize(PROVIDER)

        item = (await by_name(storage))["Acme"]
        assert (item.service_categories, item.categories_source) == (["erp", "crm"], CategorySource.USER)
        assert item.service_domains == ["business-applications", "sales-marketing"]

    async def test_a_language_model_result_is_kept_until_the_content_changes(self, storage: Storage) -> None:
        await crawl(storage, [software("Zorblax", description="Zorblax")])
        await execute(
            storage,
            "UPDATE software SET service_categories = '{crm}', service_domains = '{sales-marketing}', "
            "categories_source = 'llm', categories_fingerprint = fingerprint",
        )

        await crawl(storage, [software("Zorblax", description="Zorblax")], day=1)
        await storage.marketplaces.recategorize(PROVIDER)
        assert (await by_name(storage))["Zorblax"].service_categories == ["crm"]

        await crawl(storage, [software("Zorblax", description="Zorblax again")], day=2)
        assert (await by_name(storage))["Zorblax"].service_categories == ["other"]


class TestQueries:
    async def test_the_items_are_filtered_and_counted_by_taxonomy_node(self, storage: Storage) -> None:
        await crawl(
            storage,
            [
                software("Acme DB", ("Databases",)),
                software("Acme CRM", ("CRM",)),
                software("Acme Mix", ("Databases", "CRM")),
            ],
        )

        def names(page: Page[MarketplaceSoftware]) -> List[str]:
            return sorted(stored.item.name for stored in page.items)

        assert names(await storage.marketplaces.list(storage_query(service_categories=["database"]))) == [
            "Acme DB",
            "Acme Mix",
        ]
        assert names(await storage.marketplaces.list(storage_query(service_categories=["sales-marketing"]))) == [
            "Acme CRM",
            "Acme Mix",
        ]
        counts = await storage.marketplaces.category_counts(storage_query(service_categories=["crm"]))
        assert (counts["database"], counts["databases"], counts["crm"]) == (2, 2, 2)

    async def test_the_labels_are_filtered_and_counted_with_their_aliases(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Базы данных",)), software("Other", ("DataBases",))])
        await execute(storage, "UPDATE source_labels SET name_en = 'Databases', name_key = 'database'")
        english = await rows(storage, "SELECT id FROM source_labels WHERE key = 'database'")

        page = await storage.marketplaces.list(storage_query(source_labels=[english[0][0]]))
        counts = await storage.marketplaces.label_counts(storage_query())

        assert sorted(stored.item.name for stored in page.items) == ["Acme", "Other"]
        assert [(count.name, count.count) for count in counts] == [("Databases", 2)]


class TestManagerEdits:
    async def test_the_labels_are_detailed_with_their_links_sightings_and_items(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",)), software("Other", ("Databases", "Базы знаний"))])

        details = {label.text: label for label in await storage.labels.details()}

        assert details["Databases"].links == ["database"]
        assert details["Databases"].providers == [f"marketplace:{PROVIDER.value}"]
        assert details["Databases"].items == 2
        assert details["Базы знаний"].status is LabelStatus.PENDING
        assert details["Базы знаний"].items == 1

    async def test_a_label_named_by_hand_joins_the_aliases_of_its_name(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Базы знаний",))])
        label_id = (await rows(storage, "SELECT id FROM source_labels WHERE key = 'базызнаний'"))[0][0]

        affected = await storage.labels.set_name(int(label_id), "Knowledge bases")
        assert int(label_id) in affected
        assert await storage.recategorize(label_ids=affected) == 1

        assert (await by_name(storage))["Acme"].service_categories == ["knowledge-management"]
        assert await rows(storage, f"SELECT status, name_source FROM source_labels WHERE id = {label_id}") == [
            ("reviewed", "user")
        ]

    async def test_links_exclusions_noise_and_merges_by_hand(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",)), software("Zeta", ("Zz label",))])
        ids = {str(key): int(label_id) for key, label_id in await rows(storage, "SELECT key, id FROM source_labels")}
        database, other = int(ids["database"]), int(ids["zzlabel"])

        await storage.recategorize(label_ids=await storage.labels.link(other, "crm"))
        assert (await by_name(storage))["Zeta"].service_categories == ["crm"]

        await storage.recategorize(label_ids=await storage.labels.unlink(other, "crm"))
        assert (await by_name(storage))["Zeta"].service_categories == ["other"]

        await storage.recategorize(label_ids=await storage.labels.merge(other, database))
        assert (await by_name(storage))["Zeta"].service_categories == ["database"]

        await storage.recategorize(label_ids=await storage.labels.unmerge(other))
        assert (await by_name(storage))["Zeta"].service_categories == ["other"]

        await storage.recategorize(label_ids=await storage.labels.set_status([database], LabelStatus.NOISE))
        assert (await by_name(storage))["Acme"].service_categories == ["other"]

    async def test_a_label_cannot_be_merged_into_itself(self, storage: Storage) -> None:
        with pytest.raises(StorageWriteError, match="merged into itself"):
            await storage.labels.merge(1, 1)

    async def test_the_taxonomy_is_edited_by_hand(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",))])

        slug = await storage.taxonomy.add_node("Ledger databases", "databases", description_en="Immutable ledgers.")
        assert slug == "ledger-databases"
        assert await storage.taxonomy.add_node("Ledger databases!", "databases") == "ledger-databases-2"
        with pytest.raises(StorageWriteError, match="duplicate key"):
            await storage.taxonomy.add_node("ledger DATABASES", "databases")
        with pytest.raises(StorageWriteError, match="under a domain"):
            await storage.taxonomy.add_node("Nested", "database")
        await storage.taxonomy.update_node(slug, "Ledger DBs", "Реестровые СУБД", "账本数据库", "Ledgers.")
        await storage.taxonomy.set_hidden("ledger-databases-2", True)
        moved = await storage.taxonomy.move_node(slug, "data-analytics")
        taxonomy = await storage.taxonomy.read()

        assert taxonomy.domain_of(slug) == "data-analytics"
        ledger, copy = taxonomy.node(slug), taxonomy.node("ledger-databases-2")
        assert ledger is not None
        assert copy is not None
        assert (ledger.name_ru, ledger.edited, copy.hidden) == ("Реестровые СУБД", True, True)
        assert moved == [slug]

        merged = await storage.taxonomy.merge_node("database", "relational-database")
        await storage.recategorize(node_slugs=merged)

        assert (await by_name(storage))["Acme"].service_categories == ["relational-database"]
        database = (await storage.taxonomy.read()).node("database")
        assert database is not None
        assert database.hidden

    async def test_the_unclassified_items_are_counted_per_provider(self, storage: Storage) -> None:
        await crawl(storage, [software("Acme", ("Databases",)), software("Zeta"), software("Omega")])

        (count,) = await storage.marketplaces.unclassified()

        assert (count.provider, count.total, count.unclassified) == (PROVIDER, 3, 2)
        assert round(count.share()) == 67
        assert await storage.catalogues.unclassified() == []
