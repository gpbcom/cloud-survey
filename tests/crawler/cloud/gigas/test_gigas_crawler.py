from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.gigas.crawler import GigasCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]


def page(url: str, content: str) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = GigasCrawler()

    assert crawler.name == "gigas"
    assert GigasCrawler.catalogue_url == "https://gigas.com/en/"
    assert GigasCrawler.complement_urls == ("https://gigas.com/en/addons-cloud.html",)
    assert crawler.allowed_domains == {"gigas.com"}


async def test_extracts_the_menu_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(GigasCrawler(), make_response(GigasCrawler.catalogue_url, "gigas_home.html"))

    assert names(results) == [
        "Sovereign Cloud",
        "Cloud Datacenter",
        "VPS",
        "Virtual Desktop",
        "SAP Cloud",
        "SAGE Cloud",
        "SaaS document management solutions",
        "Gyper",
        "Managed Cybersecurity",
        "g-Backup",
        "Gigas Disaster Recovery",
        "g-Cyberprotect",
        "Biblion IA",
        "Datum",
    ]
    assert results[1] == {
        "name": "Cloud Datacenter",
        "description": "Your own virtual data centre in the cloud",
        "pricing_policy": [],
        "url": "https://gigas.com/en/cloud-datacenter",
        "catalogue_categories": ["Cloud", "Sovereign Cloud"],
    }


async def test_menu_products_are_filed_under_their_group_and_column(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(GigasCrawler(), make_response(GigasCrawler.catalogue_url, "gigas_home.html"))

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories["Sovereign Cloud"] == ["Cloud"]
    assert categories["SAP Cloud"] == ["Cloud", "Solutions"]
    assert categories["Gyper"] == ["Cloud", "Tech"]
    assert categories["g-Backup"] == ["Security", "Managed Cybersecurity"]
    assert categories["Datum"] == ["Artificial Intelligence"]


@pytest.mark.parametrize(
    "excluded",
    ["Solutions", "Cloud Addons", "Public authorities", "Health", "About us", "Success stories", "Partners"],
)
async def test_menu_non_products_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage, excluded: str) -> None:
    results = await crawl_page(GigasCrawler(), make_response(GigasCrawler.catalogue_url, "gigas_home.html"))

    assert excluded not in names(results)


async def test_menu_without_product_group_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    content = '<div class="dropdown"><a class="dropdown-toggle">Partners</a>'
    content += '<a class="dropdown-item-main" href="/en/partners.html"><p>Partners</p><span>Programme</span></a></div>'
    content += '<div class="dropdown"><a class="dropdown-toggle">Language</a><ul><li>English</li></ul></div>'

    with caplog.at_level(logging.ERROR), pytest.raises(CatalogueFormatError, match="products menu is missing"):
        await crawl_page(GigasCrawler(), page(GigasCrawler.catalogue_url, content))

    assert "has no products menu" in caplog.text


async def test_menu_entries_without_toggle_or_texts(crawl_page: CrawlPage) -> None:
    content = (
        '<div class="dropdown"><a class="dropdown-item-main" href="/en/g-mail.html"><p>g-Mail</p><span>Mail.</span></a>'
    )
    content += '<a class="dropdown-item-main" href="/en/nameless.html"><span>No name</span></a></div>'

    results = await crawl_page(GigasCrawler(), page(GigasCrawler.catalogue_url, content))

    assert names(results) == ["g-Mail"]
    assert results[0] == {
        "name": "g-Mail",
        "description": "Mail.",
        "pricing_policy": [],
        "url": "https://gigas.com/en/g-mail.html",
    }


async def test_extracts_the_addons(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(GigasCrawler(), make_response(GigasCrawler.ADDONS_URL, "gigas_addons.html"))

    assert names(results) == ["Firewall", "VPN", "Load Balancer", "Cloud Backup Pro"]
    assert results[0] == {
        "name": "Firewall",
        "description": "Advanced protection against cyberattacks to keep your infrastructure always secure. Enjoy a "
        "completely free 30-day trial with no commitment.",
        "pricing_policy": [],
        "url": "https://gigas.com/en/addons-cloud/firewall.html",
    }


async def test_addons_already_streamed_are_skipped(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = GigasCrawler()
    await crawl_page(crawler, make_response(GigasCrawler.catalogue_url, "gigas_home.html"))
    content = '<section id="addons-comp"><a href="/en/g-backup.html"><h3>Backups (g-Backup)</h3><p>Again.</p></a>'
    content += '<a href="/en/addons-cloud/dns.html"><h3>Managed DNS</h3><p>Zones <b>and</b> records .</p></a>'
    content += '<a href="/en/addons-cloud/ip.html"><h3>Public IP</h3></a></section>'

    results = await crawl_page(crawler, page(GigasCrawler.ADDONS_URL, content))

    assert results == [
        {
            "name": "Managed DNS",
            "description": "Zones and records.",
            "pricing_policy": [],
            "url": "https://gigas.com/en/addons-cloud/dns.html",
            "catalogue_categories": ["Cloud", "Cloud Addons"],
        }
    ]


async def test_addons_page_without_addon_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(EmptyCatalogueError):
        await crawl_page(GigasCrawler(), page(GigasCrawler.ADDONS_URL, "<section><h3>Greater security</h3></section>"))

    assert "holds no product" in caplog.text
