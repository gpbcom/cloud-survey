from __future__ import annotations

import json
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Type, Union

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, JsonValue
from sqlalchemy import text

from conftest import build_product, seed_catalogue
from llm.chat_model_factory import ChatModelFactory
from llm.exception import LLMBudgetExceededError
from llm.tasks.correspondence.correspondence_prompt import CorrespondencePrompt
from llm.tasks.correspondence.service_matcher import ServiceMatcher
from models.cloud.enums import CloudProvider
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.correspondence.llm.concept_batch import ConceptBatch
from storage.storage import Storage

pytestmark = pytest.mark.db

KEY_VARIABLE = "TEST_LLM_KEY"
USAGE: Dict[str, int] = {"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000}
CATALOGUES: Dict[CloudProvider, List[Tuple[str, str]]] = {
    CloudProvider.AWS: [("EC2", "virtual-machines"), ("EKS", "kubernetes")],
    CloudProvider.AZURE: [("Virtual Machines", "virtual-machines"), ("AKS", "kubernetes")],
    CloudProvider.GCP: [("GKE", "kubernetes"), ("Cloud Run", "serverless")],
}


class FakeFactory(ChatModelFactory):
    """A chat model factory filing the services by name instead of calling a provider."""

    def __init__(self, concepts: Dict[str, str], broken: bool = False, forget: Optional[str] = None) -> None:
        super().__init__()
        self.concepts = concepts
        self.broken = broken
        self.forget = forget
        self.calls: List[Tuple[str, List[str], List[str]]] = []

    def _answer(self, messages: List[BaseMessage]) -> Dict[str, Optional[Union[BaseModel, AIMessage, str]]]:
        payload = json.loads(str(messages[-1].content))
        services = [str(service["name"]) for service in payload["services"]]
        self.calls.append(
            (str(payload["category"]), services, [str(concept["name"]) for concept in payload["concepts"]])
        )
        raw = AIMessage(content="", usage_metadata=USAGE)
        if self.broken:
            return {"raw": raw, "parsed": None, "parsing_error": "not JSON"}
        grouped: Dict[str, List[Dict[str, JsonValue]]] = {}
        for service in payload["services"]:
            if service["name"] != self.forget:
                grouped.setdefault(self.concepts[str(service["name"])], []).append(
                    {"id": service["id"], "confidence": 90}
                )
        known = {str(concept["name"]): concept["concept_id"] for concept in payload["concepts"]}
        answers = [
            {"concept_id": known.get(name), "name": name, "members": members} for name, members in grouped.items()
        ]
        return {"raw": raw, "parsed": ConceptBatch.model_validate({"concepts": answers}), "parsing_error": None}

    def structured[T: BaseModel](self, cfg: LLMConfiguration, schema: Type[T]) -> Runnable:  # type: ignore[type-arg]
        return RunnableLambda(self._answer)


def settings(monkeypatch: pytest.MonkeyPatch, ceiling: int = 10) -> LLMSettings:
    monkeypatch.setenv(KEY_VARIABLE, "secret")
    profile: Dict[str, JsonValue] = {
        "provider": "anthropic",
        "model_name": "claude-sonnet-5-5",
        "api_key": KEY_VARIABLE,
        "input_rate_per_million": 1,
    }
    return LLMSettings.model_validate({"llm": profile, "llm_budget": {"ceiling": ceiling}})


async def file_products(storage: Storage) -> None:
    await storage.seeder.seed()
    for provider, catalogue in CATALOGUES.items():
        await seed_catalogue(storage, provider, [build_product(name) for name, _ in catalogue])
        for name, slug in catalogue:
            async with storage.database.connect() as connection, connection.begin():
                await connection.execute(
                    text("UPDATE products SET service_categories = ARRAY[:slug] WHERE name = :name"),
                    {"slug": slug, "name": name},
                )


async def scalar(storage: Storage, sql: str) -> JsonValue:
    async with storage.database.connect() as connection:
        value: JsonValue = await connection.scalar(text(sql))
        return value


CONCEPTS = {"EC2": "Virtual machines", "Virtual Machines": "Virtual machines", "EKS": "Managed Kubernetes"}
CONCEPTS |= {"AKS": "Managed Kubernetes", "GKE": "Managed Kubernetes"}


class TestServiceMatcher:
    async def test_the_shared_categories_are_matched_once(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await file_products(storage)
        factory = FakeFactory(CONCEPTS)
        matcher = ServiceMatcher(storage, settings(monkeypatch), factory=factory)

        assert await matcher.run() == 5
        assert await matcher.run() == 0

        assert [category for category, _, _ in factory.calls] == [
            "Containers & Kubernetes > Managed Kubernetes",
            "Compute > Virtual machines",
        ]
        assert await scalar(storage, "SELECT string_agg(name, ', ' ORDER BY name) FROM service_concepts") == (
            "Managed Kubernetes, Virtual machines"
        )
        assert await storage.llm_usage.spent("USD") == Decimal(2)

    async def test_a_new_service_joins_the_existing_concepts(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await file_products(storage)
        factory = FakeFactory({**CONCEPTS, "OKE": "Managed Kubernetes"})
        await ServiceMatcher(storage, settings(monkeypatch), factory=factory).run()
        await seed_catalogue(storage, CloudProvider.ORACLE, [build_product("OKE")])
        async with storage.database.connect() as connection, connection.begin():
            await connection.execute(
                text("UPDATE products SET service_categories = ARRAY['kubernetes'] WHERE name = 'OKE'")
            )

        assert await ServiceMatcher(storage, settings(monkeypatch), factory=factory).run(CloudProvider.ORACLE) == 1

        last = factory.calls[-1]
        assert last[1:] == (["OKE"], ["Managed Kubernetes"])
        assert await scalar(storage, "SELECT count(*) FROM service_concepts") == 2

    async def test_failures_and_forgotten_services_are_tried_again(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await file_products(storage)

        assert (
            await ServiceMatcher(storage, settings(monkeypatch), factory=FakeFactory(CONCEPTS, broken=True)).run() == 0
        )
        assert await scalar(storage, "SELECT count(*) FROM correspondence_checks WHERE llm_attempts = 1") == 5
        forgetful = FakeFactory(CONCEPTS, forget="GKE")
        assert await ServiceMatcher(storage, settings(monkeypatch), factory=forgetful).run(limit=1) == 2
        assert await scalar(
            storage,
            "SELECT llm_error FROM correspondence_checks JOIN products ON products.id = product_id WHERE name = 'GKE'",
        ) == ("no answer for the service")

    async def test_nothing_is_sent_without_a_model_or_a_budget(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await file_products(storage)
        factory = FakeFactory(CONCEPTS)

        assert await ServiceMatcher(storage, LLMSettings(), factory=factory).run() == 0
        assert not ServiceMatcher(storage, LLMSettings(), factory=factory).is_configured()
        with pytest.raises(LLMBudgetExceededError):
            await ServiceMatcher(storage, settings(monkeypatch, ceiling=0), factory=factory).run()
        assert factory.calls == []

    async def test_a_locked_category_is_skipped(self, storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
        await file_products(storage)
        factory = FakeFactory(CONCEPTS)

        async with storage.database.connect() as connection:
            assert await storage.correspondences.lock(connection, "kubernetes")
            assert await ServiceMatcher(storage, settings(monkeypatch), factory=factory).run() == 2
            await storage.correspondences.unlock(connection, "kubernetes")

        assert [category for category, _, _ in factory.calls] == ["Compute > Virtual machines"]


def test_the_prompt_sends_the_category_its_concepts_and_its_services() -> None:
    prompt = CorrespondencePrompt()

    assert "service concept" in prompt.system()
    assert "concept_id" in prompt.system()
