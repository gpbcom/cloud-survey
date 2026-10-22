from __future__ import annotations

import json

from crawler.cloud.aws.enums import AwsDirectoryParameter, AwsFulfillmentOption, AwsListingField, AwsTagNamespace
from crawler.cloud.aws.marketplace import AWSMarketplaceCrawler


def test_values_are_the_source_identifiers() -> None:
    assert AwsTagNamespace.YEAR == "GLOBAL#local-tags-year"
    assert AwsDirectoryParameter.DIRECTORY_ID == "item.directoryId"
    assert AwsListingField.LISTING_CREATOR == "ListingCreator"


def test_members_read_the_source_data() -> None:
    listing = json.loads('{"Id": "prodview-1", "FulfillmentOptionTypes": [{"Value": "SAAS"}]}')
    assert listing.get(AwsListingField.ID) == "prodview-1"
    assert AwsFulfillmentOption(listing[AwsListingField.FULFILLMENT_OPTION_TYPES][0][AwsListingField.VALUE]) in (
        AWSMarketplaceCrawler.DELIVERIES
    )
