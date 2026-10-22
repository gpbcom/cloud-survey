from __future__ import annotations

from crawler.cloud.scaleway.crawler import ScalewayCrawler
from crawler.cloud.scaleway.enums import ScalewayBlockField, ScalewayDeliveryLabel
from crawler.cloud.scaleway.marketplace import ScalewayMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert ScalewayBlockField.COMPONENT == "__component"
    assert ScalewayCrawler.PRODUCTS_BLOCK == "blocks.generic-columns"


def test_delivery_labels_match_the_application_labels() -> None:
    assert {"AI", "Cloud", "Bare Metal"} == ScalewayCrawler.MENU_GROUPS
    assert ScalewayDeliveryLabel("Virtual machines") in ScalewayMarketplaceCrawler.DELIVERIES
