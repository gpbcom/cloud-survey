from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.exception import MigrationError, StackInstallError
from scripts.install_stack import StackInstaller


def installer() -> StackInstaller:
    stack = StackInstaller()
    stack.WAIT_TIMEOUT = 0.0  # type: ignore[misc]
    return stack


def run_with(stack: StackInstaller, argv: List[str], which: str = "/usr/bin/docker") -> int:
    with (
        patch("scripts.install_stack.shutil.which", return_value=which),
        patch.object(StackInstaller, "_run", new_callable=AsyncMock, return_value="") as run,
        patch.object(StackInstaller, "_wait", new_callable=AsyncMock) as wait,
        patch("scripts.install_stack.DatabaseMigrator") as migrator,
    ):
        code = stack.parse(argv)
        stack.calls = (run, wait, migrator)  # type: ignore[attr-defined]
    return code


def test_the_stack_is_started_waited_for_and_migrated() -> None:
    stack = installer()

    assert run_with(stack, ["--test"]) == 0

    run, wait, migrator = stack.calls  # type: ignore[attr-defined]
    commands = [call.args[0] for call in run.await_args_list]
    assert commands == [
        ["docker", "compose", "version"],
        ["docker", "compose", "--profile", "test", "up", "-d", "--wait", "postgres", "postgres-test"],
    ]
    assert wait.await_count == 2
    assert migrator.return_value.upgrade.call_count == 2


def test_an_existing_server_is_used_without_docker() -> None:
    stack = installer()

    assert run_with(stack, ["--no-docker"]) == 0

    run, wait, _ = stack.calls  # type: ignore[attr-defined]
    run.assert_not_awaited()
    assert wait.await_count == 1


def test_a_missing_docker_is_reported() -> None:
    assert run_with(installer(), [], which="") == 1


def test_a_failing_migration_is_reported() -> None:
    stack = installer()
    with (
        patch.object(StackInstaller, "_start_services", new_callable=AsyncMock),
        patch.object(StackInstaller, "_wait", new_callable=AsyncMock),
        patch("scripts.install_stack.DatabaseMigrator") as migrator,
    ):
        migrator.return_value.upgrade.side_effect = MigrationError("upgrade", "boom")
        assert stack.parse([]) == 1


def test_a_missing_import_folder_is_reported(tmp_path: pytest.TempPathFactory) -> None:
    stack = installer()
    with (
        patch.object(StackInstaller, "_start_services", new_callable=AsyncMock),
        patch.object(StackInstaller, "_wait", new_callable=AsyncMock),
        patch("scripts.install_stack.DatabaseMigrator"),
    ):
        assert stack.parse(["--import-json", "/nonexistent/output"]) == 1


async def test_a_failing_command_is_reported() -> None:
    with pytest.raises(StackInstallError, match=r"exit code"):
        await installer()._run(["false"])
    with pytest.raises(StackInstallError):
        await installer()._run(["/nonexistent/command"])
    assert (await installer()._run(["echo", "ready"])).strip() == "ready"


async def test_a_database_refusing_connections_is_reported() -> None:
    from models.configuration.storage.storage_settings import StorageSettings

    with pytest.raises(StackInstallError, match="wait for the database"):
        await installer()._wait(StorageSettings(url="postgresql+asyncpg://u:p@127.0.0.1:9/nowhere"))


def test_the_installer_holds_no_state() -> None:
    assert isinstance(installer().logger, MagicMock) is False
