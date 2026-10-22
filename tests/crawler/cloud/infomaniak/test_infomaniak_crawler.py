from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.infomaniak.crawler import InfomaniakCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
LINK = "DisplayProductsLink-module--productsLink--57eff"
TITLE = "DisplayProductsLink-module--productsLinkContentTitle--f3ea6"
DESCRIPTION = "DisplayProductsLink-module--productsLinkContentDesc--91a54"


def page(content: str) -> Response:
    return Response(
        url=InfomaniakCrawler.catalogue_url,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [result["name"] for result in results if isinstance(result, dict)]


def test_configuration() -> None:
    crawler = InfomaniakCrawler()

    assert crawler.name == "infomaniak"
    assert InfomaniakCrawler.catalogue_url == "https://www.infomaniak.com/en"
    assert InfomaniakCrawler.complement_urls == ()
    assert InfomaniakCrawler.name_prefixes == ("Infomaniak ",)
    assert crawler.allowed_domains == {"www.infomaniak.com"}


async def test_extracts_the_menu_products_of_every_group(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        InfomaniakCrawler(), make_response(InfomaniakCrawler.catalogue_url, "infomaniak_home.html")
    )

    assert names(results) == [
        "kDrive",
        "kSuite PRO",
        "Euria, the ethical AI",
        "Cloud Server",
        "Public Cloud (IaaS)",
        "Access Control",
        "VOD & AOD service",
    ]
    assert results[0] == {
        "name": "kDrive",
        "description": "Store, collaborate and share your files",
        "pricing_policy": [],
        "url": "https://www.infomaniak.com/en/ksuite/kdrive",
        "catalogue_categories": ["Collaborative tools"],
    }
    assert results[4] == {
        "name": "Public Cloud (IaaS)",
        "description": "Create your projects in a high-end, ultra-competitive Cloud",
        "pricing_policy": [],
        "url": "https://www.infomaniak.com/en/hosting/public-cloud",
        "catalogue_categories": ["Cloud Computing"],
    }


async def test_menu_products_are_filed_under_their_group(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        InfomaniakCrawler(), make_response(InfomaniakCrawler.catalogue_url, "infomaniak_home.html")
    )

    categories = {result["name"]: result.get("catalogue_categories") for result in results if isinstance(result, dict)}
    assert categories == {
        "kDrive": ["Collaborative tools"],
        "kSuite PRO": ["Collaborative tools"],
        "Euria, the ethical AI": ["Collaborative tools"],
        "Cloud Server": ["Web & Domains"],
        "Public Cloud (IaaS)": ["Cloud Computing"],
        "Access Control": ["Events & Marketing"],
        "VOD & AOD service": ["Streaming"],
    }


async def test_menu_products_listed_in_several_groups_gather_them(crawl_page: CrawlPage) -> None:
    left = "".join(
        f'<p class="DisplayProductsNav-module--productsNavLeftItemTitle--19136">{title}</p>'
        for title in ("Web &amp; Domains", "Cloud Computing")
    )
    server = f'<a class="{LINK}" href="/en/hosting/managed-cloud-server"><div class="{TITLE}">Cloud Server</div>'
    server += f'<div class="{DESCRIPTION}">Guaranteed resources</div></a>'
    vps = f'<a class="{LINK}" href="/en/hosting/vps-cloud"><div class="{TITLE}">VPS Cloud</div>'
    vps += f'<div class="{DESCRIPTION}">Virtual servers</div></a>'
    panels = f"<div>{server}</div><div>{vps}{server}</div>"
    right = f'<div class="DisplayProductsNav-module--productsNavRight--77ddd">{panels}</div>'
    nav = f'<div class="DisplayProductsNav-module--productsNav--3ba8f"><div>{left}</div>{right}</div>'

    results = await crawl_page(InfomaniakCrawler(), page(nav))

    categories = [(item["name"], item.get("catalogue_categories")) for item in results if isinstance(item, dict)]
    assert categories == [("Cloud Server", ["Web & Domains", "Cloud Computing"]), ("VPS Cloud", ["Cloud Computing"])]


async def test_invalid_menu_links_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    links = [
        f'<a class="{LINK}" href="/en/nameless"><div class="{DESCRIPTION}">No name</div></a>',
        f'<a class="{LINK}" href="/en/kpaste"><div class="{TITLE}">kPaste</div></a>',
        f'<a class="{LINK}"><div class="{TITLE}">kMeet</div><div class="{DESCRIPTION}">Meetings</div></a>',
        f'<a class="{LINK}" href="https://chk.infomaniak.com"><div class="{TITLE}">Chk</div>'
        f'<div class="{DESCRIPTION}">Link reducer</div></a>',
    ]

    results = await crawl_page(InfomaniakCrawler(), page(f"<nav>{''.join(links)}</nav>"))

    assert results == [
        {"name": "kMeet", "description": "Meetings", "pricing_policy": [], "url": None},
        {"name": "Chk", "description": "Link reducer", "pricing_policy": [], "url": "https://chk.infomaniak.com"},
    ]
    assert any(record.levelname == "WARNING" and "kPaste" in record.message for record in caplog.records)


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(InfomaniakCrawler(), page("<html><body></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)
