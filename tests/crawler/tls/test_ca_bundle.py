from __future__ import annotations

import os
from pathlib import Path

import certifi
import pytest

from crawler.tls.ca_bundle import CaBundle


@pytest.fixture
def company_bundle(tmp_path: Path) -> Path:
    path = tmp_path / "company.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\nCOMPANY\n-----END CERTIFICATE-----\n", encoding="utf-8")
    return path


def test_the_environment_bundle_is_merged_with_certifi(
    isolated_ca_bundle: Path, company_bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(company_bundle))
    monkeypatch.setenv("CURL_CA_BUNDLE", str(company_bundle))

    path = CaBundle().path()

    merged = Path(path).read_text(encoding="utf-8")
    assert path == str(isolated_ca_bundle)
    assert "COMPANY" in merged
    assert Path(certifi.where()).read_text(encoding="utf-8").strip() in merged
    assert merged.count("COMPANY") == 1, "a bundle named twice is merged once"


def test_installing_points_the_http_client_at_the_merged_bundle(
    isolated_ca_bundle: Path, company_bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(company_bundle))

    path = CaBundle().install()
    size = isolated_ca_bundle.stat().st_size
    again = CaBundle().install()

    assert os.environ["REQUESTS_CA_BUNDLE"] == os.environ["CURL_CA_BUNDLE"] == path == again
    assert isolated_ca_bundle.stat().st_size == size, "the installed bundle is not merged into itself"
    assert "COMPANY" in isolated_ca_bundle.read_text(encoding="utf-8"), "the company bundle is kept"


def test_an_unreadable_environment_bundle_is_left_out(
    isolated_ca_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path / "missing.pem"))

    path = CaBundle().path()

    assert Path(path).read_text(encoding="utf-8").strip() == Path(certifi.where()).read_text(encoding="utf-8").strip()


def test_an_unwritable_cache_falls_back_to_certifi(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")

    assert CaBundle(cache_file=blocker / "ca-bundle.pem").path() == certifi.where()
