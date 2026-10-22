from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel, Field

from main import ALL_TARGETS, SOURCES
from models.cloud.enums import CloudProvider

PROJECT_ROOT = Path(__file__).parent.parent
LAUNCH_FILE = PROJECT_ROOT / ".vscode" / "launch.json"


class LaunchInput(BaseModel):
    """A `launch.json` input variable."""

    id: str
    options: List[str] = Field(default_factory=list)


class LaunchConfiguration(BaseModel):
    """A `launch.json` debug configuration (only the keys checked here)."""

    name: str
    type: str
    python: str
    program: Optional[str] = None
    module: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)


class LaunchFile(BaseModel):
    """The `.vscode/launch.json` file."""

    configurations: List[LaunchConfiguration]
    inputs: List[LaunchInput]


@pytest.fixture(scope="module")
def launch() -> LaunchFile:
    return LaunchFile.model_validate_json(LAUNCH_FILE.read_text(encoding="utf-8"))


def test_target_picker_lists_every_cloud_provider_and_all(launch: LaunchFile) -> None:
    (target_input,) = [item for item in launch.inputs if item.id == "crawlerTarget"]

    assert target_input.options == [provider.value for provider in CloudProvider] + [ALL_TARGETS]


def test_configuration_names_are_unique(launch: LaunchFile) -> None:
    names = [configuration.name for configuration in launch.configurations]

    assert len(names) == len(set(names))


def test_configurations_use_the_project_virtualenv(launch: LaunchFile) -> None:
    for configuration in launch.configurations:
        assert configuration.type == "debugpy", configuration.name
        assert configuration.python == "${workspaceFolder}/.venv/bin/python", configuration.name


def test_crawler_configurations_run_the_entrypoint_with_a_picked_target(launch: LaunchFile) -> None:
    crawlers = [configuration for configuration in launch.configurations if configuration.program is not None]

    assert crawlers
    for configuration in crawlers:
        program = configuration.program
        assert program is not None
        assert (PROJECT_ROOT / program.removeprefix("${workspaceFolder}/")).is_file()
        assert configuration.env == {
            "CRAWLER_TARGET": "${input:crawlerTarget}",
            "CRAWLER_SOURCE": "${input:crawlerSource}",
        }


def test_module_configurations_run_pytest_or_the_gui(launch: LaunchFile) -> None:
    modules = {configuration.module for configuration in launch.configurations if configuration.module is not None}

    assert modules == {"pytest", "gui.window.app"}


def test_source_picker_lists_every_crawl_source(launch: LaunchFile) -> None:
    (source_input,) = [item for item in launch.inputs if item.id == "crawlerSource"]

    assert source_input.options == list(SOURCES)


def test_crawler_configurations_pick_their_source(launch: LaunchFile) -> None:
    crawlers = [configuration for configuration in launch.configurations if "CRAWLER_TARGET" in configuration.env]

    assert crawlers
    assert all(configuration.env["CRAWLER_SOURCE"] == "${input:crawlerSource}" for configuration in crawlers)
