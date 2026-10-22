from __future__ import annotations

from crawler.cloud.ibm.crawler import IBMCloudCrawler
from crawler.cloud.ibm.enums import IbmCatalogueTag, IbmOfferField, IbmOfferKind
from crawler.cloud.ibm.marketplace import IBMMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert IbmCatalogueTag.DEPRECATED == "ibm_deprecated"
    assert IbmOfferField.CATALOG_URL == "catalogUrl"


def test_tag_groups_match_the_catalogue_tags() -> None:
    assert {"ibm_deprecated", "ibm_beta"} == IBMCloudCrawler.EXCLUDED_TAGS
    assert "ibm_third_party" in IBMMarketplaceCrawler.KEPT_TAGS
    assert IbmOfferKind("vsi_image") in IBMMarketplaceCrawler.DELIVERIES
