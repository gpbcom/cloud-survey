from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.oracle.crawler import OracleCloudCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CLOUD_URL = "https://www.oracle.com/cloud/"
TOC_URL = "https://docs.oracle.com/en-us/iaas/toc.json"
QUEUE_URL = "https://www.oracle.com/cloud/queue/"
DOCS_URL = "https://docs.oracle.com/en-us/iaas/Content/artifacts/home.htm"
PANEL = '<section class="rc105" data-lbl="oci-marchitecture:"><div class="rc105w1"></div>{}</section>'


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None, status: int = 200) -> Response:
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


def product_page(url: str, name: str, head: str = "", body: str = "", status: int = 200) -> Response:
    content = f"<html><head>{head}</head><body>{body}</body></html>"
    meta: Dict[str, JsonValue] = {OracleCloudCrawler.PRODUCT_PAGE: url, OracleCloudCrawler.PRODUCT_NAME: name}
    return page(url, content, meta, status)


def panel(*links: Tuple[str, str]) -> Response:
    items = "".join(f'<li><a href="{href}">{name}</a></li>' for name, href in links)
    return page(CLOUD_URL, PANEL.format(f'<div class="rc105w1"><ul class="rc105linklist">{items}</ul></div>'))


def requested(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Tuple[str, JsonValue]]:
    return [
        (result.url, result.meta.get(OracleCloudCrawler.PRODUCT_NAME))
        for result in results
        if isinstance(result, Request)
    ]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = OracleCloudCrawler()

    assert crawler.name == "oracle"
    assert OracleCloudCrawler.catalogue_url == CLOUD_URL
    assert OracleCloudCrawler.complement_urls == (TOC_URL,)
    assert crawler.allowed_domains == {"www.oracle.com", "docs.oracle.com"}
    assert OracleCloudCrawler.name_prefixes == ("Oracle Cloud Infrastructure ", "OCI ", "Oracle ")


async def test_starts_with_the_cloud_page_then_the_documentation() -> None:
    requests = [request async for request in OracleCloudCrawler().start_requests()]

    assert [(request.url, request.priority) for request in requests] == [
        (CLOUD_URL, OracleCloudCrawler.PRIMARY_PRIORITY),
        (TOC_URL, -1),
    ]


async def test_panel_requests_the_product_pages(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(OracleCloudCrawler(), make_response(CLOUD_URL, "oracle_cloud.html"))

    assert requested(results) == [
        ("https://www.oracle.com/cloud/cloud-native/api-management/", "API Gateway"),
        ("https://www.oracle.com/cloud/cloud-native/devops-service/", "DevOps"),
        (QUEUE_URL, "Queue"),
        ("https://www.oracle.com/cloud/streaming/", "Streaming"),
        (
            "https://www.oracle.com/artificial-intelligence/generative-ai/generative-ai-service/",
            "Generative AI Service",
        ),
        ("https://www.oracle.com/artificial-intelligence/speech/", "Speech"),
        ("https://www.oracle.com/cloud/storage/block-volumes/", "Block Volumes"),
        ("https://www.oracle.com/cloud/storage/object-storage/", "Object Storage"),
        ("https://www.oracle.com/cloud/networking/dns/", "DNS Management"),
        ("https://www.oracle.com/cloud/networking/load-balancing/", "Load Balancers"),
        ("https://www.oracle.com/security/cloud-security/bastion/", "Bastion"),
    ]
    assert all(isinstance(result, Request) and result.priority == 0 for result in results)


async def test_panel_requests_carry_the_drawer_and_group_headings(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(OracleCloudCrawler(), make_response(CLOUD_URL, "oracle_cloud.html"))

    categories = {
        result.meta[OracleCloudCrawler.PRODUCT_NAME]: result.meta[BaseCloudCrawler.PRODUCT_CATEGORIES]
        for result in results
        if isinstance(result, Request)
    }
    assert categories["Queue"] == ["Developer Services", "Build and run"]
    assert categories["Generative AI Service"] == ["AI and Machine Learning", "Generative AI"]
    assert categories["Object Storage"] == ["Storage"]
    assert categories["Bastion"] == [
        "Security, Observability and Management, Compliance, and Cost Management and Governance",
        "Cloud Infrastructure Security",
    ]


async def test_panel_merges_the_categories_of_every_drawer_listing_a_product(crawl_page: CrawlPage) -> None:
    drawer = (
        '<div class="rc105w3"><h3>{drawer}</h3><div class="rc105w4"><div class="rc105w5"><h4>{group}</h4>'
        '<ul class="rc105linklist"><li><a href="{href}">{name}</a></li></ul></div></div></div>'
    )
    drawers = drawer.format(drawer="Developer Services", group="Build and run", href="/cloud/queue/", name="Queue")
    drawers += drawer.format(drawer="Integration", group="Messaging", href="/cloud/queue", name="OCI Queue")
    drawers += drawer.format(drawer="Developer Services", group="Build and run", href="/cloud/queue/", name="Queue")

    results = await crawl_page(
        OracleCloudCrawler(), page(CLOUD_URL, PANEL.format(f'<div class="rc105w1">{drawers}</div>'))
    )

    assert [
        (result.url, result.meta[BaseCloudCrawler.PRODUCT_CATEGORIES])
        for result in results
        if isinstance(result, Request)
    ] == [(QUEUE_URL, ["Developer Services", "Build and run", "Integration", "Messaging"])]


@pytest.mark.parametrize(
    "excluded",
    [
        "API Management",
        "Oracle Fusion CX Analytics",
        "Oracle Analytics mobile app",
        "Generative AI Capabilities",
        "AI Services",
        "Customer-Premises Equipment",
        "Budget",
        "Oracle Cloud Compliance",
        "Oracle Corporate Security",
        "Privacy",
        "Multicloud solutions",
        "Global cloud regions",
        "Oracle EU Sovereign Cloud",
        "US FedRAMP regions",
        "Alloy",
    ],
)
async def test_panel_non_products_are_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(OracleCloudCrawler(), make_response(CLOUD_URL, "oracle_cloud.html"))

    assert excluded not in [name for _, name in requested(results)]


@pytest.mark.parametrize(
    "name", ["Hybrid cloud solutions", "Global cloud regions", "Oracle EU Sovereign Cloud", "Machine Learning Services"]
)
async def test_panel_regions_solutions_and_overviews_are_skipped(crawl_page: CrawlPage, name: str) -> None:
    results = await crawl_page(OracleCloudCrawler(), panel((name, "/cloud/overview/"), ("Bastion", "/bastion/")))

    assert requested(results) == [("https://www.oracle.com/bastion/", "Bastion")]


async def test_panel_lists_each_product_once(crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        OracleCloudCrawler(), panel(("Streaming", "/cloud/streaming/"), ("Streaming", "/cloud/cloud-native/streaming/"))
    )

    assert requested(results) == [("https://www.oracle.com/cloud/streaming/", "Streaming")]


async def test_panel_skips_the_products_already_streamed(crawl_page: CrawlPage) -> None:
    crawler = OracleCloudCrawler()
    await crawl_page(crawler, product_page(QUEUE_URL, "Queue", '<meta name="Description" content="Messaging.">'))

    results = await crawl_page(crawler, panel(("Queue", "/cloud/queue/"), ("Bastion", "/security/bastion/")))

    assert requested(results) == [("https://www.oracle.com/security/bastion/", "Bastion")]


@pytest.mark.parametrize(
    "content",
    [
        "<html><body>No panel</body></html>",
        '<section class="rc105" data-lbl="oci-marchitecture:"><div class="rc105w1"></div></section>',
        PANEL.format('<div class="rc105w1"><ul class="rc105linklist"></ul></div>'),
    ],
    ids=["no-panel", "no-services-block", "no-link"],
)
async def test_panel_without_links_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no link"):
        await crawl_page(OracleCloudCrawler(), page(CLOUD_URL, content))

    assert [record.levelno for record in caplog.records if record.levelno >= logging.ERROR] == [logging.ERROR]
    assert CLOUD_URL in caplog.records[-1].getMessage()


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(QUEUE_URL, "oracle_product_page.html")
    response.meta.update({OracleCloudCrawler.PRODUCT_PAGE: QUEUE_URL, OracleCloudCrawler.PRODUCT_NAME: "Queue"})

    results = await crawl_page(OracleCloudCrawler(), response)

    assert results == [
        {
            "name": "Queue",
            "description": "A serverless messaging solution for asynchronous, secure, guaranteed message delivery. "
            "Queue includes the ability to send and receive messages using REST and STOMP.",
            "pricing_policy": [],
            "url": QUEUE_URL,
        }
    ]


async def test_product_page_is_filed_under_the_categories_of_its_request(crawl_page: CrawlPage) -> None:
    response = product_page(QUEUE_URL, "Queue", '<meta name="Description" content="Messaging.">')
    response.meta[BaseCloudCrawler.PRODUCT_CATEGORIES] = ["Developer Services", "Build and run"]

    results = await crawl_page(OracleCloudCrawler(), response)

    assert results == [
        {
            "name": "Queue",
            "description": "Messaging.",
            "pricing_policy": [],
            "url": QUEUE_URL,
            "catalogue_categories": ["Developer Services", "Build and run"],
        }
    ]


async def test_documentation_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(DOCS_URL, "oracle_docs_page.html")
    response.meta.update(
        {OracleCloudCrawler.PRODUCT_PAGE: DOCS_URL, OracleCloudCrawler.PRODUCT_NAME: "Artifact Registry"}
    )

    results = await crawl_page(OracleCloudCrawler(), response)

    assert results == [
        {
            "name": "Artifact Registry",
            "description": "Artifact Registry is a repository service for storing, sharing, and managing software "
            "development packages.",
            "pricing_policy": [],
            "url": DOCS_URL,
            "updated_at": "2022-12-13T21:03:56Z",
            "updated_caveat": "page-modified",
        }
    ]


async def test_documentation_landing_page_first_paragraph_fallback(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    url = "https://docs.oracle.com/en-us/iaas/ai-data-platform/index.html"
    response = make_response(url, "oracle_docs_landing.html")
    response.meta.update({OracleCloudCrawler.PRODUCT_PAGE: url, OracleCloudCrawler.PRODUCT_NAME: "AI Data Platform"})

    results = await crawl_page(OracleCloudCrawler(), response)

    assert names(results) == ["AI Data Platform"]
    assert isinstance(results[0], dict)
    assert str(results[0]["description"]).startswith("Oracle AI Data Platform is an intelligent data platform")


async def test_missing_product_page_is_skipped(crawl_page: CrawlPage) -> None:
    head = '<meta name="Title" content="Page not found | Oracle"><meta name="Description" content="We can\'t find it">'
    response = product_page(
        "https://www.oracle.com/cloud/networking/load-balancing/", "Load Balancers", head, status=404
    )

    assert await crawl_page(OracleCloudCrawler(), response) == []


async def test_documentation_page_short_description_fallback(crawl_page: CrawlPage) -> None:
    body = '<h1>Batch</h1><p class="shortdesc">\n  Run batch   jobs at scale.\n</p>'

    results = await crawl_page(OracleCloudCrawler(), product_page(DOCS_URL, "Batch", body=body))

    assert results == [
        {"name": "Batch", "description": "Run batch jobs at scale.", "pricing_policy": [], "url": DOCS_URL}
    ]


@pytest.mark.parametrize("body", ["<h1>Batch</h1>", '<p class="shortdesc"> </p>'], ids=["none", "empty"])
async def test_page_without_description_is_skipped(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, body: str
) -> None:
    results = await crawl_page(OracleCloudCrawler(), product_page(DOCS_URL, "Batch", body=body))

    assert results == []
    assert [record.levelno for record in caplog.records if record.levelno >= logging.WARNING] == [logging.WARNING]


async def test_documentation_requests_the_services(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(OracleCloudCrawler(), make_response(TOC_URL, "oracle_toc.json"))

    assert requested(results) == [
        ("https://docs.oracle.com/en-us/iaas/analytics-cloud/index.html", "Analytics Cloud"),
        ("https://docs.oracle.com/en-us/iaas/Content/APIGateway/home.htm", "API Gateway"),
        (DOCS_URL, "Artifact Registry"),
        ("https://docs.oracle.com/en-us/iaas/Content/Block/home.htm", "Block Volume"),
        ("https://docs.oracle.com/en-us/iaas/Content/Balance/home.htm", "Load Balancer"),
        ("https://docs.oracle.com/en/cloud/paas/goldengate-service/index.html", "OCI GoldenGate"),
        ("https://docs.oracle.com/en/database/oracle/apex/26.1/index.html", "Oracle APEX"),
        ("https://docs.oracle.com/en-us/iaas/Content/queue/home.htm", "Queue"),
        ("https://docs.oracle.com/en-us/iaas/Content/search-opensearch/home.htm", "Search with OpenSearch"),
        ("https://docs.oracle.com/en-us/iaas/Content/KeyManagement/home.htm", "Vault"),
    ]


async def test_documentation_skips_the_services_already_streamed(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = OracleCloudCrawler()
    description = '<meta name="Description" content="A service.">'
    for name, url in [
        ("API Gateway", "https://www.oracle.com/cloud/cloud-native/api-management/"),
        ("Block Volumes", "https://www.oracle.com/cloud/storage/block-volumes/"),
        ("Queue", QUEUE_URL),
        ("Artifacts", DOCS_URL),
    ]:
        assert names(await crawl_page(crawler, product_page(url, name, description))) == [name]

    results = await crawl_page(crawler, make_response(TOC_URL, "oracle_toc.json"))

    assert [name for _, name in requested(results)] == [
        "Analytics Cloud",
        "Load Balancer",
        "OCI GoldenGate",
        "Oracle APEX",
        "Search with OpenSearch",
        "Vault",
    ]


async def test_documentation_entries_without_page_or_saas_are_skipped(crawl_page: CrawlPage) -> None:
    toc: JsonValue = {
        "tree": [
            "not a node",
            {"i": "root", "c": [{"i": "no-path"}, {"i": "no-base"}, "not a node", {"i": "fdi"}, {"i": "batch"}]},
        ],
        "pages": {
            "root": {"p": "Content/services.htm", "t": "Infrastructure Services", "s": 1},
            "no-path": {"t": "No path", "s": 1},
            "no-base": {"p": "home.htm", "t": "No base", "s": 404},
            "fdi": {"p": "index.html", "t": "Fusion Data Intelligence", "s": 2},
            "batch": {"p": "oci-batch/home.htm", "t": "Batch", "s": 2},
        },
        "sourceBasepaths": {"1": "/iaas", "2": "/iaas/Content/"},
    }

    results = await crawl_page(OracleCloudCrawler(), page(TOC_URL, json.dumps(toc)))

    assert requested(results) == [("https://docs.oracle.com/en-us/iaas/Content/oci-batch/home.htm", "Batch")]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("<html>Not JSON</html>", "not JSON"),
        ("[]", "section is missing"),
        ('{"tree": {}, "pages": {}}', "section is missing"),
        ('{"tree": [{"i": "a"}], "pages": {"a": {"t": "Getting Started"}}}', "section is missing"),
        ('{"tree": [{"i": "a"}], "pages": {"a": {"t": "Infrastructure Services"}}}', "section is missing"),
    ],
    ids=["not-json", "not-object", "no-tree", "no-section", "no-children"],
)
async def test_invalid_table_of_contents_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str, reason: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(OracleCloudCrawler(), page(TOC_URL, content))

    assert [record.levelno for record in caplog.records if record.levelno >= logging.ERROR] == [logging.ERROR]
    assert TOC_URL in caplog.records[-1].getMessage()
