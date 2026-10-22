from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Awaitable, Callable, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response, Spider
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError, ParseNotImplementedError
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


class DummyCrawler(BaseCloudCrawler):
    """Concrete crawler relying on every default of the base class."""


class ListCrawler(BaseCloudCrawler):
    """Crawler extracting the `name|description` lines of a plain text page."""

    name = "list-crawler"
    catalogue_url: ClassVar[str] = "https://catalogue.example.com/products/"

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        for line in response.body.decode().splitlines():
            name, _, description = line.partition("|")
            if product := self._build_product(name, description):
                yield product


def page(content: str, url: str = "https://catalogue.example.com/products/") -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def next_data_page(script: str) -> Response:
    return page(f'<html><body><script id="__NEXT_DATA__" type="application/json">{script}</script></body></html>')


class TestConfiguration:
    def test_is_a_spider(self) -> None:
        assert issubclass(BaseCloudCrawler, Spider)

    def test_defaults(self) -> None:
        crawler = DummyCrawler()

        assert crawler.name == "default-crawler"
        assert DummyCrawler.catalogue_url == ""
        assert crawler.allowed_domains == set()
        assert crawler.seen_products == set()

    def test_polite_crawl(self) -> None:
        assert BaseCloudCrawler.robots_txt_obey is True
        assert BaseCloudCrawler.concurrent_requests == 1
        assert BaseCloudCrawler.download_delay == 1.0

    def test_allowed_domain_is_the_catalogue_domain(self) -> None:
        assert ListCrawler().allowed_domains == {"catalogue.example.com"}

    def test_repr_contains_crawler_name(self) -> None:
        assert repr(ListCrawler()) == "<ListCrawler 'list-crawler'>"


class TestSessions:
    def test_registers_a_single_stealth_session(self) -> None:
        crawler = ListCrawler()

        assert crawler._session_manager.session_ids == ["list-crawler-session"]
        assert crawler._session_manager.default_session_id == "list-crawler-session"

    def test_stealth_session_options(self, stealth_session_cls: MagicMock) -> None:
        crawler = DummyCrawler()
        stealth_session_cls.reset_mock()
        manager = MagicMock(spec=SessionManager)

        crawler.configure_sessions(manager)

        stealth_session_cls.assert_called_once_with(
            timeout=120000,
            wait=2000,
            headless=False,
            load_dom=True,
            solve_cloudflare=False,
            retries=3,
            retry_delay=1.0,
        )
        manager.add.assert_called_once_with("default-crawler-session", stealth_session_cls.return_value, lazy=False)

    def test_cloudflare_solver_is_opt_in(self, stealth_session_cls: MagicMock) -> None:
        class ChallengedCrawler(BaseCloudCrawler):
            solve_cloudflare: ClassVar[bool] = True

        crawler = ChallengedCrawler()
        stealth_session_cls.reset_mock()

        crawler.configure_sessions(MagicMock(spec=SessionManager))

        assert stealth_session_cls.call_args.kwargs["solve_cloudflare"] is True

    def test_with_real_stealth_session(self) -> None:
        from scrapling.fetchers import AsyncStealthySession

        with patch("crawler.cloud.base.AsyncStealthySession", AsyncStealthySession):
            crawler = DummyCrawler()

        assert isinstance(crawler._session_manager.get("default-crawler-session"), AsyncStealthySession)


class TestStartRequests:
    async def test_starts_from_the_catalogue_url(self) -> None:
        requests = [request async for request in ListCrawler().start_requests()]

        assert [request.url for request in requests] == ["https://catalogue.example.com/products/"]
        assert requests[0].callback is None  # The engine then calls `parse`.


class TestParse:
    async def test_streams_products_as_dictionaries(self, crawl_page: CrawlPage) -> None:
        results = await crawl_page(ListCrawler(), page("Compute|Virtual machines\nStorage|Object storage"))

        assert results == [
            {"name": "Compute", "description": "Virtual machines", "pricing_policy": [], "url": None},
            {"name": "Storage", "description": "Object storage", "pricing_policy": [], "url": None},
        ]

    async def test_drops_duplicates_case_insensitively(self, crawl_page: CrawlPage) -> None:
        crawler = ListCrawler()

        first = await crawl_page(crawler, page("Compute|Virtual machines\nCOMPUTE|Again"))
        second = await crawl_page(crawler, page("compute|Once more\nStorage|Object storage"))

        assert [item["name"] for item in first + second if isinstance(item, dict)] == ["Compute", "Storage"]
        assert crawler.seen_products == {"compute", "storage"}

    async def test_skips_invalid_entries(self, crawl_page: CrawlPage) -> None:
        results = await crawl_page(ListCrawler(), page("Compute|\n|Nameless\nStorage|Object storage"))

        assert [item["name"] for item in results if isinstance(item, dict)] == ["Storage"]

    async def test_raises_when_the_page_has_no_product(
        self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(EmptyCatalogueError) as exc_info:
            await crawl_page(ListCrawler(), page("Compute|\nnot a product"))

        assert (exc_info.value.crawler, exc_info.value.url) == (
            "list-crawler",
            "https://catalogue.example.com/products/",
        )
        assert "The list-crawler catalogue page https://catalogue.example.com/products/ holds no product." in [
            record.getMessage() for record in caplog.records if record.levelname == "ERROR"
        ]

    async def test_does_not_raise_when_every_product_was_already_streamed(self, crawl_page: CrawlPage) -> None:
        crawler = ListCrawler()
        await crawl_page(crawler, page("Compute|Virtual machines"))

        assert await crawl_page(crawler, page("Compute|Virtual machines")) == []

    async def test_extraction_must_be_implemented(
        self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(ParseNotImplementedError) as exc_info:
            await crawl_page(DummyCrawler(), page("Compute|Virtual machines"))

        assert exc_info.value.crawler == "DummyCrawler"
        assert "The DummyCrawler crawler does not implement the catalogue extraction." in [
            record.getMessage() for record in caplog.records if record.levelname == "ERROR"
        ]


class TestOnStart:
    async def test_new_crawl_forgets_previous_products(self) -> None:
        crawler = ListCrawler()
        crawler.seen_products.add("compute")

        await crawler.on_start()

        assert crawler.seen_products == set()

    async def test_resumed_crawl_keeps_previous_products(self) -> None:
        crawler = ListCrawler()
        crawler.seen_products.add("compute")

        await crawler.on_start(resuming=True)

        assert crawler.seen_products == {"compute"}


class TestBuildProduct:
    def test_collapses_whitespaces(self) -> None:
        product = DummyCrawler()._build_product("  Kubernetes\n Kapsule ", "Managed\u00a0Kubernetes\t ")

        assert product == CloudProduct(name="Kubernetes Kapsule", description="Managed Kubernetes")

    def test_keeps_the_catalogue_categories_cleaned(self) -> None:
        product = DummyCrawler()._build_product(
            "Run", "Containers", categories=["  Serverless\n computing ", None, "", "Containers", "Containers"]
        )

        assert product is not None
        assert product.catalogue_categories == ["Serverless computing", "Containers"]
        assert product.item_dump()["catalogue_categories"] == ["Serverless computing", "Containers"]

    def test_without_categories_none_is_streamed(self) -> None:
        product = DummyCrawler()._build_product("Run", "Containers")

        assert product is not None
        assert product.catalogue_categories == []
        assert "catalogue_categories" not in product.item_dump()

    @pytest.mark.parametrize(
        ("name", "description"), [(None, "Description"), ("Name", None), ("  ", "Description"), ("x" * 201, "D")]
    )
    def test_invalid_entries_are_skipped(self, name: Optional[str], description: Optional[str]) -> None:
        assert DummyCrawler()._build_product(name, description) is None

    def test_long_description_is_shortened_at_a_sentence_end(self) -> None:
        sentence = "Observability for every cloud workload. "
        product = DummyCrawler()._build_product("Datadog", sentence * 40)

        assert product is not None
        assert len(product.description) <= BaseCloudCrawler.DESCRIPTION_LIMIT
        assert product.description.endswith("workload.")
        assert len(product.description) > BaseCloudCrawler.DESCRIPTION_LIMIT // 2

    def test_long_description_without_sentence_end_is_cut_at_a_word(self) -> None:
        product = DummyCrawler()._build_product("MongoDB Atlas", "word, " * 300)

        assert product is not None
        assert len(product.description) <= BaseCloudCrawler.DESCRIPTION_LIMIT
        assert product.description.endswith("word\u2026")

    def test_chinese_sentence_ends_are_kept(self) -> None:
        product = DummyCrawler()._build_product("云服务器", "弹性计算服务。" * 200)

        assert product is not None
        assert product.description.endswith("\u3002")
        assert len(product.description) <= BaseCloudCrawler.DESCRIPTION_LIMIT

    def test_short_description_is_unchanged(self) -> None:
        assert DummyCrawler()._shorten("Short.") == "Short."


class TestNextData:
    def test_reads_the_embedded_json(self) -> None:
        data = DummyCrawler()._next_data(next_data_page(json.dumps({"props": {"pageProps": {"a": 1}}})))

        assert data == {"props": {"pageProps": {"a": 1}}}

    @pytest.mark.parametrize(
        ("response", "reason"),
        [
            (page("<html><body>No script</body></html>"), "is missing"),
            (next_data_page("{not json"), "is not JSON"),
            (next_data_page("[1, 2]"), "is not a JSON object"),
        ],
    )
    def test_rejects_unexpected_content(
        self, response: Response, reason: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(CatalogueFormatError, match=reason) as exc_info:
            DummyCrawler()._next_data(response)

        assert exc_info.value.url == response.url
        assert [record.levelname for record in caplog.records].count("ERROR") == 1


class TestJsonHelpers:
    @pytest.mark.parametrize(("value", "expected"), [({"a": 1}, {"a": 1}), ([1], {}), ("a", {}), (None, {})])
    def test_as_object(self, value: JsonValue, expected: Dict[str, JsonValue]) -> None:
        assert DummyCrawler()._as_object(value) == expected

    @pytest.mark.parametrize(("value", "expected"), [("a", "a"), ("", ""), (1, None), (None, None), (["a"], None)])
    def test_as_text(self, value: JsonValue, expected: Optional[str]) -> None:
        assert DummyCrawler()._as_text(value) == expected

    def test_walk_objects_depth_first(self) -> None:
        document: JsonValue = {"id": 1, "children": [{"id": 2, "children": [{"id": 3}]}, "text", {"id": 4}]}

        ids = [node["id"] for node in DummyCrawler()._walk_objects(document)]

        assert ids == [1, 2, 3, 4]

    @pytest.mark.parametrize("value", ["text", 1, None, []])
    def test_walk_objects_without_object(self, value: JsonValue) -> None:
        assert list(DummyCrawler()._walk_objects(value)) == []

    @pytest.mark.parametrize(("text", "expected"), [(None, ""), ("", ""), (" a \n b\u00a0c ", "a b c")])
    def test_clean_text(self, text: Optional[str], expected: str) -> None:
        assert DummyCrawler()._clean_text(text) == expected


class TestLogging:
    """The crawler logs go through the application logging configuration."""

    def test_initialization_is_logged_through_the_application_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger="scrapling.spiders.list-crawler")

        ListCrawler()

        assert [(record.levelname, record.getMessage()) for record in caplog.records] == [
            ("DEBUG", "Configuring the stealth browser session list-crawler-session."),
            ("INFO", "Spider initialized"),
            (
                "DEBUG",
                "list-crawler crawler ready: catalogue https://catalogue.example.com/products/, "
                "allowed domains {'catalogue.example.com'}.",
            ),
        ]

    def test_spider_logger_is_routed_to_the_application_logging(self) -> None:
        crawler = ListCrawler()

        assert crawler.logger.name == "scrapling.spiders.list-crawler"
        assert crawler.logger.propagate is True
        assert not [handler for handler in crawler.logger.handlers if type(handler) is logging.StreamHandler]
        assert crawler.logger.handlers  # Scrapling's log counter, used by the crawl stats, is kept.

    async def test_extracted_products_are_logged(self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger="scrapling.spiders.list-crawler")

        await crawl_page(ListCrawler(), page("Compute|Virtual machines\nCOMPUTE|Again\nStorage|Object storage"))

        records = [(record.levelname, record.getMessage()) for record in caplog.records]
        assert ("INFO", "Product extracted from list-crawler: Compute - Virtual machines") in records
        assert ("INFO", "Product extracted from list-crawler: Storage - Object storage") in records
        assert ("DEBUG", "Skipping the duplicated product 'COMPUTE'.") in records
        assert records[-1] == (
            "INFO",
            "list-crawler catalogue page https://catalogue.example.com/products/ parsed: "
            "2 new products, 1 duplicates skipped.",
        )

    async def test_invalid_entries_are_logged_as_warnings(
        self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
    ) -> None:
        await crawl_page(ListCrawler(), page("Compute|\nStorage|Object storage"))

        warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
        assert warnings == [
            "Skipping the invalid catalogue entry 'Compute' (description: Value error, "
            + ("The name or description field(s) cannot be empty.).")
        ]

    async def test_crawl_start_and_end_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        crawler = ListCrawler()
        caplog.clear()  # Drop the initialization logs.

        await crawler.on_start()
        crawler.seen_products.update({"compute", "storage"})
        await crawler.on_start(resuming=True)
        await crawler.on_close()

        assert [record.getMessage() for record in caplog.records if record.levelno == logging.INFO] == [
            "Starting the list-crawler catalogue crawl from https://catalogue.example.com/products/.",
            "Resuming the list-crawler catalogue crawl (2 products already streamed).",
            "The list-crawler catalogue crawl is over: 2 products streamed.",
        ]

    async def test_fetch_errors_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        request = Request("https://catalogue.example.com/products/")

        await ListCrawler().on_error(request, TimeoutError("browser timeout"))

        assert caplog.records[-1].levelno == logging.ERROR
        assert caplog.records[-1].getMessage() == (
            "Fetching the list-crawler catalogue page https://catalogue.example.com/products/ failed: "
            "TimeoutError('browser timeout')"
        )

    async def test_crawler_errors_are_not_logged_twice(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger="scrapling.spiders.list-crawler")
        request = Request("https://catalogue.example.com/products/")
        error = EmptyCatalogueError("list-crawler", request.url)

        await ListCrawler().on_error(request, error)

        assert caplog.records[-1].levelno == logging.DEBUG
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


class PrefixedCrawler(BaseCloudCrawler):
    """Crawler of a catalogue with a complementary source and brand prefixes."""

    name = "prefixed-crawler"
    catalogue_url: ClassVar[str] = "https://catalogue.example.com/products/"
    complement_urls: ClassVar[Tuple[str, ...]] = ("https://docs.example.org/",)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Example ", "Example Cloud ")


class TestSources:
    def test_allowed_domains_cover_every_source(self) -> None:
        assert PrefixedCrawler().allowed_domains == {"catalogue.example.com", "docs.example.org"}

    async def test_main_listing_before_the_complements(self) -> None:
        requests = [request async for request in PrefixedCrawler().start_requests()]

        assert [(request.url, request.priority) for request in requests] == [
            ("https://catalogue.example.com/products/", BaseCloudCrawler.PRIMARY_PRIORITY),
            ("https://docs.example.org/", 0),
        ]


class TestDeduplication:
    @pytest.mark.parametrize(
        ("name", "key"),
        [
            ("Example Cloud Run", "run"),
            ("Example Run", "run"),
            ("  example   RUN ", "run"),
            ("Run (preview)", "run"),
            ("Key Management Service (KMS)", "keymanagementservice"),
            ("Example", "example"),
            ("(Beta)", "(beta)"),
            ("云服务器 BCC", "云服务器bcc"),
            ("人脸识别", "人脸识别"),
            ("云数据库\uff08公测\uff09", "云数据库"),
            ("Example Cloud Café-Storage", "caféstorage"),
        ],
    )
    def test_name_keys(self, name: str, key: str) -> None:
        assert PrefixedCrawler()._name_key(name) == key

    @pytest.mark.parametrize(
        ("url", "key"),
        [
            ("https://www.Example.com/Products/Run/?utm=1#top", "example.com/products/run"),
            ("http://example.com/products/run", "example.com/products/run"),
        ],
    )
    def test_url_keys(self, url: str, key: str) -> None:
        assert PrefixedCrawler()._url_key(url) == key

    def test_same_name_or_same_url_is_a_duplicate(self) -> None:
        crawler = PrefixedCrawler()
        run = CloudProduct(name="Example Run", description="Containers", url="https://example.com/run/")

        assert crawler._is_new(run)
        assert not crawler._is_new(CloudProduct(name="Run", description="Same name"))
        assert not crawler._is_new(
            CloudProduct(name="Serverless containers", description="d", url="https://example.com/run")
        )
        assert crawler._is_new(CloudProduct(name="Functions", description="Another product"))
        assert crawler.seen_urls == {"example.com/run"}

    def test_remembered_former_names(self) -> None:
        crawler = PrefixedCrawler()

        crawler._remember(["Example Kubernetes Engine", "  "])

        assert crawler.seen_products == {"kubernetesengine"}
        assert not crawler._is_new(CloudProduct(name="Kubernetes Engine", description="Former name"))

    def test_stream_logs_and_dumps_new_products(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger="scrapling.spiders.prefixed-crawler")
        crawler = PrefixedCrawler()
        product = CloudProduct(name="Run", description="Containers")

        assert crawler._stream(product) == {
            "name": "Run",
            "description": "Containers",
            "pricing_policy": [],
            "url": None,
        }
        assert crawler._stream(product) is None
        assert caplog.messages[-1] == "Skipping the duplicated product 'Run'."

    async def test_new_crawl_forgets_previous_urls(self) -> None:
        crawler = PrefixedCrawler()
        crawler.seen_urls.add("example.com/run")

        await crawler.on_start()

        assert crawler.seen_urls == set()


class TestProductUrl:
    def test_keeps_absolute_links(self) -> None:
        product = DummyCrawler()._build_product("Run", "Containers", " https://example.com/run ")

        assert product is not None
        assert product.url == "https://example.com/run"

    @pytest.mark.parametrize("url", ["/run/", "#", "mailto:team@example.com", "https://"])
    def test_drops_invalid_links_but_keeps_the_product(self, url: str) -> None:
        product = DummyCrawler()._build_product("Run", "Containers", url)

        assert product == CloudProduct(name="Run", description="Containers")


class PageCrawler(BaseCloudCrawler):
    """Crawler whose listing gives product links, the products being read on their pages."""

    name = "page-crawler"
    catalogue_url: ClassVar[str] = "https://catalogue.example.com/products/"

    def _page_title(self, title: str) -> str:
        return super()._page_title(title.removesuffix(" | Example"))


PRODUCT_URL = "https://catalogue.example.com/products/run/"


def product_page(
    head: str, body: str = "", url: str = PRODUCT_URL, meta: Optional[Dict[str, JsonValue]] = None
) -> Response:
    return Response(
        url=url,
        content=f"<html><head>{head}</head><body>{body}</body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta={BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL} if meta is None else meta,
    )


class TestProductPages:
    def test_request_marks_the_product_page(self) -> None:
        request = PageCrawler()._product_page_request(PRODUCT_URL)

        assert request is not None
        assert (request.url, request.priority, request.meta) == (
            PRODUCT_URL,
            0,
            {BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL},
        )

    def test_request_keeps_the_listed_name(self) -> None:
        request = PageCrawler()._product_page_request(PRODUCT_URL, "  Example   Run ")

        assert request is not None
        assert request.meta[BaseCloudCrawler.PRODUCT_NAME] == "Example Run"

    def test_blank_listed_name_is_ignored(self) -> None:
        request = PageCrawler()._product_page_request(PRODUCT_URL, " ")

        assert request is not None
        assert BaseCloudCrawler.PRODUCT_NAME not in request.meta

    def test_page_of_a_streamed_product_is_not_requested(self) -> None:
        crawler = PageCrawler()
        crawler.seen_urls.add(crawler._url_key(PRODUCT_URL))

        assert crawler._product_page_request("https://www.catalogue.example.com/products/run") is None

    async def test_reads_the_open_graph_title_and_the_description(self, crawl_page: CrawlPage) -> None:
        head = '<meta property="og:title" content="Run | Example"><meta name="Description" content="Serverless.">'

        results = await crawl_page(PageCrawler(), product_page(head, "<h1>Heading</h1>"))

        assert results == [{"name": "Run", "description": "Serverless.", "pricing_policy": [], "url": PRODUCT_URL}]

    async def test_falls_back_to_the_heading_and_the_open_graph_description(self, crawl_page: CrawlPage) -> None:
        head = '<meta property="og:description" content="Serverless."><meta name="description" content=" ">'

        results = await crawl_page(PageCrawler(), product_page(head, "<h1> Cloud <b>Run</b> </h1>"))

        assert results == [
            {"name": "Cloud Run", "description": "Serverless.", "pricing_policy": [], "url": PRODUCT_URL}
        ]

    async def test_listed_name_is_preferred(self, crawl_page: CrawlPage) -> None:
        meta: Dict[str, JsonValue] = {BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL, BaseCloudCrawler.PRODUCT_NAME: "Run"}
        head = '<meta property="og:title" content="Run: the serverless platform?"><meta name="description" content="X">'

        results = await crawl_page(PageCrawler(), product_page(head, meta=meta))

        assert [result["name"] for result in results if isinstance(result, dict)] == ["Run"]

    @pytest.mark.parametrize(
        "response",
        [
            product_page('<meta property="og:title" content="Run: what is serverless">'),
            product_page('<meta property="og:title" content="What is Run?">'),
            product_page('<meta name="description" content="No title.">'),
            product_page('<meta property="og:title" content="Run">', url="https://catalogue.example.com/products/"),
        ],
        ids=["article", "question", "untitled", "redirected"],
    )
    async def test_non_product_pages_are_skipped(self, crawl_page: CrawlPage, response: Response) -> None:
        assert await crawl_page(PageCrawler(), response) == []

    @pytest.mark.parametrize(
        ("url", "kept"),
        [
            ("https://catalogue.example.com/products/compute/run/", True),
            ("https://catalogue.example.com/", False),
            ("https://other.example.com/products/run/", False),
        ],
        ids=["moved", "home-page", "other-website"],
    )
    async def test_moved_page_of_a_listed_product(self, crawl_page: CrawlPage, url: str, kept: bool) -> None:
        meta: Dict[str, JsonValue] = {BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL, BaseCloudCrawler.PRODUCT_NAME: "Run"}
        head = '<meta name="description" content="Serverless.">'

        results = await crawl_page(PageCrawler(), product_page(head, url=url, meta=meta))

        expected = [{"name": "Run", "description": "Serverless.", "pricing_policy": [], "url": url}]
        assert results == (expected if kept else [])

    async def test_missing_page_is_skipped(self, crawl_page: CrawlPage) -> None:
        response = product_page('<meta property="og:title" content="Not found"><meta name="description" content="X">')
        response.status = 404

        assert await crawl_page(PageCrawler(), response) == []

    async def test_page_of_a_streamed_product_is_skipped(self, crawl_page: CrawlPage) -> None:
        crawler = PageCrawler()
        head = '<meta property="og:title" content="Run"><meta name="description" content="Serverless.">'

        first = await crawl_page(crawler, product_page(head))
        second = await crawl_page(crawler, product_page(head))

        assert (len(first), second) == (1, [])

    def test_meta_content_order_and_case(self) -> None:
        response = product_page(
            '<meta name="DESCRIPTION" content="First"><meta name="description" content="Second">'
            '<meta property="og:description" content="Open Graph"><meta content="No name">'
        )

        crawler = PageCrawler()

        assert crawler._meta_content(response, "og:description", "description") == "Open Graph"
        assert crawler._meta_content(response, "description") == "First"
        assert crawler._meta_content(response, "keywords") is None

    def test_request_carries_the_listed_categories(self) -> None:
        categories = ("Compute", "Serverless")

        request = PageCrawler()._product_page_request(PRODUCT_URL, "Run", categories=categories)

        assert request is not None
        assert request.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] == ["Compute", "Serverless"]
        assert isinstance(request.meta[BaseCloudCrawler.PRODUCT_CATEGORIES], list)

    @pytest.mark.parametrize("categories", [None, [], ()], ids=["none", "empty-list", "empty-tuple"])
    def test_request_without_categories_has_no_categories_meta(self, categories: Optional[List[str]]) -> None:
        request = PageCrawler()._product_page_request(PRODUCT_URL, "Run", categories=categories)

        assert request is not None
        assert BaseCloudCrawler.PRODUCT_CATEGORIES not in request.meta

    def test_request_categories_are_a_copy(self) -> None:
        categories = ["Compute"]

        request = PageCrawler()._product_page_request(PRODUCT_URL, categories=categories)
        categories.append("Storage")

        assert request is not None
        assert request.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] == ["Compute"]

    async def test_page_product_is_filed_under_the_request_categories(self, crawl_page: CrawlPage) -> None:
        meta: Dict[str, JsonValue] = {
            BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL,
            BaseCloudCrawler.PRODUCT_CATEGORIES: [" Compute ", "", "Serverless  Apps", "Compute"],
        }
        head = '<meta property="og:title" content="Run | Example"><meta name="description" content="Serverless.">'

        results = await crawl_page(PageCrawler(), product_page(head, meta=meta))

        assert results == [
            {
                "name": "Run",
                "description": "Serverless.",
                "pricing_policy": [],
                "url": PRODUCT_URL,
                "catalogue_categories": ["Compute", "Serverless Apps"],
            }
        ]

    @pytest.mark.parametrize("categories", [None, "Compute", []], ids=["missing", "not-a-list", "empty"])
    def test_page_product_without_request_categories(self, categories: JsonValue) -> None:
        meta: Dict[str, JsonValue] = {BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL}
        if categories is not None:
            meta[BaseCloudCrawler.PRODUCT_CATEGORIES] = categories
        head = '<meta property="og:title" content="Run"><meta name="description" content="Serverless.">'

        product = PageCrawler()._page_product(product_page(head, meta=meta))

        assert product is not None
        assert product.catalogue_categories == []

    async def test_requested_categories_reach_the_page_product(self, crawl_page: CrawlPage) -> None:
        crawler = PageCrawler()
        request = crawler._product_page_request(PRODUCT_URL, "Run", categories=["Compute"])
        assert request is not None
        head = '<meta name="description" content="Serverless.">'

        results = await crawl_page(crawler, product_page(head, meta=request.meta))

        assert [result["catalogue_categories"] for result in results if isinstance(result, dict)] == [["Compute"]]


def listed(name: str, url: Optional[str], *categories: str) -> CloudProduct:
    return CloudProduct(name=name, description=f"{name} description.", url=url, catalogue_categories=list(categories))


class TestMergeCategories:
    def test_occurrences_of_the_same_name_are_merged(self) -> None:
        products = [
            listed("Run", "https://catalogue.example.com/run", "Compute"),
            listed("run", "https://catalogue.example.com/other-run", "Serverless"),
        ]

        merged = PrefixedCrawler()._merge_categories(products)

        assert [(product.name, product.url, product.catalogue_categories) for product in merged] == [
            ("Run", "https://catalogue.example.com/run", ["Compute", "Serverless"])
        ]

    def test_occurrences_of_the_same_url_are_merged(self) -> None:
        products = [
            listed("Run", "https://catalogue.example.com/run/", "Compute"),
            listed("Cloud Run", "https://www.catalogue.example.com/run?ref=menu", "Containers"),
        ]

        merged = PageCrawler()._merge_categories(products)

        assert [(product.name, product.catalogue_categories) for product in merged] == [
            ("Run", ["Compute", "Containers"])
        ]

    def test_brand_prefix_is_ignored_when_matching_names(self) -> None:
        products = [listed("Example Run", None, "Compute"), listed("Run", None, "Serverless")]

        merged = PrefixedCrawler()._merge_categories(products)

        assert [(product.name, product.catalogue_categories) for product in merged] == [
            ("Example Run", ["Compute", "Serverless"])
        ]

    def test_first_occurrence_order_is_kept(self) -> None:
        products = [
            listed("Run", None, "Serverless"),
            listed("Store", None, "Storage"),
            listed("Run", None, "Compute", "Serverless"),
            listed("Queue", None),
            listed("Store", None, "Backup"),
        ]

        merged = PageCrawler()._merge_categories(products)

        assert [(product.name, product.catalogue_categories) for product in merged] == [
            ("Run", ["Serverless", "Compute"]),
            ("Store", ["Storage", "Backup"]),
            ("Queue", []),
        ]

    def test_distinct_products_are_kept_unchanged(self) -> None:
        products = [listed("Run", "https://catalogue.example.com/run", "Compute"), listed("Store", None)]

        merged = PageCrawler()._merge_categories(iter(products))

        assert merged == products

    def test_merged_product_is_validated(self) -> None:
        first = listed("Run", None, "Compute")
        again = CloudProduct.model_construct(
            name="Run", description="Run.", url=None, catalogue_categories=["  Serverless   Apps ", " ", "Compute"]
        )

        merged = PageCrawler()._merge_categories([first, again])

        assert merged[0].catalogue_categories == ["Compute", "Serverless Apps"]
        assert merged[0] is not first
        assert first.catalogue_categories == ["Compute"]

    def test_merged_product_keeps_its_other_fields(self) -> None:
        added = datetime(2024, 1, 2, tzinfo=UTC)
        first = CloudProduct(
            name="Run", description="Serverless.", url=PRODUCT_URL, added_at=added, catalogue_categories=["A"]
        )

        merged = PageCrawler()._merge_categories([first, listed("Run", None, "B")])

        assert merged[0].model_dump() == {**first.model_dump(), "catalogue_categories": ["A", "B"]}

    def test_invalid_merged_product_keeps_the_first_occurrence(self, caplog: pytest.LogCaptureFixture) -> None:
        first = CloudProduct.model_construct(name="Run", description="", url=None, catalogue_categories=["A"])

        with caplog.at_level(logging.WARNING):
            merged = PageCrawler()._merge_categories([first, listed("Run", None, "B")])

        assert merged == [first]
        assert "Keeping the categories of the first 'Run' listing" in caplog.text


class TestSitemap:
    def test_lists_the_pages_once(self) -> None:
        sitemap = (
            "<urlset><url><loc> https://example.com/a?x=1&amp;y=2 </loc></url>"
            "<url><loc><![CDATA[https://example.com/b]]></loc></url><url><loc>https://example.com/b</loc></url></urlset>"
        )

        assert PageCrawler()._sitemap_urls(page(sitemap, "https://example.com/sitemap.xml")) == [
            "https://example.com/a?x=1&y=2",
            "https://example.com/b",
        ]

    def test_empty_sitemap_is_an_error(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(CatalogueFormatError, match="lists no page"):
            PageCrawler()._sitemap_urls(page("<urlset></urlset>", "https://example.com/sitemap.xml"))

        assert any(record.levelname == "ERROR" for record in caplog.records)


class TestJsonBody:
    def test_reads_the_raw_body(self) -> None:
        assert PageCrawler()._json_body(page('{"products": [1]}')) == {"products": [1]}

    def test_rejects_a_page_which_is_not_json(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(CatalogueFormatError, match="is not JSON"):
            PageCrawler()._json_body(page("<html>Blocked</html>"))

        assert any(record.levelname == "ERROR" for record in caplog.records)


class TestWebsiteDates:
    def test_parse_date(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        crawler = PageCrawler()

        assert crawler._parse_date("2026-07-31T13:50:20.900074515-04:00") == datetime(
            2026, 7, 31, 17, 50, 20, 900074, tzinfo=UTC
        )
        assert crawler._parse_date(1792120332000) == datetime(2026, 10, 16, 3, 12, 12, tzinfo=UTC)
        assert crawler._parse_date("last week", "Run") is None
        assert "Ignoring the unreadable date 'last week' of the entry 'Run'." in caplog.messages

    def test_sitemap_entries_keep_the_last_modification(self) -> None:
        sitemap = (
            "<urlset><url><loc>https://example.com/a</loc><lastmod>2025-12-04T15:08:01+01:00</lastmod></url>"
            "<url><loc>https://example.com/b</loc></url>"
            "<url><loc>https://example.com/a</loc><lastmod>2020-01-01</lastmod></url></urlset>"
        )
        index = "<sitemapindex><sitemap><loc>https://example.com/s1.xml</loc><lastmod>2026-01-01</lastmod></sitemap>"

        crawler = PageCrawler()

        assert crawler._sitemap_entries(page(sitemap, "https://example.com/sitemap.xml")) == {
            "https://example.com/a": "2025-12-04T15:08:01+01:00",
            "https://example.com/b": None,
        }
        assert crawler._sitemap_entries(page(index, "https://example.com/sitemap.xml")) == {
            "https://example.com/s1.xml": "2026-01-01"
        }

    def test_request_carries_the_sitemap_date(self) -> None:
        request = PageCrawler()._product_page_request(PRODUCT_URL, updated="2025-12-04")

        assert request is not None
        assert request.meta[BaseCloudCrawler.PRODUCT_UPDATED] == "2025-12-04"

    async def test_page_dates(self, crawl_page: CrawlPage) -> None:
        head = (
            '<meta property="og:title" content="Run"><meta name="description" content="Serverless.">'
            '<meta property="article:published_time" content="2024-03-01T10:00:00Z">'
            '<meta name="cpp-last-modified-time" content="2022-12-13 21:03:56Z">'
        )

        results = await crawl_page(PageCrawler(), product_page(head))

        assert results == [
            {
                "name": "Run",
                "description": "Serverless.",
                "pricing_policy": [],
                "url": PRODUCT_URL,
                "added_at": "2024-03-01T10:00:00Z",
                "added_caveat": "page-published",
                "updated_at": "2022-12-13T21:03:56Z",
                "updated_caveat": "page-modified",
            }
        ]

    async def test_sitemap_date_is_preferred_to_the_page_one(self, crawl_page: CrawlPage) -> None:
        meta: Dict[str, JsonValue] = {
            BaseCloudCrawler.PRODUCT_PAGE: PRODUCT_URL,
            BaseCloudCrawler.PRODUCT_UPDATED: "2025-12-04T15:08:01+01:00",
        }
        head = (
            '<meta property="og:title" content="Run"><meta name="description" content="Serverless.">'
            '<meta property="article:modified_time" content="2020-01-01">'
        )

        results = await crawl_page(PageCrawler(), product_page(head, meta=meta))

        assert [result.get("updated_at") for result in results if isinstance(result, dict)] == ["2025-12-04T14:08:01Z"]


SITEMAP_URL = "https://catalogue.example.com/sitemap.xml"


class DatedCrawler(ListCrawler):
    """Crawler whose listing products are dated by the sitemap of their pages."""

    name = "dated-crawler"
    complement_urls: ClassVar[Tuple[str, ...]] = (SITEMAP_URL, "https://catalogue.example.com/more/")
    dates_sitemaps: ClassVar[Tuple[str, ...]] = (SITEMAP_URL,)

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        for line in response.body.decode().splitlines():
            name, _, url = line.partition("|")
            if product := self._build_product(name, f"{name} service", url or None):
                yield product


def sitemap_page(entries: List[Tuple[str, str]], status: int = 200) -> Response:
    urls = "".join(f"<url><loc>{url}</loc><lastmod>{lastmod}</lastmod></url>" for url, lastmod in entries)
    return Response(
        url=SITEMAP_URL,
        content=f"<urlset>{urls}</urlset>",
        status=status,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta={BaseCloudCrawler.PAGE_DATES: SITEMAP_URL},
    )


class TestSitemapDates:
    async def test_the_sitemaps_are_read_first_and_requested_again(self) -> None:
        requests = [request async for request in DatedCrawler().start_requests()]

        assert [(request.url, request.priority, request.dont_filter) for request in requests] == [
            (SITEMAP_URL, BaseCloudCrawler.DATES_PRIORITY, True),
            ("https://catalogue.example.com/products/", BaseCloudCrawler.PRIMARY_PRIORITY, False),
            (SITEMAP_URL, 0, True),
            ("https://catalogue.example.com/more/", 0, False),
        ]
        assert requests[0].meta == {BaseCloudCrawler.PAGE_DATES: SITEMAP_URL}

    async def test_listing_products_are_dated_by_their_page(self, crawl_page: CrawlPage) -> None:
        crawler = DatedCrawler()
        dated = [("https://www.catalogue.example.com/run/", "2025-12-04T15:08:01+01:00"), (PRODUCT_URL, "2024-01-02")]

        assert await crawl_page(crawler, sitemap_page(dated)) == []
        results = await crawl_page(
            crawler, page("Run|https://catalogue.example.com/run\nBatch|\nJobs|https://x.example/")
        )

        assert [
            (result.get("updated_at"), result.get("updated_caveat")) for result in results if isinstance(result, dict)
        ] == [
            ("2025-12-04T14:08:01Z", "page-modified"),
            (None, None),
            (None, None),
        ]

    async def test_sitemap_of_one_day_is_ignored(self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        crawler = DatedCrawler()
        entries = [(f"https://catalogue.example.com/p{index}/", "2026-10-16") for index in range(10)]

        await crawl_page(crawler, sitemap_page(entries))

        assert crawler.page_dates == {}
        assert any("dates its 10 pages 2026-10-16, its generation date" in message for message in caplog.messages)

    async def test_missing_sitemap(self, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
        crawler = DatedCrawler()

        assert await crawl_page(crawler, sitemap_page([], status=404)) == []
        assert "The dated-crawler sitemap https://catalogue.example.com/sitemap.xml is unavailable (HTTP 404)." in (
            caplog.messages
        )

    async def test_new_crawl_forgets_the_page_dates(self) -> None:
        crawler = DatedCrawler()
        crawler.page_dates["catalogue.example.com/run"] = "2024-01-02"

        await crawler.on_start()

        assert crawler.page_dates == {}


@pytest.mark.parametrize("value", ["0004-01-01T00:00:00Z", "1989-12-31", "2999-01-01"])
def test_implausible_dates_are_dropped(value: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    assert PageCrawler()._parse_date(value, "Run") is None
    assert any("Ignoring the implausible date" in message for message in caplog.messages)
