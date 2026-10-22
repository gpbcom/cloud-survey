from __future__ import annotations

from typing import Type

import pytest

from storage.exception import (
    StorageConnectionError,
    StorageError,
    StorageExportError,
    StorageImportError,
    StorageLockError,
    StorageReadError,
    StorageSchemaError,
    StorageWriteError,
)


def test_the_root_error_keeps_its_message() -> None:
    error = StorageError("Something went wrong.")

    assert (error.message, str(error)) == ("Something went wrong.", "Something went wrong.")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (StorageConnectionError("postgresql://db", "refused"), "Cannot use the database postgresql://db: refused."),
        (
            StorageSchemaError("none", "0001"),
            "The database schema is at revision none instead of 0001: run `uv run migrate-db upgrade`.",
        ),
        (StorageLockError("marketplace", "civo"), "The civo marketplace is already being written by another crawl."),
        (StorageWriteError("civo marketplace", "full"), "Cannot write the civo marketplace: full."),
        (StorageReadError("datasets", "gone"), "Cannot read the datasets: gone."),
        (StorageImportError("output/civo.json", "invalid"), "Cannot import output/civo.json: invalid."),
        (StorageExportError("civo.csv", "disk full"), "Cannot export to civo.csv: disk full."),
    ],
)
def test_every_error_explains_itself(error: StorageError, message: str) -> None:
    assert str(error) == message
    assert isinstance(error, StorageError)


@pytest.mark.parametrize(
    "error_cls",
    [
        StorageConnectionError,
        StorageSchemaError,
        StorageLockError,
        StorageWriteError,
        StorageReadError,
        StorageImportError,
        StorageExportError,
    ],
)
def test_every_error_inherits_from_the_root(error_cls: Type[StorageError]) -> None:
    assert issubclass(error_cls, StorageError)
