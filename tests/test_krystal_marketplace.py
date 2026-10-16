from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.krystal.marketplace import KrystalMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
HOSTING = "https://krystal.io/hosting/"
LISTING = KrystalMarketplaceCrawler.LISTING
MAY_BE_EMPTY = KrystalMarketplaceCrawler.MAY_BE_EMPTY


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> KrystalMarketplaceCrawler:
    return KrystalMarketplaceCrawler(classifier=classifier)


def response(url: str, content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def fixture_page(url: str, fixture: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return response(url, (FIXTURES / fixture).read_bytes(), meta)


def next_data_page(url: str, page_props: JsonValue, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    script = json.dumps({"props": {"pageProps": page_props}})
    return response(url, f'<script id="__NEXT_DATA__" type="application/json">{script}</script>', meta)


def listing(slug: str, name: str, categories: List[Tuple[str, str]]) -> Dict[str, JsonValue]:
    labels: List[JsonValue] = [{"name": label, "slug": category} for label, category in categories]
    return {LISTING: {"url": f"{HOSTING}{slug}", "name": name, "categories": labels}, MAY_BE_EMPTY: True}


def framework(slug: str, name: str, categories: JsonValue) -> Dict[str, JsonValue]:
    return {"name": name, "slug": slug, "categories": categories, "type": "cpanel"}


def requests_of(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, Dict[str, JsonValue]]]:
    return [(result.url, dict(result.meta)) for result in results if isinstance(result, Request)]


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def test_configuration(crawler: KrystalMarketplaceCrawler) -> None:
    assert crawler.name == "krystal-marketplace"
    assert KrystalMarketplaceCrawler.catalogue_url == f"{HOSTING}cms"
    assert KrystalMarketplaceCrawler.complement_urls == tuple(
        f"{HOSTING}{slug}" for slug in ("crm", "ecommerce", "forum", "billingsystems", "blog", "php")
    )
    assert crawler.allowed_domains == {"krystal.io"}
    assert crawler.requested_urls == {
        KrystalMarketplaceCrawler.catalogue_url,
        *KrystalMarketplaceCrawler.complement_urls,
    }


async def test_category_page_requests_the_application_pages(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, fixture_page(f"{HOSTING}cms", "krystal_cms.html"))

    assert items(results) == []
    assert requests_of(results) == [
        (f"{HOSTING}drupal", listing("drupal", "Drupal", [("Blog", "blog"), ("CMS", "cms")])),
        (f"{HOSTING}wordpress", listing("wordpress", "WordPress", [("Blog", "blog"), ("CMS", "cms")])),
        (f"{HOSTING}mediawiki", listing("mediawiki", "MediaWiki", [("CMS", "cms")])),
        (f"{HOSTING}php-nuke", listing("php-nuke", "PHP Nuke", [("CMS", "cms"), ("PHP", "php")])),
    ]


async def test_applications_of_several_categories_are_requested_once(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(crawler, fixture_page(f"{HOSTING}cms", "krystal_cms.html"))
    blog: List[JsonValue] = [framework("wordpress", "WordPress", [{"name": "Blog", "slug": "blog"}])]

    results = await crawl_page(crawler, next_data_page(f"{HOSTING}blog", {"pageType": "category", "frameworks": blog}))

    assert results == []


async def test_unknown_categories_are_requested(crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    categories: List[JsonValue] = [{"name": "Wiki", "slug": "wiki"}, {"name": "CMS", "slug": "cms"}]
    wiki: List[JsonValue] = [framework("mediawiki", "MediaWiki", categories)]

    results = await crawl_page(crawler, next_data_page(f"{HOSTING}cms", {"pageType": "category", "frameworks": wiki}))

    assert [url for url, _ in requests_of(results)] == [f"{HOSTING}wiki", f"{HOSTING}mediawiki"]
    assert requests_of(results)[0][1] == {}


async def test_invalid_slugs_are_ignored(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    frameworks: List[JsonValue] = [
        framework("../client", "Traversal", None),
        {"name": "No slug", "categories": [{"name": "CMS"}]},
        framework("grav", "Grav", [{"name": "CMS", "slug": "cms"}]),
    ]

    with caplog.at_level(logging.DEBUG):
        results = await crawl_page(
            crawler, next_data_page(f"{HOSTING}cms", {"pageType": "category", "frameworks": frameworks})
        )

    assert [url for url, _ in requests_of(results)] == [f"{HOSTING}grav"]
    assert "invalid krystal-marketplace application slug '../client'" in caplog.text
    assert "invalid krystal-marketplace category slug None" in caplog.text


async def test_application_page(crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    meta = listing("wordpress", "WordPress", [("Blog", "blog"), ("CMS", "cms")])

    results = await crawl_page(crawler, fixture_page(f"{HOSTING}wordpress", "krystal_app_wordpress.html", meta))

    assert results == [
        {
            "name": "WordPress",
            "description": (
                "Expert managed WordPress hosting powered by Onyx. Enjoy lightning-fast performance, advanced "
                "security, automatic updates and award-winning UK support."
            ),
            "publisher": None,
            "url": f"{HOSTING}wordpress",
            "delivery": "one-click-app",
            "marketplace_categories": ["Blog", "CMS"],
            "categories": ["end-user-software"],
            "types": ["cms"],
        }
    ]


async def test_listing_categories_are_merged(crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    meta = listing("suitecrm", "SuiteCRM", [("Sales", "sales")])

    results = await crawl_page(crawler, fixture_page(f"{HOSTING}suitecrm", "krystal_app_suitecrm.html", meta))

    assert [(item["name"], item["marketplace_categories"], item["types"]) for item in items(results)] == [
        ("SuiteCRM", ["CRM", "Sales"], ["crm"])
    ]


async def test_dedicated_page_completed_by_its_listing(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(crawler, fixture_page(f"{HOSTING}ecommerce", "krystal_ecommerce.html"))
    meta = listing("woocommerce", "WooCommerce", [("E-commerce", "ecommerce")])

    results = await crawl_page(crawler, fixture_page(f"{HOSTING}woocommerce", "krystal_app_woocommerce.html", meta))

    assert [(item["name"], item["marketplace_categories"], item["types"]) for item in items(results)] == [
        ("WooCommerce", ["E-commerce"], ["ecommerce"])
    ]
    assert str(items(results)[0]["description"]).startswith("Lightning-fast, secure, fully managed WooCommerce")


async def test_forum_category(crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(crawler, fixture_page(f"{HOSTING}forum", "krystal_forum.html"))

    assert requests_of(results) == [
        (f"{HOSTING}phpbb", listing("phpbb", "PHPBB", [("Forum", "forum")])),
        (f"{HOSTING}xenforo", listing("xenforo", "Xenforo", [("Forum", "forum"), ("PHP", "php")])),
    ]


async def test_meta_description_fallback(crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    script = json.dumps({"props": {"pageProps": {"pageType": "framework", "name": "Grav", "slug": "grav"}}})
    content = (
        '<html><head><meta name="description" content="Grav hosting."></head>'
        f'<body><script id="__NEXT_DATA__" type="application/json">{script}</script></body></html>'
    )

    software = list(crawler.extract_software(response(f"{HOSTING}grav", content)))

    assert [(item.name, item.description, item.url) for item in software] == [
        ("Grav", "Grav hosting.", f"{HOSTING}grav")
    ]


async def test_redirected_application_page_is_skipped(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    meta = listing("mahara", "Mahara", [("CMS", "cms")])

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, next_data_page("https://krystal.io/hosting", {"title": "Hosting"}, meta))

    assert results == []
    assert "application 'Mahara': its page https://krystal.io/hosting/mahara is redirected" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_invalid_application_is_skipped(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    meta = listing("grav", "Grav", [("CMS", "cms")])

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, next_data_page(f"{HOSTING}grav", {"pageType": "framework"}, meta))

    assert results == []
    assert "invalid marketplace entry 'Grav'" in caplog.text


@pytest.mark.parametrize("frameworks", [None, [], "drupal"])
async def test_category_page_without_applications_is_an_error(
    crawler: KrystalMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    frameworks: JsonValue,
) -> None:
    page = next_data_page(f"{HOSTING}cms", {"pageType": "category", "frameworks": frameworks})

    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, page)

    assert any(
        record.levelno == logging.ERROR
        and "category page https://krystal.io/hosting/cms lists no application" in record.getMessage()
        for record in caplog.records
    )


async def test_page_without_next_data_is_an_error(
    crawler: KrystalMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="__NEXT_DATA__"):
        await crawl_page(crawler, response(f"{HOSTING}cms", "<html><body>Maintenance</body></html>"))

    assert any(record.levelno == logging.ERROR and "__NEXT_DATA__" in record.getMessage() for record in caplog.records)
