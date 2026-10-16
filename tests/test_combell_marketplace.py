from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.combell.marketplace import CombellMarketplaceCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
URL = "https://www.combell.com/en/hosting/cms"
ONE_CLICK = "One-click installation on Combell web hosting."
SUPPORTED = "Supported on Combell web hosting."


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> CombellMarketplaceCrawler:
    return CombellMarketplaceCrawler(classifier=classifier)


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "combell_cms.html").read_bytes())


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def by_name(results: List[Union[Dict[str, JsonValue], Request]], name: str) -> Dict[str, JsonValue]:
    return next(item for item in items(results) if item["name"] == name)


def test_configuration(crawler: CombellMarketplaceCrawler) -> None:
    assert crawler.name == "combell-marketplace"
    assert CombellMarketplaceCrawler.catalogue_url == URL
    assert CombellMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.combell.com"}
    assert CombellMarketplaceCrawler.ONE_CLICK_DESCRIPTION == ONE_CLICK
    assert CombellMarketplaceCrawler.SUPPORTED_DESCRIPTION == SUPPORTED
    assert CombellMarketplaceCrawler.CATEGORY == "CMS"


async def test_extracts_the_content_management_systems(
    crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert names(results) == [
        "WordPress",
        "WooCommerce",
        "Drupal",
        "Joomla",
        "PrestaShop",
        "Laravel",
        "Symfony",
        "CraftCMS",
        "Shopware",
        "Fork",
        "Umbraco .NET",
        "Matomo",
        "TYPO3",
        "Concrete5",
        "Nextcloud",
    ]
    assert items(results)[0] == {
        "name": "WordPress",
        "description": ONE_CLICK,
        "publisher": None,
        "url": "https://www.combell.com/en/hosting/cms#wordpress",
        "delivery": "one-click-app",
        "marketplace_categories": ["CMS"],
        "categories": ["end-user-software"],
        "types": ["cms"],
    }


async def test_review_badges_are_not_listings(crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert "Review Outstanding" not in names(results)


async def test_only_the_badged_cards_are_one_click(crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert [item["name"] for item in items(results) if item["description"] == ONE_CLICK] == [
        "WordPress",
        "Drupal",
        "Joomla",
    ]
    assert by_name(results, "WooCommerce")["description"] == SUPPORTED


async def test_hosting_suffix_is_removed(crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    umbraco = by_name(await crawl_page(crawler, fixture_page()), "Umbraco .NET")

    assert umbraco["url"] == "https://www.combell.com/en/hosting/cms#umbraco-net"


async def test_every_listing_is_a_one_click_app(crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert {str(item["delivery"]) for item in items(results)} == {"one-click-app"}
    assert by_name(results, "WordPress")["types"] == ["cms"]
    assert by_name(results, "WooCommerce")["types"] == ["ecommerce"]


async def test_malformed_cards_are_skipped(crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    cards = (
        '<div class="card shadow"><div class="card-body">No logo</div></div>'
        '<div class="card shadow"><img src="/x.png" alt=" "></div>'
        '<div class="card shadow"><img src="/y.png" alt="+++"></div>'
    )

    results = await crawl_page(crawler, response(f"<div><div>{cards}</div></div>"))

    assert [(item["name"], item["url"]) for item in items(results)] == [("+++", None)]


async def test_page_without_cards_is_an_error(
    crawler: CombellMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, response('<img src="/stars.svg" alt="Review Outstanding">'))

    assert any(
        record.levelno == logging.ERROR and "holds no software" in record.getMessage() for record in caplog.records
    )


async def test_invalid_listing_is_skipped(
    crawler: CombellMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(crawler, "SUPPORTED_DESCRIPTION", " ")

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, fixture_page())

    assert names(results) == ["WordPress", "Drupal", "Joomla"]
    assert "invalid marketplace entry 'WooCommerce'" in caplog.text
