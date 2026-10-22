from __future__ import annotations

from typing import Dict, List, Tuple

import pytest
from pydantic import JsonValue
from sqlalchemy import text

from conftest import build_product, seed_catalogue
from models.cloud.enums import CloudProvider
from models.correspondence.enums import (
    CardinalityClass,
    ConceptSource,
    CoverageFilter,
    MatchStrength,
    MemberRole,
    ViewMode,
)
from models.correspondence.llm.concept_answer import ConceptAnswer
from models.correspondence.query.correspondence_query import CorrespondenceQuery
from storage.storage import Storage

pytestmark = pytest.mark.db

AWS, AZURE, GCP = CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP
COLUMNS = [AWS, AZURE, GCP]
CATALOGUES: Dict[CloudProvider, List[Tuple[str, str, str]]] = {
    AWS: [
        ("EC2", "virtual-machines", "compute"),
        ("EKS", "kubernetes", "containers-kubernetes"),
        ("S3", "object-storage", "storage-services"),
    ],
    AZURE: [("Virtual Machines", "virtual-machines", "compute"), ("AKS", "kubernetes", "containers-kubernetes")],
    GCP: [
        ("Compute Engine", "virtual-machines", "compute"),
        ("GKE", "kubernetes", "containers-kubernetes"),
        ("Cloud Run", "serverless", "compute"),
    ],
}


async def execute(storage: Storage, sql: str, **parameters: str) -> None:
    async with storage.database.connect() as connection, connection.begin():
        await connection.execute(text(sql), parameters)


async def ids(storage: Storage) -> Dict[str, int]:
    async with storage.database.connect() as connection:
        return {
            str(name): int(row_id)
            for row_id, name in (await connection.execute(text("SELECT id, name FROM products"))).all()
        }


async def scalar(storage: Storage, sql: str) -> JsonValue:
    async with storage.database.connect() as connection:
        value: JsonValue = await connection.scalar(text(sql))
        return value


def answer(name: str, *members: Tuple[int, str, int], concept_id: int = 0) -> ConceptAnswer:
    return ConceptAnswer.model_validate(
        {
            "concept_id": concept_id or None,
            "name": name,
            "members": [{"id": member, "role": role, "confidence": confidence} for member, role, confidence in members],
        }
    )


@pytest.fixture
async def products(storage: Storage) -> Dict[str, int]:
    await storage.seeder.seed()
    for provider, catalogue in CATALOGUES.items():
        await seed_catalogue(storage, provider, [build_product(name) for name, _, _ in catalogue])
        for name, slug, domain in catalogue:
            await execute(
                storage,
                "UPDATE products SET service_categories = ARRAY[:slug], service_domains = ARRAY[:domain] "
                "WHERE name = :name",
                slug=slug,
                domain=domain,
                name=name,
            )
    return await ids(storage)


async def match_kubernetes(storage: Storage, products: Dict[str, int]) -> None:
    sent = [products["EKS"], products["AKS"], products["GKE"]]
    kubernetes = answer(
        "Managed Kubernetes",
        (products["EKS"], "equivalent", 95),
        (products["AKS"], "equivalent", 90),
        (products["GKE"], "partial", 60),
        (99999, "equivalent", 90),
    )
    assert await storage.correspondences.apply_answer("kubernetes", [kubernetes], sent) == 3


async def match_machines(storage: Storage, products: Dict[str, int]) -> None:
    machines = [products["EC2"], products["Virtual Machines"], products["Compute Engine"]]
    vms = answer("Virtual machines", *((member, "equivalent", 90) for member in machines))
    assert await storage.correspondences.apply_answer("virtual-machines", [vms], machines) == 3


class TestMatching:
    async def test_the_categories_of_two_providers_are_pending(
        self, storage: Storage, products: Dict[str, int]
    ) -> None:
        repository = storage.correspondences

        assert await repository.pending_buckets() == ["kubernetes", "virtual-machines"]
        assert await repository.pending_buckets(AZURE) == ["kubernetes", "virtual-machines"]
        bucket = await repository.bucket("kubernetes", 60)
        assert [service.name for service in bucket.pending] == ["EKS", "GKE", "AKS"]
        assert bucket.concepts == []

    async def test_an_answer_files_the_services_and_checks_them(
        self, storage: Storage, products: Dict[str, int]
    ) -> None:
        await match_kubernetes(storage, products)
        repository = storage.correspondences

        assert await repository.pending_buckets() == ["virtual-machines"]
        bucket = await repository.bucket("kubernetes", 60)
        assert bucket.pending == []
        (concept,) = bucket.concepts
        assert concept.name == "Managed Kubernetes"
        assert [member.name for member in concept.members] == ["EKS", "GKE", "AKS"]
        assert concept.members_of(GCP)[0].role is MemberRole.PARTIAL

    async def test_a_changed_service_is_matched_again_with_the_existing_concepts(
        self, storage: Storage, products: Dict[str, int]
    ) -> None:
        await match_kubernetes(storage, products)
        await execute(storage, "UPDATE products SET fingerprint = 'changed' WHERE name = 'AKS'")
        repository = storage.correspondences

        bucket = await repository.bucket("kubernetes", 60)
        assert [service.name for service in bucket.pending] == ["AKS"]
        concept_id = bucket.concepts[0].id
        again = answer("Kubernetes", (products["AKS"], "equivalent", 80), concept_id=concept_id)
        assert await repository.apply_answer("kubernetes", [again], [products["AKS"]]) == 0
        assert await scalar(storage, "SELECT count(*) FROM service_concepts") == 1

    async def test_a_removed_service_is_never_filed_again(self, storage: Storage, products: Dict[str, int]) -> None:
        await match_kubernetes(storage, products)
        repository = storage.correspondences
        concept_id = (await repository.bucket("kubernetes", 60)).concepts[0].id

        await repository.unlink(concept_id, products["AKS"])
        await repository.invalidate("kubernetes")
        await match_kubernetes_again(storage, products, concept_id)

        concept = await repository.concept(concept_id)
        assert concept is not None
        assert [member.name for member in concept.members] == ["EKS", "GKE"]
        await repository.link(concept_id, products["AKS"], MemberRole.PARTIAL)
        concept = await repository.concept(concept_id)
        assert concept is not None
        assert concept.members_of(AZURE)[0].source is ConceptSource.USER

    async def test_failed_attempts_stop_after_three(self, storage: Storage, products: Dict[str, int]) -> None:
        repository = storage.correspondences
        sent = [products["EKS"], products["AKS"], products["GKE"]]

        for _ in range(3):
            assert "kubernetes" in await repository.pending_buckets()
            await repository.release("kubernetes", sent, "timeout")

        assert await repository.pending_buckets() == ["virtual-machines"]
        assert await scalar(storage, "SELECT max(llm_error) FROM correspondence_checks") == "timeout"

    async def test_a_category_is_locked_by_one_run_at_a_time(self, storage: Storage, products: Dict[str, int]) -> None:
        repository = storage.correspondences
        async with storage.database.connect() as first, storage.database.connect() as second:
            assert await repository.lock(first, "kubernetes")
            assert not await repository.lock(second, "kubernetes")
            assert await repository.lock(second, "virtual-machines")
            await repository.unlock(first, "kubernetes")
            assert await repository.lock(second, "kubernetes")


async def match_kubernetes_again(storage: Storage, products: Dict[str, int], concept_id: int) -> None:
    sent = [products["EKS"], products["AKS"], products["GKE"]]
    again = answer("Managed Kubernetes", *((member, "equivalent", 90) for member in sent), concept_id=concept_id)
    assert await storage.correspondences.apply_answer("kubernetes", [again], sent) == 0


class TestReading:
    async def test_the_concepts_of_the_columns_are_filtered(self, storage: Storage, products: Dict[str, int]) -> None:
        await match_kubernetes(storage, products)
        await match_machines(storage, products)
        repository = storage.correspondences

        def query(**fields: JsonValue) -> CorrespondenceQuery:
            return CorrespondenceQuery.model_validate({"columns": COLUMNS, **fields})

        assert [concept.name for concept in await repository.rows(query())] == [
            "Managed Kubernetes",
            "Virtual machines",
        ]
        equivalent = await repository.rows(query(strength=MatchStrength.EQUIVALENT, coverage=CoverageFilter.COMPLETE))
        assert [concept.name for concept in equivalent] == ["Virtual machines"]
        assert [concept.name for concept in await repository.rows(query(min_confidence=70, coverage="gaps"))] == [
            "Managed Kubernetes"
        ]
        assert [concept.name for concept in await repository.rows(query(search="gke"))] == ["Managed Kubernetes"]
        assert [concept.name for concept in await repository.rows(query(service_categories=["compute"]))] == [
            "Virtual machines"
        ]
        assert await repository.rows(query(sources=["user"])) == []
        assert await repository.rows(query(cardinalities=["2:1"])) == []
        assert await repository.classes(query()) == {CardinalityClass.ONE_TO_ONE: 2}

    async def test_the_figures_and_the_coverage_are_counted(self, storage: Storage, products: Dict[str, int]) -> None:
        await match_kubernetes(storage, products)
        repository = storage.correspondences

        stats = await repository.stats(CorrespondenceQuery(columns=[AWS, AZURE]))
        cells = {(cell.source, cell.target): (cell.matched, cell.total) for cell in await repository.coverage(COLUMNS)}

        assert (stats.concepts, stats.matched, stats.services, stats.pending) == (1, 2, 5, 2)
        assert stats.last_checked is not None
        assert round(stats.coverage()) == 40
        assert cells[(AWS, AZURE)] == (1, 3)
        assert cells[(GCP, AWS)] == (1, 3)
        assert len(cells) == 6


class TestEditing:
    async def test_concepts_are_created_renamed_merged_and_deleted(
        self, storage: Storage, products: Dict[str, int]
    ) -> None:
        await match_kubernetes(storage, products)
        repository = storage.correspondences
        kubernetes = (await repository.bucket("kubernetes", 60)).concepts[0].id

        created = await repository.create("Container clusters", "kubernetes", [products["EKS"], products["Cloud Run"]])
        await repository.rename(created, "Container platforms", "Clusters and runtimes")
        await repository.merge(kubernetes, created)

        merged = await repository.concept(kubernetes)
        assert merged is not None
        assert merged.edited
        assert sorted(member.name for member in merged.members) == ["AKS", "Cloud Run", "EKS", "GKE"]
        assert await repository.concept(created) is None
        assert [service.name for service in await repository.services("kubernetes")] == ["EKS", "GKE", "AKS"]
        await repository.delete(kubernetes)
        assert await scalar(storage, "SELECT count(*) FROM concept_members") == 0


class TestCategories:
    async def test_the_categories_align_the_services_without_the_ai(
        self, storage: Storage, products: Dict[str, int]
    ) -> None:
        repository = storage.correspondences
        query = CorrespondenceQuery(columns=COLUMNS, mode=ViewMode.CATEGORIES)

        rows = await repository.rows(query)
        stats = await repository.stats(query)
        cells = {
            (cell.source, cell.target): (cell.matched, cell.total)
            for cell in await repository.coverage(COLUMNS, ViewMode.CATEGORIES)
        }

        assert [row.name for row in rows] == [
            "Managed Kubernetes",
            "Object storage",
            "Serverless functions",
            "Virtual machines",
        ]
        assert [member.name for member in rows[0].members] == ["EKS", "GKE", "AKS"]
        assert (stats.concepts, stats.matched, stats.services, stats.stored) == (4, 6, 8, 0)
        assert cells[(AWS, AZURE)] == (2, 3)
        assert cells[(GCP, AZURE)] == (2, 3)
        unique = await repository.rows(query.model_copy(update={"coverage": CoverageFilter.UNIQUE}))
        assert [row.name for row in unique] == ["Object storage", "Serverless functions"]
