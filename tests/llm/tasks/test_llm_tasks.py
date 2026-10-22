from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Type, Union

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, JsonValue
from sqlalchemy import text

from llm.chat_model_factory import ChatModelFactory
from llm.exception import LLMBudgetExceededError
from llm.tasks.item_classifier import ItemClassifier
from llm.tasks.label_translator import LabelTranslator
from models.cloud.enums import CloudProvider, DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.taxonomy.enums import CategorySource
from models.taxonomy.llm.categorization_batch import CategorizationBatch
from models.taxonomy.llm.translation_batch import TranslationBatch
from storage.storage import Storage

pytestmark = pytest.mark.db

PROVIDER = CloudProvider.SELECTEL
T0 = datetime(2026, 1, 1, tzinfo=UTC)
KEY_VARIABLE = "TEST_LLM_KEY"
USAGE: Dict[str, int] = {"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000}


class FakeFactory(ChatModelFactory):
    """A chat model factory answering from tables instead of calling a provider."""

    def __init__(
        self,
        names: Optional[Dict[str, Tuple[str, List[str]]]] = None,
        slugs: Optional[Dict[str, List[str]]] = None,
        broken: bool = False,
    ) -> None:
        super().__init__()
        self.names = names or {}
        self.slugs = slugs or {}
        self.broken = broken
        self.calls: List[Dict[str, List[Dict[str, JsonValue]]]] = []

    def _answer(self, messages: List[BaseMessage]) -> Dict[str, Optional[Union[BaseModel, AIMessage, str]]]:
        payload = json.loads(str(messages[-1].content))
        self.calls.append(payload)
        raw = AIMessage(content="", usage_metadata=USAGE)
        if self.broken:
            return {"raw": raw, "parsed": None, "parsing_error": "not JSON"}
        if "labels" in payload:
            answers = [
                {
                    "id": label["id"],
                    "english": self.names[str(label["text"])][0],
                    "slugs": self.names[str(label["text"])][1],
                }
                for label in payload["labels"]
                if str(label["text"]) in self.names
            ]
            return {"raw": raw, "parsed": TranslationBatch.model_validate({"labels": answers}), "parsing_error": None}
        items = [
            {"id": item["id"], "slugs": self.slugs[str(item["name"])]}
            for item in payload["items"]
            if str(item["name"]) in self.slugs
        ]
        return {"raw": raw, "parsed": CategorizationBatch.model_validate({"items": items}), "parsing_error": None}

    def structured[T: BaseModel](self, cfg: LLMConfiguration, schema: Type[T]) -> Runnable:  # type: ignore[type-arg]
        return RunnableLambda(self._answer)


def settings(monkeypatch: pytest.MonkeyPatch, ceiling: int = 10) -> LLMSettings:
    monkeypatch.setenv(KEY_VARIABLE, "secret")
    profile: Dict[str, JsonValue] = {
        "provider": "anthropic",
        "model_name": "claude-haiku-5-5",
        "api_key": KEY_VARIABLE,
        "input_rate_per_million": 1,
        "output_rate_per_million": 5,
    }
    return LLMSettings.model_validate({"llm": profile, "batch_size": 2, "llm_budget": {"ceiling": ceiling}})


def software(name: str, labels: Tuple[str, ...] = ()) -> MarketplaceSoftware:
    return MarketplaceSoftware(
        name=name,
        description="Zz",
        url=f"https://marketplace.example.com/{name.casefold().replace(' ', '-')}",
        publisher="ACME",
        delivery=DeliveryMethod.SAAS,
        categories=["developer-tool"],
        types=["other"],
        marketplace_categories=list(labels),
    )


async def crawl(storage: Storage, items: List[MarketplaceSoftware]) -> None:
    await storage.seeder.seed()
    async with storage.marketplaces.writer(PROVIDER, T0, 0.0) as writer:
        for item in items:
            await writer.add(item)
        await writer.finish()


async def categories(storage: Storage) -> Dict[str, Tuple[List[str], Optional[CategorySource]]]:
    marketplace = await storage.marketplaces.load(PROVIDER)
    assert marketplace is not None
    return {item.name: (item.service_categories, item.categories_source) for item in marketplace.software}


async def scalar(storage: Storage, sql: str) -> JsonValue:
    async with storage.database.connect() as connection:
        value: JsonValue = await connection.scalar(text(sql))
        return value


class TestLabelTranslator:
    LABELS: Tuple[str, ...] = ("Квантовые симуляторы", "Площадки для турниров", "Ящик")

    async def test_the_pending_labels_are_translated_and_their_items_categorized(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await crawl(storage, [software("Qsim", self.LABELS[:1]), software("Arena", self.LABELS[1:])])
        factory = FakeFactory(
            names={
                self.LABELS[0]: ("Quantum simulators", ["quantum", "unknown-slug"]),
                self.LABELS[1]: ("Tournament platforms", ["gaming"]),
            }
        )

        translated = await LabelTranslator(storage, settings(monkeypatch), factory=factory).run()

        assert translated == 2
        assert len(factory.calls) == 4
        stored = await categories(storage)
        assert stored["Qsim"][0] == ["quantum"]
        assert "gaming" in stored["Arena"][0]
        assert await scalar(storage, "SELECT name_en FROM source_labels WHERE text = 'Квантовые симуляторы'") == (
            "Quantum simulators"
        )
        assert (
            await scalar(storage, "SELECT string_agg(node_slug, ',') FROM label_links WHERE source = 'llm'") == "gaming"
        )
        assert await scalar(storage, "SELECT llm_attempts FROM source_labels WHERE text = 'Ящик'") == 3
        assert await storage.llm_usage.spent("USD") == Decimal(4)

    async def test_a_broken_answer_releases_the_labels(self, storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
        await crawl(storage, [software("Qsim", self.LABELS[:1])])

        assert await LabelTranslator(storage, settings(monkeypatch), factory=FakeFactory(broken=True)).run(limit=1) == 0

        assert (
            await scalar(storage, "SELECT status FROM source_labels WHERE text = 'Квантовые симуляторы'") == "pending"
        )
        assert "unexpected answer" in str(
            await scalar(storage, "SELECT llm_error FROM source_labels WHERE llm_error IS NOT NULL")
        )

    async def test_nothing_is_sent_without_a_model_or_a_budget(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await crawl(storage, [software("Qsim", self.LABELS[:1])])
        factory = FakeFactory()

        assert await LabelTranslator(storage, LLMSettings(), factory=factory).run() == 0
        with pytest.raises(LLMBudgetExceededError):
            await LabelTranslator(storage, settings(monkeypatch, ceiling=0), factory=factory).run()
        assert factory.calls == []

    async def test_concurrent_claims_never_share_a_label(self, storage: Storage) -> None:
        await crawl(storage, [software("Qsim", self.LABELS)])

        first, second = await asyncio.gather(storage.labels.claim_pending(2), storage.labels.claim_pending(2))

        assert len(first) + len(second) == 3
        assert not {label.id for label in first} & {label.id for label in second}
        assert await storage.labels.claim_pending(2) == []


class TestItemClassifier:
    async def test_the_unclassified_items_are_filed_once(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await crawl(storage, [software("Zorg"), software("Blip"), software("Nada")])
        assert {name: slugs for name, (slugs, _) in (await categories(storage)).items()} == {
            "Zorg": ["other"],
            "Blip": ["other"],
            "Nada": ["other"],
        }
        factory = FakeFactory(slugs={"Zorg": ["gpu", "nowhere", "compute"], "Blip": ["other"]})

        assert await ItemClassifier(storage, settings(monkeypatch), factory=factory).run(provider=PROVIDER) == 1

        stored = await categories(storage)
        assert stored["Zorg"] == (["gpu"], CategorySource.LLM)
        assert stored["Blip"][0] == ["other"]
        assert len(factory.calls) == 2
        assert await ItemClassifier(storage, settings(monkeypatch), factory=factory).run(limit=1) == 0

    async def test_the_answer_is_kept_until_the_content_changes(
        self, storage: Storage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await crawl(storage, [software("Zorg")])
        await ItemClassifier(storage, settings(monkeypatch), factory=FakeFactory(slugs={"Zorg": ["gpu"]})).run()

        await storage.recategorize()
        kept = await categories(storage)
        changed = software("Zorg").model_copy(update={"description": "Another description"})
        await crawl(storage, [changed])

        assert kept["Zorg"] == (["gpu"], CategorySource.LLM)
        assert (await categories(storage))["Zorg"][0] == ["other"]
