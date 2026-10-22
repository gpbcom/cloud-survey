from __future__ import annotations

from decimal import Decimal
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.configuration.llm.enums import LLMEffort, LLMProvider, LLMTask
from models.configuration.llm.exception import EmptyLLMRoutingError, UnknownLLMProfileError
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.configuration.llm.routing.llm_routing_config import LLMRoutingConfig

KEY_VARIABLE = "TEST_LLM_KEY"


def profile(model: str, **fields: JsonValue) -> Dict[str, JsonValue]:
    return {"provider": "anthropic", "model_name": model, "api_key": KEY_VARIABLE, **fields}


def test_the_key_is_read_from_the_named_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_VARIABLE, " secret ")
    configured = LLMConfiguration.model_validate(profile("claude-haiku-5-5"))
    monkeypatch.delenv(KEY_VARIABLE)
    unset = LLMConfiguration.model_validate(profile("claude-haiku-5-5"))

    assert configured.api_key is not None
    assert configured.api_key.get_secret_value() == "secret"
    assert configured.is_configured()
    assert unset.api_key is None
    assert not unset.is_configured()


def test_the_settings_are_validated() -> None:
    model = LLMConfiguration.model_validate(
        profile(" claude-sonnet-5-5 ", temperature=-1, input_rate_per_million=2, output_rate_per_million=10)
    )

    assert (model.model_name, model.temperature, model.provider) == ("claude-sonnet-5-5", 0.0, LLMProvider.ANTHROPIC)
    assert model.cache_read_rate() == Decimal("0.2")
    with pytest.raises(ValidationError):
        LLMConfiguration.model_validate(profile("claude-sonnet-5-5", max_tokens=0))
    with pytest.raises(ValidationError):
        LLMConfiguration.model_validate(profile("claude-sonnet-5-5", unknown=1))


class TestRouting:
    def routing(self, **fields: JsonValue) -> LLMRoutingConfig:
        values: Dict[str, JsonValue] = {
            "default_profile": "balanced",
            "profiles": {"balanced": profile("claude-sonnet-5-5"), "fast": profile("claude-haiku-5-5")},
            "tasks": {"label_translation": {"profile": "fast", "effort": "low", "max_tokens": 1024}},
            **fields,
        }
        return LLMRoutingConfig.model_validate(values)

    def test_a_task_gets_its_profile_with_its_overrides(self) -> None:
        resolved = self.routing().resolve(LLMTask.LABEL_TRANSLATION, None)

        assert resolved is not None
        assert (resolved.model_name, resolved.effort, resolved.max_tokens) == ("claude-haiku-5-5", LLMEffort.LOW, 1024)

    def test_an_unnamed_task_gets_the_default_profile_and_a_disabled_routing_the_fallback(self) -> None:
        fallback = LLMConfiguration.model_validate(profile("claude-opus-5-5"))
        default = self.routing().resolve(LLMTask.ITEM_CLASSIFICATION, fallback)

        assert default is not None
        assert default.model_name == "claude-sonnet-5-5"
        assert self.routing(enabled=False).resolve(LLMTask.LABEL_TRANSLATION, fallback) is fallback

    def test_an_undeclared_profile_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Unknown LLM profiles"):
            self.routing(tasks={"item_classification": {"profile": "precise"}}, default_profile="nowhere")
        assert UnknownLLMProfileError(["a"]).problems == ["a"]

    def test_an_enabled_routing_needs_a_profile(self) -> None:
        with pytest.raises(ValidationError, match="at least one profile"):
            LLMRoutingConfig.model_validate({"profiles": {}})
        assert isinstance(EmptyLLMRoutingError(), ValueError)


def test_a_task_is_configured_only_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    raw: Dict[str, JsonValue] = {"llm": profile("claude-sonnet-5-5"), "batch_size": 20}
    assert not LLMSettings.model_validate(raw).is_configured(LLMTask.LABEL_TRANSLATION)
    monkeypatch.setenv(KEY_VARIABLE, "secret")

    settings = LLMSettings.model_validate(raw)

    assert settings.is_configured(LLMTask.LABEL_TRANSLATION)
    assert settings.configuration(LLMTask.ITEM_CLASSIFICATION) == settings.llm
    assert LLMSettings().configuration(LLMTask.LABEL_TRANSLATION) is None
    assert (settings.batch_size, settings.after_crawl, settings.llm_budget.currency) == (20, True, "USD")
