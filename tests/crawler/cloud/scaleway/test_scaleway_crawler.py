from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.scaleway.crawler import ScalewayCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]


def next_data_page(page_props: JsonValue) -> Response:
    script = json.dumps({"props": {"pageProps": page_props}})
    return Response(
        url=ScalewayCrawler.catalogue_url,
        content=f'<script id="__NEXT_DATA__" type="application/json">{script}</script>',
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = ScalewayCrawler()

    assert crawler.name == "scaleway"
    assert ScalewayCrawler.catalogue_url == "https://www.scaleway.com/en/all-products/"
    assert ScalewayCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"www.scaleway.com"}


async def test_extracts_the_columns_then_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        ScalewayCrawler(), make_response(ScalewayCrawler.catalogue_url, "scaleway_all_products.html")
    )

    assert names(results) == [
        "Identity and Access Management (IAM)",
        "Secret Manager",
        "Kubernetes Kapsule",
        "GPU Clusters",
        "Serverless SQL Database",
        "Moshi (Labs)",
    ]
    assert results[0] == {
        "name": "Identity and Access Management (IAM)",
        "description": "The easiest way to safely collaborate in the cloud",
        "pricing_policy": [],
        "url": "https://www.scaleway.com/en/iam/",
        "catalogue_categories": ["Security and Identity"],
    }
    assert results[3] == {
        "name": "GPU Clusters",
        "description": "Secure your dedicated cluster capacity.",
        "pricing_policy": [],
        "url": "https://www.scaleway.com/en/gpu-clusters/",
        "catalogue_categories": ["AI", "GPU"],
        "added_at": "2024-11-28T16:40:12.115000Z",
        "added_caveat": "website-record",
        "updated_at": "2026-05-28T14:02:11.871000Z",
        "updated_caveat": "page-modified",
    }


async def test_products_are_filed_under_their_column_or_menu_groups(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(
        ScalewayCrawler(), make_response(ScalewayCrawler.catalogue_url, "scaleway_all_products.html")
    )

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories == {
        "Identity and Access Management (IAM)": ["Security and Identity"],
        "Secret Manager": ["Security and Identity"],
        "Kubernetes Kapsule": ["Containers"],
        "GPU Clusters": ["AI", "GPU"],
        "Serverless SQL Database": ["Cloud"],
        "Moshi (Labs)": ["Cloud"],
    }


async def test_products_listed_several_times_gather_their_categories(crawl_page: CrawlPage) -> None:
    gpu: Dict[str, JsonValue] = {
        "title": "L4 GPU Instance",
        "description": "GPU",
        "link": {"url": "https://www.scaleway.com/en/l4/"},
    }
    blocks: JsonValue = [
        {"__component": "blocks.generic-columns", "title": "AI", "items": [gpu]},
        {"__component": "blocks.generic-columns", "title": "Compute", "items": [{**gpu, "title": "L4 GPU"}]},
    ]
    header: JsonValue = {
        "mainNavigationItems": [
            {
                "groupName": "Cloud",
                "children": [
                    {
                        "groupName": "Serverless Compute",
                        "children": [
                            {
                                "groupName": "Serverless Jobs",
                                "children": [{"groupName": "Serverless Jobs", "description": "Batch", "children": []}],
                            },
                        ],
                    },
                    {"groupName": "L4 GPU Instance", "description": "GPU", "children": []},
                ],
            },
            {
                "groupName": "AI",
                "children": [
                    {"groupName": "Jobs", "children": [{"groupName": "serverless jobs", "description": "Batch"}]}
                ],
            },
        ]
    }

    results = await crawl_page(ScalewayCrawler(), next_data_page({"page": {"blocks": blocks}, "header": header}))

    categories = [(item["name"], item.get("catalogue_categories")) for item in results if isinstance(item, dict)]
    assert categories == [
        ("L4 GPU Instance", ["AI", "Compute"]),
        ("Serverless Jobs", ["Cloud", "Serverless Compute", "AI", "Jobs"]),
    ]


async def test_products_are_dated_by_their_page_record(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        ScalewayCrawler(), make_response(ScalewayCrawler.catalogue_url, "scaleway_all_products.html")
    )

    dated = [
        (result["name"], result.get("added_at"), result.get("updated_at"))
        for result in results
        if isinstance(result, dict)
    ]
    assert dated == [
        ("Identity and Access Management (IAM)", None, None),
        ("Secret Manager", "2024-11-28T16:40:12.115000Z", "2026-06-16T09:23:04.300000Z"),
        ("Kubernetes Kapsule", None, None),
        ("GPU Clusters", "2024-11-28T16:40:12.115000Z", "2026-05-28T14:02:11.871000Z"),
        ("Serverless SQL Database", "2024-11-28T16:40:12.115000Z", "2026-09-02T08:45:19.044000Z"),
        ("Moshi (Labs)", None, None),
    ]
    caveats = {
        (result.get("added_caveat"), result.get("updated_caveat")) for result in results if isinstance(result, dict)
    }
    assert caveats == {(None, None), ("website-record", "page-modified")}


@pytest.mark.parametrize(
    ("link", "created", "updated"),
    [
        (
            {"page": {"createdAt": "2024-11-28T16:40:12.115Z", "updatedAt": "2026-06-16T09:23:04.300Z"}},
            "2024-11-28T16:40:12.115Z",
            "2026-06-16T09:23:04.300Z",
        ),
        ({"url": None, "page": {"path": "/iam/", "updatedAt": "not a date"}}, None, None),
        ({"url": None, "page": {"path": "/iam/", "createdAt": "2024-11-28"}}, "2024-11-28", None),
        ({"url": "https://www.scaleway.com/en/iam/", "page": None}, None, None),
        (None, None, None),
    ],
)
def test_link_dates(link: JsonValue, created: Optional[str], updated: Optional[str]) -> None:
    expected = tuple(
        datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None for value in (created, updated)
    )

    assert ScalewayCrawler()._link_dates(link, "IAM") == expected


@pytest.mark.parametrize("excluded", ["Compare our GPUs", "Quantum Adoption Program", "Startup Program", "Coming soon"])
async def test_non_products_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(
        ScalewayCrawler(), make_response(ScalewayCrawler.catalogue_url, "scaleway_all_products.html")
    )

    assert excluded not in names(results)


@pytest.mark.parametrize(
    ("link", "url"),
    [
        ({"url": "https://www.scaleway.com/en/iam/", "page": None}, "https://www.scaleway.com/en/iam/"),
        ({"url": None, "page": {"path": "/gpu-clusters/"}}, "https://www.scaleway.com/en/gpu-clusters/"),
        ({"url": None, "page": None}, None),
        (None, None),
    ],
)
def test_link_urls(link: JsonValue, url: Optional[str]) -> None:
    assert ScalewayCrawler()._link_url(link) == url


@pytest.mark.parametrize("items", [None, "items", [None, 5]])
async def test_skips_malformed_blocks(crawl_page: CrawlPage, items: JsonValue) -> None:
    blocks: JsonValue = [
        {"__component": "blocks.generic-columns", "items": items},
        {"__component": "blocks.generic-columns", "items": [{"title": "Instances", "description": "Virtual machines"}]},
    ]

    results = await crawl_page(ScalewayCrawler(), next_data_page({"page": {"blocks": blocks}}))

    assert results == [{"name": "Instances", "description": "Virtual machines", "pricing_policy": [], "url": None}]


@pytest.mark.parametrize(
    "header",
    [None, {"mainNavigationItems": "menu"}, {"mainNavigationItems": [None, {"groupName": "Pricing", "children": []}]}],
)
async def test_skips_malformed_menus(crawl_page: CrawlPage, header: JsonValue) -> None:
    blocks: JsonValue = [
        {"__component": "blocks.generic-columns", "items": [{"title": "Instances", "description": "VM"}]}
    ]

    results = await crawl_page(ScalewayCrawler(), next_data_page({"page": {"blocks": blocks}, "header": header}))

    assert names(results) == ["Instances"]


async def test_page_without_products_is_an_error(crawl_page: CrawlPage) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(ScalewayCrawler(), next_data_page({"page": {"blocks": [{"__component": "blocks.hero"}]}}))


async def test_invalid_menu_entries_are_skipped(crawl_page: CrawlPage) -> None:
    header: JsonValue = {
        "mainNavigationItems": [
            {
                "groupName": "Cloud",
                "children": [
                    {"groupName": "x" * 201, "description": "Too long", "children": []},
                    {"groupName": "Instances", "description": "Virtual machines", "children": []},
                ],
            }
        ]
    }

    results = await crawl_page(ScalewayCrawler(), next_data_page({"page": {"blocks": []}, "header": header}))

    assert names(results) == ["Instances"]
