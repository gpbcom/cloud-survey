from __future__ import annotations

from pathlib import Path

import pytest

from conf import LLM_CONFIG_PATH
from llm.exception import LLMConfigurationFileError
from llm.settings_loader import LLMSettingsLoader
from models.configuration.llm.enums import LLMTask


def test_the_project_settings_route_both_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")

    settings = LLMSettingsLoader().load()

    translation = settings.configuration(LLMTask.LABEL_TRANSLATION)
    classification = settings.configuration(LLMTask.ITEM_CLASSIFICATION)
    assert LLMSettingsLoader().path() == LLM_CONFIG_PATH
    assert translation is not None
    assert classification is not None
    assert translation.model_name.startswith("claude-haiku-")
    assert classification.model_name.startswith("claude-sonnet-")
    assert settings.is_configured(LLMTask.LABEL_TRANSLATION)


def test_the_variable_names_another_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "llm.yaml"
    other.write_text("batch_size: 7\n", encoding="utf-8")
    monkeypatch.setenv(LLMSettingsLoader.PATH_VARIABLE, str(other))

    settings = LLMSettingsLoader().load()

    assert settings.batch_size == 7
    assert settings.configuration(LLMTask.LABEL_TRANSLATION) is None
    assert LLMSettingsLoader().load(tmp_path / "missing.yaml").llm is None


@pytest.mark.parametrize("content", ["llm: [unclosed", "batch_size: 0", "llm_routing: {profiles: {}}"])
def test_broken_settings_are_refused(tmp_path: Path, content: str) -> None:
    broken = tmp_path / "llm.yaml"
    broken.write_text(content, encoding="utf-8")

    with pytest.raises(LLMConfigurationFileError):
        LLMSettingsLoader().load(broken)
