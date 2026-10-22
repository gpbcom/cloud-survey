from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import JsonValue, SecretStr

from llm.chat_model_factory import ChatModelFactory
from llm.exception import LLMBudgetExceededError, LLMConfigurationFileError
from llm.tasks.taxonomy_prompt import TaxonomyPrompt
from llm.usage_meter import UsageMeter, UsageValue
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.configuration.llm.enums import LLMEffort, LLMProvider, LLMTask
from models.configuration.llm.model.llm_budget_config import LLMBudgetConfig
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.taxonomy.labels.source_label import SourceLabel
from models.taxonomy.nodes.taxonomy import Taxonomy


def configuration(provider: LLMProvider, model: str, **fields: JsonValue) -> LLMConfiguration:
    cfg = LLMConfiguration.model_validate({"provider": provider.value, "model_name": model, **fields})
    return cfg.model_copy(update={"api_key": SecretStr("test-key")})


def taxonomy() -> Taxonomy:
    names: Dict[str, JsonValue] = {"name_ru": "Сеть", "name_zh": "中"}
    return Taxonomy.model_validate(
        {
            "nodes": [
                {"slug": "compute", "name_en": "Compute", "description_en": "Servers.", **names},
                {"slug": "gpu", "parent_slug": "compute", "name_en": "GPU", "description_en": "Cards.", **names},
                {"slug": "old", "parent_slug": "compute", "name_en": "Old", "hidden": True, **names},
                {"slug": "other", "name_en": "Other", "hidden": True, **names},
            ]
        }
    )


class TestChatModelFactory:
    def test_a_current_claude_model_gets_an_effort_and_no_temperature(self) -> None:
        cfg = configuration(LLMProvider.ANTHROPIC, "claude-haiku-5-5", effort="low", temperature=0.3, max_tokens=900)

        model = ChatModelFactory().make(cfg)

        assert isinstance(model, ChatAnthropic)
        assert (model.model, model.max_tokens, model.temperature) == ("claude-haiku-5-5", 900, None)
        assert model.effort == "low"

    def test_an_older_claude_model_gets_a_temperature_and_no_effort(self) -> None:
        cfg = configuration(LLMProvider.ANTHROPIC, "claude-3-5-haiku-latest", effort="low", temperature=0.3)

        model = ChatModelFactory().make(cfg)

        assert isinstance(model, ChatAnthropic)
        assert (model.temperature, model.effort) == (0.3, None)

    def test_an_openai_reasoning_model_gets_a_clamped_effort(self) -> None:
        cfg = configuration(LLMProvider.OPENAI, "gpt-5-mini", effort=LLMEffort.MAX.value)

        model = ChatModelFactory().make(cfg)

        assert isinstance(model, ChatOpenAI)
        assert model.reasoning_effort == "high"
        assert model.disabled_params == {"parallel_tool_calls": None}
        plain = ChatModelFactory().make(configuration(LLMProvider.OPENAI, "gpt-4.1", effort="low"))
        assert isinstance(plain, ChatOpenAI)
        assert plain.reasoning_effort is None

    def test_the_system_prompt_is_cached_on_anthropic_only(self) -> None:
        factory = ChatModelFactory()

        anthropic = factory.system_message(configuration(LLMProvider.ANTHROPIC, "claude-haiku-5-5"), "Rules")
        openai = factory.system_message(configuration(LLMProvider.OPENAI, "gpt-5-mini"), "Rules")

        assert anthropic.content == [{"type": "text", "text": "Rules", "cache_control": {"type": "ephemeral"}}]
        assert openai.content == "Rules"


class TestUsageMeter:
    def test_the_cached_tokens_are_priced_apart(self) -> None:
        cfg = configuration(
            LLMProvider.ANTHROPIC, "claude-sonnet-5-5", input_rate_per_million=2, output_rate_per_million=10
        )
        usage: Dict[str, UsageValue] = {
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "input_token_details": {"cache_read": 500_000, "cache_creation": 100_000},
        }
        meter = UsageMeter(LLMBudgetConfig())

        assert meter.tokens(usage) == (400_000, 100_000, 500_000, 100_000)
        assert meter.cost(cfg, usage) == Decimal("0.8") + Decimal("0.25") + Decimal("0.1") + Decimal("1")
        assert meter.tokens(None) == (0, 0, 0, 0)
        assert meter.cost(cfg, None) == 0

    def test_the_ceiling_stops_the_calls_when_enforced(self) -> None:
        UsageMeter(LLMBudgetConfig(ceiling=Decimal(1))).check(Decimal("0.99"))
        UsageMeter(LLMBudgetConfig(ceiling=Decimal(1), enforce=False)).check(Decimal(5))
        with pytest.raises(LLMBudgetExceededError):
            UsageMeter(LLMBudgetConfig(ceiling=Decimal(1))).check(Decimal(1))


class TestTaxonomyPrompt:
    def test_the_system_prompt_lists_the_visible_nodes(self) -> None:
        system = TaxonomyPrompt().system(LLMTask.ITEM_CLASSIFICATION, taxonomy())

        lines: List[str] = system.splitlines()
        assert "compute: Compute (domain): Servers." in lines
        assert "gpu: Compute > GPU: Cards." in lines
        assert "old:" not in system
        assert "other:" not in system
        assert system != TaxonomyPrompt().system(LLMTask.LABEL_TRANSLATION, taxonomy())

    def test_the_batches_are_json(self) -> None:
        prompt = TaxonomyPrompt()
        label = SourceLabel.model_validate({"id": 7, "text": "Базы данных", "language": "ru"})
        item = MarketplaceSoftware(
            name="Pg",
            description="x" * 900,
            categories=["developer-tool"],
            types=["other"],
            url="https://example.com/pg",
            publisher="ACME",
            delivery=DeliveryMethod.SAAS,
            marketplace_categories=["Базы данных"],
        )

        assert prompt.labels([label], {7: ["selectel"]}) == (
            '{"labels": [{"id": 7, "text": "Базы данных", "providers": ["selectel"]}]}'
        )
        assert '"labels": ["Базы данных"]' in prompt.items([(3, "selectel", item)])
        assert "x" * 601 not in prompt.items([(3, "selectel", item)])

    def test_unreadable_prompts_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(LLMConfigurationFileError):
            TaxonomyPrompt(path=tmp_path / "missing.yaml")
