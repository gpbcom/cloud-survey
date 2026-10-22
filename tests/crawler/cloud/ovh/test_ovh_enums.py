from __future__ import annotations

from crawler.cloud.ovh.enums import OvhMenuKey, OvhServiceType
from crawler.cloud.ovh.marketplace import OVHcloudMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert OvhMenuKey.COMING_SOON == "comingSoon"
    assert OvhServiceType.SOFTWARE_ON_PREM == "software on-prem"


def test_service_types_match_the_case_folded_filters() -> None:
    assert "Managed Services".casefold() in OVHcloudMarketplaceCrawler.EXCLUDED_SERVICE_TYPES
    assert OvhServiceType("saas") in OVHcloudMarketplaceCrawler.DELIVERIES
