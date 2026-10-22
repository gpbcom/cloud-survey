from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
CARD = (
    '<div class="card"><div class="card-body"><h3 class="h5">{name}</h3>'
    "<div data-oc-token-text><p>{description}</p></div>{link}</div></div>"
)


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = AzureCrawler()

    assert crawler.name == "azure"
    assert AzureCrawler.catalogue_url == "https://azure.microsoft.com/en-us/products/"
    assert AzureCrawler.complement_urls == ("https://learn.microsoft.com/en-us/azure/?product=all",)
    assert crawler.allowed_domains == {"azure.microsoft.com", "learn.microsoft.com"}


async def test_extracts_the_products_page_once(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(AzureCrawler(), make_response(AzureCrawler.catalogue_url, "azure_products.html"))

    assert names(results) == ["Microsoft Foundry", "Azure AI Bot Service", "Azure AI Search", "Azure Databricks"]
    assert results[0] == {
        "name": "Microsoft Foundry",
        "description": "The AI app and agent factory.",
        "pricing_policy": [],
        "url": "https://azure.microsoft.com/en-us/products/ai-foundry",
        "catalogue_categories": ["AI + machine learning", "Analytics"],
    }


async def test_products_page_categories_are_the_headings(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(AzureCrawler(), make_response(AzureCrawler.catalogue_url, "azure_products.html"))

    assert {result["name"]: result["catalogue_categories"] for result in results if isinstance(result, dict)} == {
        "Microsoft Foundry": ["AI + machine learning", "Analytics"],
        "Azure AI Bot Service": ["AI + machine learning"],
        "Azure AI Search": ["AI + machine learning"],
        "Azure Databricks": ["Analytics"],
    }


async def test_product_cards_merge_the_categories_of_every_listing(crawl_page: CrawlPage) -> None:
    link = '<a data-bi-cn="Product" href="/en-us/products/functions/">Product</a>'
    content = "".join(
        f'<h2 class="h4">{category}</h2><div class="content-card-list">'
        f"{CARD.format(name=name, description='Serverless compute', link=link)}</div>"
        for category, name in (("Compute", "Azure Functions"), ("Containers", "Functions"), ("Compute", "Functions"))
    )

    results = await crawl_page(AzureCrawler(), page(AzureCrawler.catalogue_url, content))

    assert results == [
        {
            "name": "Azure Functions",
            "description": "Serverless compute",
            "pricing_policy": [],
            "url": "https://azure.microsoft.com/en-us/products/functions/",
            "catalogue_categories": ["Compute", "Containers"],
        }
    ]


async def test_learn_directory_completes_the_products_page(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = AzureCrawler()
    await crawl_page(crawler, make_response(AzureCrawler.catalogue_url, "azure_products.html"))

    results = await crawl_page(crawler, make_response(AzureCrawler.LEARN_URL, "azure_learn.html"))

    assert results == [
        {
            "name": "Azure Service Fabric",
            "description": "Develop microservices and orchestrate containers on Windows or Linux",
            "pricing_policy": [],
            "url": "https://learn.microsoft.com/en-us/azure/service-fabric/",
            "catalogue_categories": ["Compute", "Containers"],
        },
        {
            "name": "Azure Cache for Redis",
            "description": "Power applications with high-throughput, low-latency data access",
            "pricing_policy": [],
            "url": "https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/",
            "catalogue_categories": ["Databases"],
        },
    ]


async def test_learn_directory_skips_the_all_services_cards(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(AzureCrawler(), make_response(AzureCrawler.LEARN_URL, "azure_learn.html"))

    assert "All networking services" not in names(results)
    assert names(results) == ["Azure Databricks", "Azure Service Fabric", "Azure Cache for Redis"]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Azure AI Speech", "Speech"),
        ("App Configuration", "Azure App Configuration"),
        ("Microsoft Azure Data Box", "Data Box"),
        ("Azure Content Delivery Network", "Content Delivery Network (CDN)"),
    ],
)
async def test_brand_prefixes_and_notes_are_ignored(crawl_page: CrawlPage, first: str, second: str) -> None:
    content = "".join(CARD.format(name=name, description="Description", link="") for name in (first, second))

    results = await crawl_page(
        AzureCrawler(), page(AzureCrawler.catalogue_url, f'<div class="content-card-list">{content}</div>')
    )

    assert names(results) == [first]


async def test_same_product_page_under_two_names(crawl_page: CrawlPage) -> None:
    link = '<a data-bi-cn="Product" href="/en-us/products/app-configuration/">Product</a>'
    content = CARD.format(name="App Configuration", description="Store settings", link=link)
    content += CARD.format(name="Configuration store", description="Store settings", link=link)

    results = await crawl_page(
        AzureCrawler(), page(AzureCrawler.catalogue_url, f'<div class="content-card-list">{content}</div>')
    )

    assert names(results) == ["App Configuration"]


async def test_skips_invalid_cards(crawl_page: CrawlPage) -> None:
    content = CARD.format(name="Azure Retired", description=" ", link="")
    content += CARD.format(name="Azure Functions", description="Event-driven serverless compute.", link="")
    content += '<div class="card"><div class="card-body"></div></div>'

    results = await crawl_page(
        AzureCrawler(), page(AzureCrawler.catalogue_url, f'<div class="content-card-list">{content}</div>')
    )

    assert results == [
        {
            "name": "Azure Functions",
            "description": "Event-driven serverless compute.",
            "pricing_policy": [],
            "url": None,
        }
    ]


async def test_learn_cards_without_title_or_description_are_skipped(crawl_page: CrawlPage) -> None:
    content = (
        '<div data-bi-name="product-card"><p class="card-content-description">No title</p></div>'
        '<div data-bi-name="product-card"><a class="card-title" href="batch/">Azure Batch</a></div>'
        '<div data-bi-name="product-card"><a class="card-title" href="functions/">Azure Functions</a>'
        '<p class="card-content-description">Serverless compute</p></div>'
    )

    results = await crawl_page(AzureCrawler(), page(AzureCrawler.LEARN_URL, content))

    assert results == [
        {
            "name": "Azure Functions",
            "description": "Serverless compute",
            "pricing_policy": [],
            "url": "https://learn.microsoft.com/en-us/azure/functions/",
        }
    ]


async def test_page_without_cards_is_an_error(crawl_page: CrawlPage) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(AzureCrawler(), page(AzureCrawler.catalogue_url, "<html><body><h1>Azure</h1></body></html>"))


async def test_invalid_learn_cards_are_skipped(crawl_page: CrawlPage) -> None:
    name = "x" * 201
    content = (
        f'<div data-bi-name="product-card"><a class="card-title" href="x/">{name}</a>'
        '<p class="card-content-description">Too long</p></div>'
        '<div data-bi-name="product-card"><a class="card-title" href="batch/">Azure Batch</a>'
        '<p class="card-content-description">Batch jobs</p></div>'
    )

    assert names(await crawl_page(AzureCrawler(), page(AzureCrawler.LEARN_URL, content))) == ["Azure Batch"]
