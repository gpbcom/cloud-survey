from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, ClassVar, Dict, Iterator, List, Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import EmptyCatalogueError, ParseNotImplementedError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod, SoftwareCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
API_URL = "https://marketplace.example.com/api/listings"


class DummyMarketplaceCrawler(BaseMarketplaceCrawler):
    """Marketplace crawler relying on every default of the base class."""


class JsonMarketplaceCrawler(BaseMarketplaceCrawler):
    """Marketplace crawler reading a JSON list of `{name, description, url, categories}` listings."""

    name = "json-marketplace"
    catalogue_url: ClassVar[str] = API_URL

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        for entry in json.loads(response.body):
            software = self._build_software(
                entry.get("name"),
                entry.get("description"),
                entry.get("url"),
                entry.get("publisher"),
                DeliveryMethod.SAAS,
                entry.get("categories", []),
                [self._category(path, "/".join(path)) for path in entry.get("paths", [])],
            )
            if software is not None:
                yield software


def page(listings: JsonValue, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=API_URL,
        content=json.dumps(listings),
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def listing(
    name: str, categories: List[str], url: str = "https://marketplace.example.com/p/1", paths: JsonValue = None
) -> JsonValue:
    labels: List[JsonValue] = list(categories)
    entry: Dict[str, JsonValue] = {"name": name, "description": f"{name} description", "url": url, "categories": labels}
    if paths is not None:
        entry["paths"] = paths
    return entry


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


class TestConfiguration:
    def test_defaults(self, classifier: SoftwareClassifier) -> None:
        crawler = DummyMarketplaceCrawler(classifier=classifier)

        assert BaseMarketplaceCrawler.lazy_browser is True
        assert BaseMarketplaceCrawler.page_limit is None
        assert crawler.software_categories == {}
        assert crawler.classifier is classifier

    def test_default_classifier(self) -> None:
        assert isinstance(DummyMarketplaceCrawler().classifier, SoftwareClassifier)

    def test_sessions(self, stealth_session_cls: MagicMock) -> None:
        crawler = JsonMarketplaceCrawler()
        manager = MagicMock(spec=SessionManager)

        with patch("crawler.marketplace.base.FetcherSession", autospec=True) as http_cls:
            crawler.configure_sessions(manager)

        assert [call.args[0] for call in manager.add.call_args_list] == [
            "json-marketplace-session",
            "json-marketplace-http",
        ]
        assert manager.add.call_args_list[0].kwargs == {"lazy": True}
        assert manager.add.call_args_list[1].kwargs == {"default": True}
        http_cls.assert_called_once_with(impersonate="chrome", timeout=60, retries=3, retry_delay=1)

    def test_http_session_is_the_default(self) -> None:
        crawler = JsonMarketplaceCrawler()

        assert crawler._session_manager.default_session_id == "json-marketplace-http"
        assert crawler._session_manager.session_ids == ["json-marketplace-session", "json-marketplace-http"]


class TestRequests:
    def test_api_request(self) -> None:
        request = JsonMarketplaceCrawler()._api_request(
            API_URL, "POST", {"page": 2}, {"x-language": "en"}, {"page": 2}, 5
        )

        assert (request.url, request.sid, request.priority, request.dont_filter, request.meta) == (
            API_URL,
            "json-marketplace-http",
            5,
            True,
            {"page": 2},
        )
        assert request._session_kwargs == {"method": "POST", "json": {"page": 2}, "headers": {"x-language": "en"}}

    def test_api_request_defaults(self) -> None:
        request = JsonMarketplaceCrawler()._api_request(API_URL)

        assert request._session_kwargs == {"method": "GET", "json": None, "headers": None}
        assert (request.meta, request.priority) == ({}, 0)

    @pytest.mark.parametrize(("limit", "page", "allowed"), [(None, 500, True), (2, 2, True), (2, 3, False)])
    def test_page_limit(self, limit: Optional[int], page: int, allowed: bool) -> None:
        crawler = JsonMarketplaceCrawler()

        with patch.object(JsonMarketplaceCrawler, "page_limit", limit):
            assert crawler._within_page_limit(page) is allowed


class TestBuildSoftware:
    def test_classified_software(self, classifier: SoftwareClassifier) -> None:
        software = JsonMarketplaceCrawler(classifier=classifier)._build_software(
            " Acme   Recruit ",
            "Hiring\u00a0made simple",
            " https://marketplace.example.com/p/acme ",
            " Acme Inc ",
            DeliveryMethod.SAAS,
            ["Human Resources", " ", None, "Talent Acquisition"],
        )

        assert software == MarketplaceSoftware(
            name="Acme Recruit",
            description="Hiring made simple",
            publisher="Acme Inc",
            url="https://marketplace.example.com/p/acme",
            delivery=DeliveryMethod.SAAS,
            marketplace_categories=["Human Resources", "Talent Acquisition"],
            categories=[SoftwareCategory.END_USER_SOFTWARE],
        )

    def test_long_texts_are_shortened_and_bad_urls_dropped(self, classifier: SoftwareClassifier) -> None:
        software = JsonMarketplaceCrawler(classifier=classifier)._build_software(
            "x" * 400, "Word. " * 300, "/relative", " "
        )

        assert software is not None
        assert (len(software.name), software.url, software.publisher) == (300, None, None)
        assert len(software.description) <= 1000

    def test_invalid_entries_are_skipped(
        self, classifier: SoftwareClassifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        assert JsonMarketplaceCrawler(classifier=classifier)._build_software(None, "Description") is None
        assert any(record.levelname == "WARNING" for record in caplog.records)


class TestParse:
    async def test_streams_the_software(self, crawl_page: CrawlPage, classifier: SoftwareClassifier) -> None:
        results = await crawl_page(JsonMarketplaceCrawler(classifier=classifier), page([listing("Acme CRM", [])]))

        assert results == [
            {
                "name": "Acme CRM",
                "description": "Acme CRM description",
                "publisher": None,
                "url": "https://marketplace.example.com/p/1",
                "delivery": "saas",
                "marketplace_categories": [],
                "categories": ["end-user-software"],
            }
        ]

    async def test_duplicates_are_skipped(self, crawl_page: CrawlPage, classifier: SoftwareClassifier) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        await crawl_page(crawler, page([listing("Acme", ["Security"])]))

        assert await crawl_page(crawler, page([listing("Acme", ["Security"])])) == []

    async def test_new_categories_stream_the_software_again(
        self, crawl_page: CrawlPage, classifier: SoftwareClassifier
    ) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        await crawl_page(crawler, page([listing("Acme", ["Security"])]))

        results = await crawl_page(crawler, page([listing("Acme", ["CRM"])]))

        assert len(results) == 1
        item = results[0]
        assert isinstance(item, dict)
        assert (item["marketplace_categories"], item["categories"]) == (
            ["Security", "CRM"],
            ["developer-tool", "end-user-software"],
        )
        assert crawler.software_categories == {"https://marketplace.example.com/p/1": ["Security", "CRM"]}

    async def test_page_without_software_is_an_error(
        self, crawl_page: CrawlPage, classifier: SoftwareClassifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(EmptyCatalogueError):
            await crawl_page(JsonMarketplaceCrawler(classifier=classifier), page([{"name": " "}]))

        assert any(record.levelno == logging.ERROR for record in caplog.records)

    async def test_page_which_may_be_empty(self, crawl_page: CrawlPage, classifier: SoftwareClassifier) -> None:
        response = page([], {BaseMarketplaceCrawler.MAY_BE_EMPTY: True})

        assert await crawl_page(JsonMarketplaceCrawler(classifier=classifier), response) == []

    async def test_extraction_must_be_implemented(
        self, crawl_page: CrawlPage, classifier: SoftwareClassifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(ParseNotImplementedError):
            await crawl_page(DummyMarketplaceCrawler(classifier=classifier), page([]))

        assert any(record.levelno == logging.ERROR for record in caplog.records)


class TestLifecycle:
    async def test_new_crawl_forgets_the_software(self, classifier: SoftwareClassifier) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        crawler.software_categories["x"] = []

        await crawler.on_start()

        assert crawler.software_categories == {}

    async def test_resumed_crawl_keeps_the_software(self, classifier: SoftwareClassifier) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        crawler.software_categories["x"] = []

        await crawler.on_start(resuming=True)

        assert crawler.software_categories == {"x": []}

    async def test_summary(self, classifier: SoftwareClassifier, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        crawler.software_categories["x"] = []

        await crawler.on_close()

        assert "The json-marketplace marketplace crawl is over: 1 software streamed." in caplog.messages


@pytest.mark.parametrize(
    ("url", "publisher", "identity"),
    [
        ("https://Marketplace.example.com/P/1/", "Acme", "https://marketplace.example.com/p/1"),
        (None, "Acme", "acme crm|acme"),
        (None, None, "acme crm|"),
    ],
)
def test_software_identity(url: Optional[str], publisher: Optional[str], identity: str) -> None:
    software = MarketplaceSoftware(
        name="Acme CRM",
        description="CRM",
        url=url,
        publisher=publisher,
        categories=[SoftwareCategory.END_USER_SOFTWARE],
    )

    assert software.identity() == identity


class TestCategoryPaths:
    def test_a_category_is_built_from_the_scraped_labels(self, classifier: SoftwareClassifier) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)

        category = crawler._category(["  Data ", None, "", "Databases"], 12)

        assert category is not None
        assert (category.path, category.id) == (["Data", "Databases"], "12")
        assert crawler._category([None, " "]) is None
        assert crawler._category(["a", "b", "c", "d", "e", "f", "g"]) is None

    async def test_listings_seen_again_merge_their_paths(
        self, crawl_page: CrawlPage, classifier: SoftwareClassifier
    ) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        first = listing("Acme CRM", ["CRM"], paths=[["Business"]])
        again = listing("Acme CRM", ["CRM"], paths=[["Business", "CRM"], ["AI"]])

        results = await crawl_page(crawler, page([first, again, again]))

        assert len(results) == 2, "the second listing brings new paths, the third nothing"
        item = results[1]
        assert isinstance(item, dict)
        assert item["marketplace_category_paths"] == [
            {"path": ["Business", "CRM"], "id": "Business/CRM"},
            {"path": ["AI"], "id": "AI"},
        ]
        assert [path.label() for path in crawler.software_category_paths["https://marketplace.example.com/p/1"]] == [
            "Business > CRM",
            "AI",
        ]

    async def test_a_listing_without_paths_streams_none(
        self, crawl_page: CrawlPage, classifier: SoftwareClassifier
    ) -> None:
        results = await crawl_page(JsonMarketplaceCrawler(classifier=classifier), page([listing("Acme CRM", ["CRM"])]))

        item = results[0]
        assert isinstance(item, dict)
        assert "marketplace_category_paths" not in item

    async def test_a_new_crawl_forgets_the_paths(self, classifier: SoftwareClassifier) -> None:
        crawler = JsonMarketplaceCrawler(classifier=classifier)
        crawler.software_category_paths["x"] = []

        await crawler.on_start()

        assert crawler.software_category_paths == {}
