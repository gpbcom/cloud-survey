from __future__ import annotations

import asyncio
import threading
from typing import List

import pytest
from pytestqt.qtbot import QtBot
from sqlalchemy import text

from gui.storage_bridge.storage_loop import StorageLoop
from models.configuration.storage.storage_settings import StorageSettings
from models.storage.dataset_stamp import DatasetStamp
from storage.exception import StorageError
from storage.storage import Storage


@pytest.mark.db
def test_a_request_runs_in_the_storage_thread_and_answers_in_the_gui_thread(
    qtbot: QtBot, gui_loop: StorageLoop
) -> None:
    answers: List[List[DatasetStamp]] = []
    threads: List[str] = []

    async def job(storage: Storage) -> List[DatasetStamp]:
        threads.append(threading.current_thread().name)
        return await storage.datasets.stamps()

    def answer(stamps: List[DatasetStamp]) -> None:
        answers.append(stamps)
        threads.append(threading.current_thread().name)

    gui_loop.submit(job, answer)

    qtbot.waitUntil(lambda: len(answers) == 1)
    assert answers == [[]]
    assert threads == ["storage", threading.main_thread().name]
    assert gui_loop.is_running


def test_an_unreachable_storage_answers_with_its_error(qtbot: QtBot) -> None:
    loop = StorageLoop(Storage(StorageSettings(url="postgresql+asyncpg://u:p@127.0.0.1:9/nowhere")))
    errors: List[StorageError] = []
    try:
        loop.submit(lambda storage: storage.datasets.stamps(), lambda stamps: None, errors.append)
        qtbot.waitUntil(lambda: len(errors) == 1)
    finally:
        loop.stop()

    assert "Cannot use the database" in str(errors[0])
    assert not loop.is_running


def test_a_failing_request_without_error_callback_is_only_logged(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    loop = StorageLoop(Storage(StorageSettings(url="postgresql+asyncpg://u:p@127.0.0.1:9/nowhere")))
    try:
        future = loop.submit(lambda storage: storage.datasets.stamps(), lambda stamps: None)
        future.result(10)
        qtbot.wait(50)
    finally:
        loop.stop()

    assert any("cannot be opened" in message for message in caplog.messages)


def test_stopping_a_loop_never_started_does_nothing() -> None:
    loop = StorageLoop(Storage(StorageSettings()))

    loop.stop()

    assert not loop.is_running


@pytest.mark.db
async def test_stopping_cancels_the_running_jobs_and_frees_their_connections(
    qtbot: QtBot, storage: Storage, storage_settings: StorageSettings
) -> None:
    loop = StorageLoop(Storage(storage_settings))
    started = threading.Event()
    answers: List[int] = []

    async def job(opened: Storage) -> int:
        async with opened.database.connect() as connection:
            await connection.execute(text("SELECT count(*) FROM software"))
            started.set()
            await asyncio.sleep(60)
        return 1

    loop.submit(job, answers.append)
    qtbot.waitUntil(started.is_set, timeout=5000)

    loop.stop()

    async with storage.database.connect() as connection:
        await connection.execute(text("SET lock_timeout = '2s'"))
        await connection.execute(text("LOCK TABLE software IN ACCESS EXCLUSIVE MODE"))
        await connection.rollback()
    assert answers == []
    assert not loop.is_running


async def test_stopping_lets_a_short_running_job_finish(
    qtbot: QtBot, storage: Storage, storage_settings: StorageSettings
) -> None:
    loop = StorageLoop(Storage(storage_settings))
    started, finished = threading.Event(), threading.Event()

    async def job(opened: Storage) -> int:
        async with opened.database.connect() as connection:
            started.set()
            await asyncio.sleep(0.3)
            await connection.execute(text("SELECT count(*) FROM software"))
        finished.set()
        return 1

    loop.submit(job, lambda answer: None)
    qtbot.waitUntil(started.is_set, timeout=5000)

    loop.stop()

    assert finished.is_set()
    async with storage.database.connect() as connection:
        await connection.execute(text("SET lock_timeout = '2s'"))
        await connection.execute(text("LOCK TABLE software IN ACCESS EXCLUSIVE MODE"))
        await connection.rollback()
