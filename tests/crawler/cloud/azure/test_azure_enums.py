from __future__ import annotations

from crawler.cloud.azure.enums import AzureCatalogParameter, AzureOfferField, AzureOfferType
from crawler.cloud.azure.marketplace import AzureMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert AzureOfferType.CONSULTING_SERVICES == "ConsultingServices"
    assert AzureOfferField.BIG_CAT_LAST_MODIFIED_DATE == "bigCatLastModifiedDate"


def test_catalog_query_selects_the_offer_dates() -> None:
    query = AzureMarketplaceCrawler.CATALOG_QUERY
    assert query[AzureCatalogParameter.SELECT] == "id,creationDate,bigCatLastModifiedDate"
    assert query["$top"] == "100000"
