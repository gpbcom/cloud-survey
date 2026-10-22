from __future__ import annotations

from crawler.cloud.gcp.enums import GcpBrowseRequestField, GcpHtmlAttribute, GcpProductType
from crawler.cloud.gcp.marketplace import GoogleCloudMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert GcpHtmlAttribute.CATEGORY_ID == "data-category-id"
    assert GcpBrowseRequestField.TYPE == "@type"


def test_product_types_match_the_card_texts() -> None:
    assert "SaaS & APIs" in GoogleCloudMarketplaceCrawler.DELIVERIES
    assert GcpProductType("Professional Services") in GoogleCloudMarketplaceCrawler.EXCLUDED_TYPES
