from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.yandex.marketplace import YandexMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
MARKETPLACE_URL = "https://yandex.cloud/en/marketplace"
SITEMAP_URL = "https://yandex.cloud/sitemap_main.xml"
PRODUCTS_URL = f"{MARKETPLACE_URL}/products"
LOGGER = "scrapling.spiders.yandex-marketplace"
STATE = re.compile(r"\n__DATA__ = (\{.*\});</script>", re.S)


@pytest.fixture(scope="module")
def crawler() -> YandexMarketplaceCrawler:
    return YandexMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: YandexMarketplaceCrawler) -> YandexMarketplaceCrawler:
    crawler.software_categories.clear()
    crawler.software_category_paths.clear()
    return crawler


def page(
    url: str, content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None, status: int = 200
) -> Response:
    return Response(
        url=url,
        content=content,
        status=status,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
        meta=meta or {},
    )


def fixture_page(url: str, fixture: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return page(url, (FIXTURES / fixture).read_bytes(), meta)


def product_page(slug: str, fixture: str) -> Response:
    url = f"{PRODUCTS_URL}/{slug}"
    return fixture_page(url, fixture, {"product": url, "may_be_empty": True})


def state_page(data: JsonValue, url: str = MARKETPLACE_URL, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    state = json.dumps({"err": None, "props": {"pageProps": {"data": data}}, "context": {}})
    return page(url, f"<html><body><script>window.__DATA__ = {{}};</script><script>__DATA__ = {state};</script>", meta)


def fixture_product(fixture: str) -> Dict[str, JsonValue]:
    match = STATE.search((FIXTURES / fixture).read_text(encoding="utf-8"))
    assert match is not None
    product = json.loads(match.group(1))["props"]["pageProps"]["data"]
    assert isinstance(product, dict)
    return product


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: YandexMarketplaceCrawler) -> None:
    assert crawler.name == "yandex-marketplace"
    assert YandexMarketplaceCrawler.catalogue_url == MARKETPLACE_URL
    assert YandexMarketplaceCrawler.complement_urls == (SITEMAP_URL,)
    assert crawler.allowed_domains == {"yandex.cloud"}
    assert crawler.robots_txt_obey is True


def test_pages_are_read_by_an_http_session_naming_the_crawler(crawler: YandexMarketplaceCrawler) -> None:
    manager = SessionManager()

    crawler.configure_sessions(manager)

    assert manager.session_ids == ["yandex-marketplace-session", "yandex-marketplace-http"]
    assert manager.default_session_id == "yandex-marketplace-http"
    session = manager.get("yandex-marketplace-http")
    assert isinstance(session, FetcherSession)
    assert session._default_headers == {"User-Agent": "Mozilla/5.0 (compatible; poc-crawler/0.1.0)"}
    assert (session._default_impersonate, session._stealth) == ("chrome", False)


async def test_start_requests_read_the_home_page_then_the_sitemap(crawler: YandexMarketplaceCrawler) -> None:
    starts = [request async for request in crawler.start_requests()]

    assert [(request.url, request.priority, request.sid) for request in starts] == [
        (MARKETPLACE_URL, 10, ""),
        (SITEMAP_URL, 0, "yandex-marketplace-http"),
    ]
    assert starts[1].meta == {"sitemap": True}


async def test_extracts_the_home_page_software(fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page(MARKETPLACE_URL, "yandex_marketplace.html"))

    assert names(results) == [
        "Neurolegal",
        "SPM server based on Windows Server 2025 Standard",
        "SPM terminal server Windows Server 2025 Standard RDS 50",
        "SPM terminal server Windows Server 2025 Standard RDS 10",
        "Ubuntu 24.04 LTS",
        "Ubuntu 24.04 LTS",
        "LAMP",
    ]
    assert items(results)[0] == {
        "name": "Neurolegal",
        "description": (
            "Neurolegal is a Yandex GPT\u2013based AI assistant for lawyers that helps select legal frameworks, "
            "answers questions, and saves time on routine tasks.."
        ),
        "publisher": "Yandex Cloud",
        "url": f"{PRODUCTS_URL}/yc/neurolegal",
        "delivery": "saas",
        "marketplace_categories": ["AI Agents", "Business applications", "ML & AI", "Yandex services"],
        "marketplace_category_paths": [
            {"path": ["AI Agents"], "id": "ai-agents"},
            {"path": ["Business applications"], "id": "business-apps"},
            {"path": ["ML & AI"], "id": "ml-and-ai"},
            {"path": ["Yandex services"], "id": "yandex-services"},
        ],
        "categories": ["developer-tool", "end-user-software"],
        "added_at": "2025-10-20T15:36:39Z",
        "updated_at": "2026-03-31T14:25:33Z",
        "updated_caveat": "catalogue-entry",
    }
    assert requests(results) == []


async def test_selections_are_not_categories(fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page(MARKETPLACE_URL, "yandex_marketplace.html"))

    server = items(results)[1]
    assert server["url"] == f"{PRODUCTS_URL}/skservice/spmwinst2025"
    assert server["marketplace_categories"] == ["Operation systems"]
    assert server["marketplace_category_paths"] == [{"path": ["Operation systems"], "id": "os"}]
    labels = [item["marketplace_categories"] for item in items(results)]
    assert all(isinstance(listed, list) for listed in labels)
    assert not {str(label) for listed in labels if isinstance(listed, list) for label in listed} & {
        "Recommended",
        "New arrivals",
    }


async def test_software_shown_by_several_selections_is_streamed_once(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    product = fixture_product("yandex_product_cisco_asav.html")
    home: Dict[str, JsonValue] = {
        "categories": [
            {"name": "recommended", "title": "Recommended", "products": [product]},
            {"name": "network", "title": "Network infrastructure", "products": [product]},
            {"name": "security", "title": "Security", "products": [product]},
        ]
    }

    results = await crawl_page(fresh, state_page(home))

    assert names(results) == ["Cisco ASAv firewall"]
    assert items(results)[0]["marketplace_categories"] == ["Network infrastructure", "Security"]


@pytest.mark.parametrize(
    ("kind", "delivery"),
    [
        ("COMPUTE_IMAGE", "virtual-machine"),
        ("BAREMETAL", "virtual-machine"),
        ("BAREMETAL_EXTEND", "virtual-machine"),
        ("COS", "container"),
        ("K8S", "kubernetes"),
        ("SAAS", "saas"),
        ("CLOUD_APP", "one-click-app"),
        ("DATALENS_TEMPLATE", "other"),
        ("DATALENS_CONNECTOR", "other"),
    ],
)
async def test_delivery_follows_the_product_type(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, kind: str, delivery: str
) -> None:
    product = {**fixture_product("yandex_product_llm_box_base.html"), "type": kind}

    results = await crawl_page(fresh, state_page({"categories": [{"name": "ml-and-ai", "products": [product]}]}))

    assert [item["delivery"] for item in items(results)] == [delivery]


async def test_sitemap_requests_the_product_pages_not_streamed_yet(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    await crawl_page(fresh, fixture_page(MARKETPLACE_URL, "yandex_marketplace.html"))

    results = await crawl_page(fresh, fixture_page(SITEMAP_URL, "yandex_sitemap_main.xml", {"sitemap": True}))

    assert [request.url for request in requests(results)] == [
        f"{PRODUCTS_URL}/papadata/llm-box-base",
        f"{PRODUCTS_URL}/cisco/cisco-asav-firewall",
        f"{PRODUCTS_URL}/yandex/sample-superstore",
    ]
    assert items(results) == []
    request = requests(results)[0]
    assert (request.sid, request.priority) == ("yandex-marketplace-http", 0)
    assert request.meta == {"product": f"{PRODUCTS_URL}/papadata/llm-box-base", "may_be_empty": True}


async def test_page_limit_stops_the_product_pages(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    with (
        patch.object(YandexMarketplaceCrawler, "page_limit", 2),
        patch.object(YandexMarketplaceCrawler, "DETAILS_PER_PAGE", 1),
    ):
        results = await crawl_page(fresh, fixture_page(SITEMAP_URL, "yandex_sitemap_main.xml", {"sitemap": True}))

    assert [request.url for request in requests(results)] == [
        f"{PRODUCTS_URL}/papadata/llm-box-base",
        f"{PRODUCTS_URL}/yc/neurolegal",
    ]
    assert any("Page limit (2) reached: 2 product pages not requested." in record.message for record in caplog.records)


async def test_extracts_the_software_of_a_product_page(fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, product_page("papadata/llm-box-base", "yandex_product_llm_box_base.html"))

    assert items(results) == [
        {
            "name": "LLM-Box Base — Private AI (Qwen3-8B) in Your Cloud",
            "description": (
                "A ready-to-run private AI server: Qwen3-8B language model, OpenAI-compatible API and a ChatGPT-style "
                "web UI. One-click deployment on an NVIDIA T4 GPU VM. Your data stays in your cloud."
            ),
            "publisher": "PAPA DATA",
            "url": f"{PRODUCTS_URL}/papadata/llm-box-base",
            "delivery": "virtual-machine",
            "marketplace_categories": ["ML & AI"],
            "marketplace_category_paths": [{"path": ["ML & AI"], "id": "ml-and-ai"}],
            "categories": ["developer-tool", "end-user-software"],
            "added_at": "2026-08-03T10:02:04Z",
            "updated_at": "2026-08-12T08:41:29Z",
            "updated_caveat": "catalogue-entry",
        }
    ]
    assert requests(results) == []


async def test_description_falls_back_to_the_first_paragraph(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, product_page("cisco/cisco-asav-firewall", "yandex_product_cisco_asav.html"))

    (software,) = items(results)
    assert software["description"] == (
        "Cisco ASA firewalls help find balance between security and performance. This solution includes a set of "
        "network security services and provides:"
    )
    assert (software["publisher"], software["marketplace_categories"]) == (
        "Cisco",
        ["Network infrastructure", "Security"],
    )


async def test_datasets_are_not_software(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    results = await crawl_page(fresh, product_page("yandex/sample-superstore", "yandex_product_sample_superstore.html"))

    assert results == []
    assert "Skipping the yandex-marketplace product 'Sample Superstore', not a software (type DATALENS_DATASET)." in (
        caplog.messages
    )


async def test_missing_product_page_holds_nothing(fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    url = f"{PRODUCTS_URL}/yc/retired"

    results = await crawl_page(fresh, page(url, "<html></html>", {"product": url, "may_be_empty": True}, status=404))

    assert results == []


async def test_invalid_products_are_skipped(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    valid = fixture_product("yandex_product_llm_box_base.html")
    home: Dict[str, JsonValue] = {
        "categories": [
            {
                "name": "ml-and-ai",
                "products": [
                    {**valid, "marketingInfo": {"name": "  ", "shortDescription": "No name"}},
                    {**valid, "name": "x/no-description", "marketingInfo": {"name": "No description"}},
                    {
                        **valid,
                        "categories": "none",
                        "publisher": None,
                        "createdAt": "someday",
                        "name": None,
                        "id": None,
                    },
                    "not a product",
                ],
            },
            "not a selection",
        ]
    }
    caplog.set_level(logging.WARNING, logger=LOGGER)

    results = await crawl_page(fresh, state_page(home))

    assert [(item["name"], item["url"], item["publisher"]) for item in items(results)] == [
        ("LLM-Box Base — Private AI (Qwen3-8B) in Your Cloud", None, None)
    ]
    assert "added_at" not in items(results)[0]
    assert "marketplace_category_paths" not in items(results)[0]
    warnings = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert len([message for message in warnings if "Skipping the invalid marketplace entry" in message]) == 3
    assert any("Skipping the invalid marketplace entry 'No description'" in message for message in warnings)


async def test_empty_home_page_is_an_error(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError, match="no product found"):
        await crawl_page(fresh, state_page({"categories": [{"name": "os", "products": []}]}))

    assert any(record.levelname == "ERROR" and "holds no software" in record.message for record in caplog.records)


async def test_page_without_state_is_an_error(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="page state is missing"):
        await crawl_page(fresh, page(MARKETPLACE_URL, "<html><script>window.__DATA__ = {};</script></html>"))

    assert any(record.levelname == "ERROR" and "embeds no page state" in record.message for record in caplog.records)


async def test_captcha_is_an_error(
    fresh: YandexMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    captcha = page("https://yandex.cloud/showcaptchafast?d=1E4B&retpath=aHR0", "<html><title>Captcha</title></html>")

    with pytest.raises(CatalogueFormatError, match="the page is a captcha"):
        await crawl_page(fresh, captcha)

    assert any(
        record.levelname == "ERROR" and "redirected to the captcha" in record.message for record in caplog.records
    )
