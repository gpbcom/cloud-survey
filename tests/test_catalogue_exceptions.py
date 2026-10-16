from __future__ import annotations

from pathlib import Path

from catalogue.exception import CatalogueFileError, CatalogueStoreError, CatalogueWriteError


def test_root_error() -> None:
    error = CatalogueStoreError("Something went wrong.")

    assert isinstance(error, Exception)
    assert (error.message, str(error)) == ("Something went wrong.", "Something went wrong.")


def test_file_error() -> None:
    error = CatalogueFileError(Path("output/scaleway.json"), "the file is not valid JSON")

    assert isinstance(error, CatalogueStoreError)
    assert (error.path, error.reason) == (Path("output/scaleway.json"), "the file is not valid JSON")
    assert str(error) == "Cannot load the catalogue 'output/scaleway.json': the file is not valid JSON."


def test_write_error() -> None:
    error = CatalogueWriteError(Path("output/scaleway.json"), "Permission denied")

    assert isinstance(error, CatalogueStoreError)
    assert (error.path, error.reason) == (Path("output/scaleway.json"), "Permission denied")
    assert str(error) == "Cannot write the catalogue 'output/scaleway.json': Permission denied."
