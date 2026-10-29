from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from crawler.factory import CrawlerFactory
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.bundle.bundle_files import BundleFiles
from curated.exception import CuratedError


def test_the_shipped_catalogue_names_only_known_crawlers() -> None:
    catalog = BundleCatalogs().launches()

    crawlers = {crawler.name for crawler in CrawlerFactory.CRAWLER_MAP.values()}
    assert {entry.crawler for entry in catalog.aliases} | {entry.crawler for entry in catalog.launches} <= crawlers


@pytest.mark.parametrize(
    "content",
    [None, '{"launches": [', '{"launches": [{"crawler": "gcp", "name": "Spanner", "launched": "2017"}]}'],
)
def test_reports_why_a_catalogue_cannot_be_read(tmp_path: Path, content: Optional[str]) -> None:
    if content is not None:
        (tmp_path / "launches.json").write_text(content, encoding="utf-8")

    with pytest.raises(CuratedError):
        BundleCatalogs(BundleFiles(tmp_path)).launches()
