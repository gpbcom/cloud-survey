from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.infomaniak.marketplace import InfomaniakMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://www.infomaniak.com/en/hosting/dedicated-and-cloud-servers/jelastic-cloud/applications"
TAB = '<button class="IKLink-module--ikLink--ed03e">{label}</button>'
BLOCK = (
    '<div class="BentoLayout-module--bentoLayout--1a2b3"><p class="IkTypography-module--h4--9z8y7">{name}</p>'
    '<p class="IkTypography-module--body2--4c5d6">{description}</p></div>'
)


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> InfomaniakMarketplaceCrawler:
    return InfomaniakMarketplaceCrawler(classifier=classifier)


def response(content: Union[str, bytes]) -> Response:
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page() -> Response:
    return response((FIXTURES / "infomaniak_applications.html").read_bytes())


def tabbed_page(tabs: List[str], panels: List[str]) -> Response:
    buttons = "".join(TAB.format(label=label) for label in tabs)
    content = "".join(
        f'<div class="FeaturesSection-module--sectionContainerBentosContent--0f9e8">{panel}</div>' for panel in panels
    )
    return response(f'<section><div class="Tabs-module--tabsTab--77aa1">{buttons}</div>{content}</section>')


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def by_name(results: List[Union[Dict[str, JsonValue], Request]], name: str) -> Dict[str, JsonValue]:
    return next(item for item in items(results) if item["name"] == name)


def test_configuration(crawler: InfomaniakMarketplaceCrawler) -> None:
    assert crawler.name == "infomaniak-marketplace"
    assert InfomaniakMarketplaceCrawler.catalogue_url == URL
    assert InfomaniakMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.infomaniak.com"}


async def test_extracts_the_applications_of_each_tab(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(crawler, fixture_page())

    assert [(item["name"], item["marketplace_categories"]) for item in items(results)] == [
        ("Wordpress", ["Web sites"]),
        ("Ghost", ["Web sites"]),
        ("Drupal", ["Web sites"]),
        ("Joomla", ["Web sites"]),
        ("PrestaShop", ["E-commerce"]),
        ("Magento", ["E-commerce"]),
        ("Moodle", ["Collaboration"]),
        ("NextCloud", ["Collaboration"]),
        ("Odoo Community Edition", ["Collaboration"]),
        ("XWiki", ["Collaboration"]),
        ("Mattermost", ["Communication"]),
        ("Jitsi", ["Communication"]),
    ]
    assert by_name(results, "Mattermost") == {
        "name": "Mattermost",
        "description": (
            "A sovereign alternative to Slack or Teams for real-time team messaging, with private hosting and total "
            "data control."
        ),
        "publisher": None,
        "url": f"{URL}#mattermost",
        "delivery": "container",
        "marketplace_categories": ["Communication"],
        "marketplace_category_paths": [{"path": ["Communication"], "id": "communication"}],
        "categories": ["end-user-software"],
    }


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("Wordpress", {"path": ["Web sites"], "id": "website"}),
        ("PrestaShop", {"path": ["E-commerce"], "id": "ecommerce"}),
        ("XWiki", {"path": ["Collaboration"], "id": "collaboration"}),
    ],
)
async def test_category_paths_are_the_tabs(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage, name: str, path: Dict[str, JsonValue]
) -> None:
    assert by_name(await crawl_page(crawler, fixture_page()), name)["marketplace_category_paths"] == [path]


async def test_feature_bullets_are_not_the_description(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    wordpress = by_name(await crawl_page(crawler, fixture_page()), "Wordpress")

    assert wordpress["description"] == (
        "The benchmark platform for creating websites, blogs or online stores easily, thanks to its rich ecosystem of "
        "themes and extensions"
    )


async def test_wrong_descriptions_are_kept_as_published(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    ghost = by_name(await crawl_page(crawler, fixture_page()), "Ghost")

    assert str(ghost["description"]).startswith("An open-source relational database engine")
    assert ghost["categories"] == ["end-user-software"]


@pytest.mark.parametrize(
    ("name", "audiences"),
    [
        ("Wordpress", ["end-user-software"]),
        ("PrestaShop", ["end-user-software"]),
        ("NextCloud", ["end-user-software"]),
        ("Jitsi", ["end-user-software"]),
    ],
)
async def test_classification(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage, name: str, audiences: List[str]
) -> None:
    assert by_name(await crawl_page(crawler, fixture_page()), name)["categories"] == audiences


async def test_malformed_blocks(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    panel = (
        '<div class="BentoLayout-module--bentoLayout--1a2b3"><p class="IkTypography-module--h4--9z8y7">Alone</p></div>'
        + BLOCK.format(name="Empty", description=" ")
        + BLOCK.format(name="+++", description="An application.")
    )

    with caplog.at_level(logging.WARNING):
        results = await crawl_page(crawler, tabbed_page(["Web sites"], [panel]))

    assert [(item["name"], item["url"]) for item in items(results)] == [("+++", None)]
    assert items(results)[0]["marketplace_category_paths"] == [{"path": ["Web sites"], "id": None}]
    assert "invalid marketplace entry 'Empty'" in caplog.text


async def test_tabs_not_matching_the_panels_are_an_error(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    page = tabbed_page(["Web sites", "E-commerce"], [BLOCK.format(name="Ghost", description="A blog.")])

    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="do not match the tab panels"):
        await crawl_page(crawler, page)

    assert any(
        record.levelno == logging.ERROR and "2 tabs for 1 panels" in record.getMessage() for record in caplog.records
    )


async def test_page_without_tabs_is_an_error(
    crawler: InfomaniakMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(crawler, response("<html><body><h1>Applications</h1></body></html>"))

    assert any(
        record.levelno == logging.ERROR and "holds no software" in record.getMessage() for record in caplog.records
    )
