from __future__ import annotations

import html
import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.alibaba.crawler import AlibabaCloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
NAV_URL = (
    "https://file-intl.alicdn.com/stmt/2/alibabacloud/product/navigation_product_tree/aggregation-product/1.0/en.json"
)
PRODUCTS_URL = "https://www.alibabacloud.com/en/product"
HELP_URL = "https://www.alibabacloud.com/help/en/"
SITEMAP_URL = "https://www.alibabacloud.com/sitemaps/en/product/sitemap.xml"
AGENTCORE_URL = "https://www.alibabacloud.com/en/product/agentcore"
EPG_URL = "https://www.alibabacloud.com/help/en/epg/"
BOILERPLATE = "Learn from Alibaba Cloud experts about EPG product information, API, purchasing guide and FAQs."


def page(url: str, content: str, meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def nav_page(data: JsonValue) -> Response:
    return page(NAV_URL, json.dumps(data))


def cards_page(sections: JsonValue) -> Response:
    data = html.escape(json.dumps({"content": sections}), quote=True)
    return page(PRODUCTS_URL, f'<html><body><div class="render-container-data" data-data="{data}"></div></body></html>')


def product_page(
    url: str, title: str, description: str = "A product.", requested: str = AGENTCORE_URL, body: str = ""
) -> Response:
    head = f'<title>{title}</title><meta name="description" content="{description}">'
    return page(
        url, f"<html><head>{head}</head><body>{body}</body></html>", {AlibabaCloudCrawler.PRODUCT_PAGE: requested}
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


async def crawl_listings(crawler: AlibabaCloudCrawler, make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    await crawl_page(crawler, make_response(NAV_URL, "alibaba_nav_product_tree_en.json"))
    await crawl_page(crawler, make_response(f"{PRODUCTS_URL}?_p_lc=1", "alibaba_products_en.html"))


def test_configuration() -> None:
    crawler = AlibabaCloudCrawler()

    assert crawler.name == "alibaba"
    assert AlibabaCloudCrawler.catalogue_url == NAV_URL
    assert AlibabaCloudCrawler.complement_urls == (PRODUCTS_URL, HELP_URL)
    assert crawler.allowed_domains == {"file-intl.alicdn.com", "www.alibabacloud.com"}
    assert AlibabaCloudCrawler.name_prefixes == ("Alibaba Cloud ", "Alibaba ", "ApsaraDB for ", "ApsaraDB ", "Apsara ")
    assert (crawler.help_names, crawler.deprecated_names, crawler.category_urls) == ({}, set(), set())


async def test_starts_with_the_product_tree_then_waits_for_the_documentation() -> None:
    started = [request async for request in AlibabaCloudCrawler().start_requests()]

    assert [(request.url, request.priority) for request in started] == [
        (NAV_URL, AlibabaCloudCrawler.PRIMARY_PRIORITY),
        (PRODUCTS_URL, 0),
        (HELP_URL, 1),
    ]
    assert "wait_selector" not in started[1]._session_kwargs
    assert started[2]._session_kwargs["wait_selector"] == '[class*="ProductList--subNodeContent"] a'


async def test_extracts_the_product_tree(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = AlibabaCloudCrawler()

    results = await crawl_page(crawler, make_response(NAV_URL, "alibaba_nav_product_tree_en.json"))

    assert names(results) == [
        "Elastic Compute Service (ECS)",
        "Elastic GPU Service",
        "ECS Bare Metal Instance",
        "Elastic Container Instance (ECI)",
        "Function Compute (FC)",
        "Serverless App Engine (SAE)",
        "Alibaba Cloud Model Studio",
        "Platform for AI (PAI)",
        "DashVector",
        "AIRec",
        "Domain Names and Website",
        "Alibaba Cloud DNS (DNS)",
        "GoChina ICP Filing Assistant",
        "WHOIS",
    ]
    assert results[0] == {
        "name": "Elastic Compute Service (ECS)",
        "description": "Host your website and scale enterprise workloads anywhere",
        "pricing_policy": [],
        "url": "https://www.alibabacloud.com/product/ecs",
    }
    assert crawler.category_urls == {"alibabacloud.com/product/computing"}


@pytest.mark.parametrize("excluded", ["Cloud Server", "Elasticity Assurance", "Product Map", "Featured Products"])
async def test_product_tree_ads_and_featured_entries_are_left_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(AlibabaCloudCrawler(), make_response(NAV_URL, "alibaba_nav_product_tree_en.json"))

    assert not [name for name in names(results) if str(name).startswith(excluded)]


async def test_product_tree_shapes(crawl_page: CrawlPage) -> None:
    tree: JsonValue = {
        "detailedCategories": [
            "not a category",
            {"name": "Storage", "products": None, "subCategories": None},
            {
                "name": "Computing",
                "products": ["not a product", {"name": "", "shortDesc": "Nameless"}],
                "subCategories": [{"products": [{"name": "Gateway", "shortDesc": "NAT", "url": "/product/nat"}]}],
            },
        ]
    }

    results = await crawl_page(AlibabaCloudCrawler(), nav_page(tree))

    assert results == [{"name": "Gateway", "description": "NAT", "pricing_policy": [], "url": None}]


@pytest.mark.parametrize("data", [{"detailedCategories": {}}, {}, []], ids=["object", "missing", "list"])
async def test_product_tree_without_categories_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, data: JsonValue
) -> None:
    with pytest.raises(CatalogueFormatError, match="`detailedCategories` is not a list"):
        await crawl_page(AlibabaCloudCrawler(), nav_page(data))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The alibaba product tree {NAV_URL} has no `detailedCategories` list."


async def test_product_tree_not_json_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="not JSON"):
        await crawl_page(AlibabaCloudCrawler(), page(NAV_URL, "<html>Access denied</html>"))

    assert caplog.records[-1].levelno == logging.ERROR


async def test_product_tree_without_product_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(AlibabaCloudCrawler(), nav_page({"detailedCategories": []}))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The alibaba catalogue page {NAV_URL} holds no product."


async def test_cards_complete_the_product_tree(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = AlibabaCloudCrawler()
    await crawl_page(crawler, make_response(NAV_URL, "alibaba_nav_product_tree_en.json"))

    results = await crawl_page(crawler, make_response(f"{PRODUCTS_URL}?_p_lc=1", "alibaba_products_en.html"))

    assert names(results) == [
        "Simple Application Server",
        "Super Computing Cluster",
        "Batch Compute",
        "Server Load Balancer",
        "Dynamic Content Delivery Network",
        "PolarDB-X",
        "ApsaraDB RDS for MySQL",
        "Time Series Database",
        "AnalyticDB for PostgreSQL",
        "Anti-Bot Service",
    ]
    assert results[1] == {
        "name": "Super Computing Cluster",
        "description": "Parallel computing on a RDMA network",
        "pricing_policy": [],
        "url": "https://www.alibabacloud.com/en/product/scc",
    }


async def test_cards_deprecated_in_the_documentation_are_left_out(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = AlibabaCloudCrawler()
    crawler.deprecated_names.add("batchcompute")

    results = await crawl_page(crawler, make_response(PRODUCTS_URL, "alibaba_products_en.html"))

    assert "Batch Compute" not in names(results)
    assert "Super Computing Cluster" in names(results)


@pytest.mark.parametrize("excluded", ["Secure Content Delivery", "ACA Cloud Computing Certification"])
async def test_cards_solutions_and_academy_are_left_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    results = await crawl_page(AlibabaCloudCrawler(), make_response(PRODUCTS_URL, "alibaba_products_en.html"))

    assert excluded not in names(results)


async def test_card_shapes(crawl_page: CrawlPage) -> None:
    sections: JsonValue = [
        "not a section",
        {"FirstLevelHead": "Storage", "productCard": None},
        {
            "FirstLevelHead": "Database",
            "productCard": [
                {"cardList": None},
                {"cardList": ["not a card", {"title": "Tair", "desc": "In-memory database"}]},
            ],
        },
    ]

    results = await crawl_page(AlibabaCloudCrawler(), cards_page(sections))

    assert results == [{"name": "Tair", "description": "In-memory database", "pricing_policy": [], "url": None}]


@pytest.mark.parametrize(
    "content",
    [
        "<html><body></body></html>",
        '<html><body><div class="render-container-data" data-data="{&quot;nav&quot;: []}"></div></body></html>',
    ],
    ids=["missing", "no-content"],
)
async def test_page_without_cards_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    with pytest.raises(CatalogueFormatError, match="product cards"):
        await crawl_page(AlibabaCloudCrawler(), page(PRODUCTS_URL, content))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The alibaba page {PRODUCTS_URL} embeds no product cards."


async def test_documentation_requests_the_sitemap(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.alibaba")
    crawler = AlibabaCloudCrawler()
    await crawl_listings(crawler, make_response, crawl_page)

    results = await crawl_page(crawler, make_response(HELP_URL, "alibaba_help_en.html"))

    assert [(request.url, request.meta) for request in requests(results)] == [(SITEMAP_URL, {})]
    assert names(results) == []
    assert crawler.help_names["starops"] == ("STAROps", "starops")
    assert crawler.help_names["optimizationsolver"] == ("Optimization Solver", "optimization-solver")
    assert crawler.deprecated_names == {"oceanbase", "databasegateway", "cassandra"}
    messages = [record.getMessage() for record in caplog.records]
    assert "Skipping the documentation entry 'Platform For AI', already streamed." in messages


@pytest.mark.parametrize(
    "excluded",
    [
        "The Beginner's Guide",
        "ApsaraDB Console",
        "ApsaraDB for OceanBase (Deprecated)",
        "Database Gateway - Deprecated",
        "Alibaba Cloud SDK",
        "Alibaba Cloud CLI",
        "BSS OpenAPI",
        "Terraform",
        "Pulumi",
        "Ticket System API",
        "Support",
    ],
)
async def test_documentation_non_products_are_left_out(
    make_response: MakeResponse, crawl_page: CrawlPage, excluded: str
) -> None:
    crawler = AlibabaCloudCrawler()

    await crawl_page(crawler, make_response(HELP_URL, "alibaba_help_en.html"))

    assert excluded not in [name for name, _ in crawler.help_names.values()]


async def test_documentation_without_entry_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    content = (
        '<div class="ProductList--allProductsBodyBlock--x"></div><div class="ProductList--allProductsBodyBlock--y">'
    )
    with pytest.raises(CatalogueFormatError, match="the documentation lists no product"):
        await crawl_page(AlibabaCloudCrawler(), page(HELP_URL, f"<html><body>{content}</div></body></html>"))

    assert caplog.records[-1].levelno == logging.ERROR
    assert caplog.records[-1].getMessage() == f"The alibaba documentation page {HELP_URL} lists no product."


async def test_sitemap_requests_the_product_pages_not_streamed_yet(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = AlibabaCloudCrawler()
    await crawl_listings(crawler, make_response, crawl_page)
    await crawl_page(crawler, make_response(HELP_URL, "alibaba_help_en.html"))
    crawler.help_names["cassandra"] = ("Elastic GPU Service", "egs")
    crawler.help_names["gpu"] = ("Elastic GPU Service", "egs")

    results = await crawl_page(crawler, make_response(SITEMAP_URL, "alibaba_sitemap_product_en.xml"))

    pages = [request for request in requests(results) if AlibabaCloudCrawler.PRODUCT_PAGE in request.meta]
    assert [(request.url, request.meta) for request in pages] == [
        (
            AGENTCORE_URL,
            {
                AlibabaCloudCrawler.PRODUCT_PAGE: AGENTCORE_URL,
                AlibabaCloudCrawler.PRODUCT_NAME: "AgentCore",
                AlibabaCloudCrawler.HELP_SLUG: "agentcore",
            },
        ),
        (
            "https://www.alibabacloud.com/en/product/starops",
            {
                AlibabaCloudCrawler.PRODUCT_PAGE: "https://www.alibabacloud.com/en/product/starops",
                AlibabaCloudCrawler.PRODUCT_NAME: "STAROps",
                AlibabaCloudCrawler.HELP_SLUG: "starops",
            },
        ),
        (
            "https://www.alibabacloud.com/en/product/optimization_solver",
            {
                AlibabaCloudCrawler.PRODUCT_PAGE: "https://www.alibabacloud.com/en/product/optimization_solver",
                AlibabaCloudCrawler.PRODUCT_NAME: "Optimization Solver",
                AlibabaCloudCrawler.HELP_SLUG: "optimization-solver",
            },
        ),
    ]
    assert "starops" not in crawler.help_names


async def test_sitemap_requests_the_documentation_of_the_entries_without_product_page(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    crawler = AlibabaCloudCrawler()
    await crawl_listings(crawler, make_response, crawl_page)
    await crawl_page(crawler, make_response(HELP_URL, "alibaba_help_en.html"))
    crawler.help_names["gpu"] = ("Elastic GPU Service", "egs")

    results = await crawl_page(crawler, make_response(SITEMAP_URL, "alibaba_sitemap_product_en.xml"))

    landings = {
        request.meta[AlibabaCloudCrawler.PRODUCT_NAME]: (request.url, request.meta[AlibabaCloudCrawler.HELP_LANDING])
        for request in requests(results)
        if AlibabaCloudCrawler.HELP_LANDING in request.meta
    }
    assert landings["OpenSearch"] == ("https://www.alibabacloud.com/help/en/open-search/", "open-search")
    assert landings["Cloud Control API"] == (
        "https://www.alibabacloud.com/help/en/cloud-control-api/",
        "cloud-control-api",
    )
    assert "Elastic GPU Service" not in landings
    assert "AgentCore" not in landings


async def test_sitemap_category_pages_are_not_requested(crawl_page: CrawlPage) -> None:
    crawler = AlibabaCloudCrawler()
    crawler.category_urls.add("alibabacloud.com/product/alibaba-cloud-workspace")
    sitemap = (
        "<urlset><url><loc>https://www.alibabacloud.com/en/product/alibaba-cloud-workspace?_p_lc=1</loc></url></urlset>"
    )

    assert await crawl_page(crawler, page(SITEMAP_URL, sitemap)) == []


async def test_empty_sitemap_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="lists no page"):
        await crawl_page(AlibabaCloudCrawler(), page(SITEMAP_URL, "<urlset></urlset>"))

    assert caplog.records[-1].levelno == logging.ERROR


async def test_product_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response(f"{AGENTCORE_URL}?_p_lc=1", "alibaba_product_agentcore.html")
    response.meta[AlibabaCloudCrawler.PRODUCT_PAGE] = AGENTCORE_URL

    results = await crawl_page(AlibabaCloudCrawler(), response)

    assert results == [
        {
            "name": "AgentCore",
            "description": "AgentCore unifies construction, governance, and execution so enterprises can deploy "
            "diverse agents with confidence.",
            "pricing_policy": [],
            "url": AGENTCORE_URL,
        }
    ]


async def test_product_page_name_drops_the_seo_tagline(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    url = "https://www.alibabacloud.com/en/product/cassandra"
    response = make_response(f"{url}?_p_lc=1", "alibaba_product_cassandra.html")
    response.meta[AlibabaCloudCrawler.PRODUCT_PAGE] = url

    assert names(await crawl_page(AlibabaCloudCrawler(), response)) == ["ApsaraDB for Cassandra"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("PolarDB for Xscale_Distributed Database_MySQL_PolarDB-X_Database-Alibaba Cloud", "PolarDB for Xscale"),
        ("WonderClip - Alibaba Cloud's Full-Cycle AI Platform for Video Creation", "WonderClip"),
        ("AI-Native Database Service (AIDBS) | Agent-Ready Data Platform", "AI-Native Database Service (AIDBS)"),
        ("Anti-DDoS Basic - Alibaba Cloud", "Anti-DDoS Basic"),
    ],
)
async def test_product_page_name_drops_the_taglines(crawl_page: CrawlPage, title: str, expected: str) -> None:
    assert names(await crawl_page(AlibabaCloudCrawler(), product_page(AGENTCORE_URL, title))) == [expected]


async def test_product_page_deprecated_in_the_documentation_is_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    url = "https://www.alibabacloud.com/en/product/cassandra"
    response = make_response(f"{url}?_p_lc=1", "alibaba_product_cassandra.html")
    response.meta[AlibabaCloudCrawler.PRODUCT_PAGE] = url
    crawler = AlibabaCloudCrawler()
    crawler.deprecated_names.add("cassandra")

    assert await crawl_page(crawler, response) == []


async def test_product_page_named_by_the_documentation(crawl_page: CrawlPage) -> None:
    response = product_page(AGENTCORE_URL, "Agent Core platform - Alibaba Cloud")
    response.meta[AlibabaCloudCrawler.PRODUCT_NAME] = "AgentCore"

    assert names(await crawl_page(AlibabaCloudCrawler(), response)) == ["AgentCore"]


@pytest.mark.parametrize(
    ("og_title", "expected"),
    [("Apsara Stack - Alibaba Cloud - Alibaba Cloud", ["Apsara Stack"]), (None, [])],
    ids=["open-graph", "untitled"],
)
async def test_product_page_without_title(crawl_page: CrawlPage, og_title: Optional[str], expected: List[str]) -> None:
    head = f'<meta property="og:title" content="{og_title}">' if og_title else ""
    content = f'<html><head>{head}<meta name="description" content="Hybrid cloud."></head><body></body></html>'
    response = page(AGENTCORE_URL, content, {AlibabaCloudCrawler.PRODUCT_PAGE: AGENTCORE_URL})

    assert names(await crawl_page(AlibabaCloudCrawler(), response)) == expected


@pytest.mark.parametrize(
    "response",
    [
        product_page("https://www.alibabacloud.com/en/notfound?_p_lc=1", "not found"),
        product_page(AGENTCORE_URL, "AgentCore", description=""),
    ],
    ids=["not-found", "no-description"],
)
async def test_unknown_product_pages_are_skipped(crawl_page: CrawlPage, response: Response) -> None:
    assert await crawl_page(AlibabaCloudCrawler(), response) == []


async def test_retired_product_page_is_skipped(
    make_response: MakeResponse, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="scrapling.spiders.alibaba")
    url = "https://www.alibabacloud.com/en/product/hitsdb"
    response = make_response(f"{url}?_p_lc=1", "alibaba_product_hitsdb.html")
    response.meta[AlibabaCloudCrawler.PRODUCT_PAGE] = url

    assert await crawl_page(AlibabaCloudCrawler(), response) == []
    assert caplog.records[-1].getMessage() == (f"Skipping {url}?_p_lc=1, the product is no longer available for sale.")


async def test_product_page_without_description_reads_the_documentation(crawl_page: CrawlPage) -> None:
    response = product_page(AGENTCORE_URL, "AgentCore", description="")
    response.meta.update({AlibabaCloudCrawler.PRODUCT_NAME: "AgentCore", AlibabaCloudCrawler.HELP_SLUG: "agentcore"})

    results = await crawl_page(AlibabaCloudCrawler(), response)

    assert [(request.url, request.meta) for request in requests(results)] == [
        (
            "https://www.alibabacloud.com/help/en/agentcore/",
            {AlibabaCloudCrawler.HELP_LANDING: "agentcore", AlibabaCloudCrawler.PRODUCT_NAME: "AgentCore"},
        )
    ]


async def test_documentation_landing_with_a_genuine_description(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    response = make_response(EPG_URL, "alibaba_help_landing_epg.html")
    response.meta.update(
        {AlibabaCloudCrawler.HELP_LANDING: "epg", AlibabaCloudCrawler.PRODUCT_NAME: "Egress Proxy Gateway"}
    )

    results = await crawl_page(AlibabaCloudCrawler(), response)

    assert names(results) == ["Egress Proxy Gateway"]
    assert isinstance(results[0], dict)
    assert str(results[0]["description"]).startswith("Egress Proxy Gateway (EPG) is a fully managed egress traffic")
    assert results[0]["url"] == EPG_URL


def landing_page(links: List[str], description: str = BOILERPLATE) -> Response:
    anchors = "".join(f'<a href="{link}">{link}</a>' for link in links)
    content = f'<html><head><meta name="description" content="{description}"></head><body>{anchors}</body></html>'
    meta: Dict[str, JsonValue] = {AlibabaCloudCrawler.HELP_LANDING: "epg", AlibabaCloudCrawler.PRODUCT_NAME: "EPG"}
    return page(EPG_URL, content, meta)


@pytest.mark.parametrize(
    ("links", "article"),
    [
        (
            ["/help/en/epg/product-introduction", "/help/en/epg/what-is-epg", "/help/en/ecs/what-is-ecs"],
            "https://www.alibabacloud.com/help/en/epg/what-is-epg",
        ),
        (
            ["/help/en/epg/billing-overview", "/help/en/epg/epg-overview", "/help/en/epg/product-overview/"],
            "https://www.alibabacloud.com/help/en/epg/epg-overview",
        ),
        (
            ["/help/en/epg/product-overview/product-introduction", "/help/en/epg/what-is/"],
            "https://www.alibabacloud.com/help/en/epg/product-overview/product-introduction",
        ),
        (
            ["/help/en/epg/product-overview/", "/help/en/epg/product-overview/product-introduction/"],
            "https://www.alibabacloud.com/help/en/epg/product-overview/product-introduction/",
        ),
        (
            ["/help/en/epg/getting-started", "/help/en/epg/billing-overview"],
            "https://www.alibabacloud.com/help/en/epg/product-overview/what-is-epg",
        ),
    ],
    ids=["what-is", "overview", "introduction", "section", "guessed"],
)
async def test_documentation_landing_with_a_generic_description_requests_the_overview_article(
    crawl_page: CrawlPage, links: List[str], article: str
) -> None:
    results = await crawl_page(AlibabaCloudCrawler(), landing_page(links))

    assert [(request.url, request.meta) for request in requests(results)] == [
        (article, {AlibabaCloudCrawler.HELP_ARTICLE: EPG_URL, AlibabaCloudCrawler.PRODUCT_NAME: "EPG"})
    ]


async def test_overview_article(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    response = make_response("https://www.alibabacloud.com/help/en/epg/what-is-epg", "alibaba_help_article_epg.html")
    response.meta.update(
        {AlibabaCloudCrawler.HELP_ARTICLE: EPG_URL, AlibabaCloudCrawler.PRODUCT_NAME: "Egress Proxy Gateway"}
    )

    results = await crawl_page(AlibabaCloudCrawler(), response)

    assert names(results) == ["Egress Proxy Gateway"]
    assert isinstance(results[0], dict)
    assert str(results[0]["description"]).startswith("Egress Proxy Gateway (EPG) is a fully managed outbound traffic")
    assert results[0]["url"] == EPG_URL


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        (
            '<meta name="description" content="">',
            '<div class="markdown-body"><p> </p><p>EPG proxies traffic.</p></div>',
            ["EPG"],
        ),
        (f'<meta name="description" content="{BOILERPLATE}">', "", []),
        ("", "<main><p>This Product</p></main>", []),
    ],
    ids=["paragraph", "boilerplate", "none"],
)
async def test_overview_article_descriptions(crawl_page: CrawlPage, head: str, body: str, expected: List[str]) -> None:
    meta: Dict[str, JsonValue] = {AlibabaCloudCrawler.HELP_ARTICLE: EPG_URL, AlibabaCloudCrawler.PRODUCT_NAME: "EPG"}
    response = page(f"{EPG_URL}what-is-epg", f"<html><head>{head}</head><body>{body}</body></html>", meta)

    assert names(await crawl_page(AlibabaCloudCrawler(), response)) == expected


async def test_documentation_product_already_streamed(crawl_page: CrawlPage) -> None:
    crawler = AlibabaCloudCrawler()
    response = landing_page([], description="EPG proxies traffic.")

    first, second = await crawl_page(crawler, response), await crawl_page(crawler, response)

    assert (names(first), second) == (["EPG"], [])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "https://www.alibabacloud.com/product/polardb-x",
            "https://www.alibabacloud.com/en/product/polardb-for-xscale",
        ),
        ("https://www.alibabacloud.com/product/ecs", "https://www.alibabacloud.com/en/product/ecs?_p_lc=1"),
        ("https://www.alibabacloud.com/Product/advisor", "https://alibabacloud.com/en/product/advisor/"),
    ],
)
def test_url_keys_ignore_the_locale(first: str, second: str) -> None:
    crawler = AlibabaCloudCrawler()

    assert crawler._url_key(first) == crawler._url_key(second)


async def test_streamed_products_remember_their_abbreviation_and_documentation_names(crawl_page: CrawlPage) -> None:
    crawler = AlibabaCloudCrawler()
    sections: JsonValue = [
        {
            "FirstLevelHead": "Developer Services",
            "productCard": [
                {
                    "cardList": [
                        {"title": "mPaaS", "desc": "Mobile apps"},
                        {"title": "Edge Node Service (ENS)", "desc": "Edge"},
                    ]
                }
            ],
        }
    ]

    await crawl_page(crawler, cards_page(sections))

    assert {"mobileplatformasaservice", "ens", "edgenodeservice", "mpaas"} <= crawler.seen_products
