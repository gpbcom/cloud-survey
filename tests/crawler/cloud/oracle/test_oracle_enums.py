from __future__ import annotations

from crawler.cloud.oracle.crawler import OracleCloudCrawler
from crawler.cloud.oracle.enums import OracleListingType, OracleTocField
from crawler.cloud.oracle.marketplace import OracleMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert OracleTocField.SOURCE_BASEPATHS == "sourceBasepaths"
    assert OracleListingType.OCI_APPLICATION == "OCI_APPLICATION"


def test_groups_match_the_source_codes() -> None:
    assert OracleCloudCrawler.PANEL_CATEGORIES == (("rc105w3", "h3"), ("rc105w5", "h4"))
    assert "SERVICE" in OracleMarketplaceCrawler.EXCLUDED_TYPES
