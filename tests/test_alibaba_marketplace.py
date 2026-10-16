from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.alibaba.marketplace import AlibabaMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parent / "fixtures" / "marketplace"
HOST = "https://marketplace.alibabacloud.com"
BUSINESS = "56682003"
CARD = ".product-list-item:not(.advertising)"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> AlibabaMarketplaceCrawler:
    return AlibabaMarketplaceCrawler(classifier=classifier)


@pytest.fixture(autouse=True)
def no_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "page_limit", None)


def page(url: str, content: Union[str, bytes], meta: Optional[Dict[str, JsonValue]] = None) -> Response:
    return Response(
        url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta or {}
    )


def fixture(name: str) -> bytes:
    return (FIXTURES / f"alibaba_{name}.html").read_bytes()


def result_page(content: Union[str, bytes], number: int, top: str = BUSINESS) -> Response:
    return page(f"{HOST}/products?categoryId={top}", content, {"top": top, "page": number})


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def software(results: List[Union[Dict[str, JsonValue], Request]]) -> Dict[str, Dict[str, JsonValue]]:
    return {str(result["name"]): result for result in results if isinstance(result, dict)}


def card(
    name: str = "Tool",
    href: str = "/products/56720001/sgcmjj00000001.html?innerSource=search",
    info: str = "<li>Delivery Method: Image</li>",
    extra: str = '<div class="list-item-describe"><span>A tool.</span></div><a class="list-item-company">By Acme</a>',
) -> str:
    link = f'<h3 class="list-item-title"><a href="{href}">{name}</a></h3>' if href else ""
    return f'<div class="product-list-item fff">{link}<ul class="list-item-info">{info}</ul>{extra}</div>'


def cards_page(*cards: str, total: int = 1) -> bytes:
    pagination = f'<div class="next-pagination-total">Total: {total}</div>' if total else ""
    return fixture("products").replace(b"</body>", ("".join(cards) + pagination + "</body>").encode())


def browser_page(jump_count: int) -> MagicMock:
    browser = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock()
    locator.fill = AsyncMock()
    locator.count = AsyncMock(return_value=jump_count)
    locator.first.click = AsyncMock()
    locator.first.text_content = AsyncMock(return_value="First product")
    browser.locator.return_value = locator
    browser.wait_for_function = AsyncMock()
    return browser


def test_configuration(crawler: AlibabaMarketplaceCrawler) -> None:
    assert crawler.name == "alibaba-marketplace"
    assert AlibabaMarketplaceCrawler.catalogue_url == f"{HOST}/products"
    assert AlibabaMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"marketplace.alibabacloud.com"}
    assert crawler.category_names == {}


async def test_starts_with_the_products_page_in_the_browser(crawler: AlibabaMarketplaceCrawler) -> None:
    started = [request async for request in crawler.start_requests()]

    assert [(request.url, request.sid, request.priority) for request in started] == [
        (f"{HOST}/products", "alibaba-marketplace-session", 10)
    ]
    assert started[0]._session_kwargs == {"wait_selector": "ul.menu_item"}


async def test_requests_the_software_top_categories(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    found = requests(await crawl_page(crawler, page(f"{HOST}/products", fixture("products"))))

    assert [(request.url, request.meta) for request in found] == [
        (f"{HOST}/products?categoryId=56682004", {"top": "56682004", "page": 1}),
        (f"{HOST}/products?categoryId=56718002", {"top": "56718002", "page": 1}),
        (f"{HOST}/products?categoryId={BUSINESS}", {"top": BUSINESS, "page": 1}),
    ]
    request = found[0]
    assert (request.sid, request.dont_filter) == ("alibaba-marketplace-session", True)
    assert request._session_kwargs["wait_selector"] == CARD
    action = request._session_kwargs["page_action"]
    assert isinstance(action, partial)
    assert action.args == (1,)
    assert crawler.category_names["56732001"] == "Operating Systems"
    assert crawler.category_names["56728001"] == "Application Stacks"
    assert len(crawler.category_names) == 41
    assert "Skipping the top category 'Professional Service' (not software)." in caplog.text


async def test_raises_without_category_menu(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    menu = '<ul class="menu_item"><li class="item title"><a href="/products">All</a></li><li><span>x</span></li></ul>'

    with pytest.raises(CatalogueFormatError, match="the category menu is missing"):
        await crawl_page(crawler, page(f"{HOST}/products", f"<html><body>{menu}</body></html>"))

    assert any(
        record.levelno == logging.ERROR and "has no category menu" in record.message for record in caplog.records
    )


async def test_extracts_a_first_result_page_and_requests_the_next_ones(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "PAGE_SIZE", 6)
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "page_limit", 3)

    results = await crawl_page(crawler, result_page(fixture("page1"), 1))

    next_pages = requests(results)
    assert [(request.url, request.meta) for request in next_pages] == [
        (f"{HOST}/products?categoryId={BUSINESS}", {"top": BUSINESS, "page": 2}),
        (f"{HOST}/products?categoryId={BUSINESS}", {"top": BUSINESS, "page": 3}),
    ]
    assert [request._session_kwargs["page_action"].args for request in next_pages] == [(2,), (3,)]
    found = software(results)
    assert list(found) == [
        "Salesforce Products",
        "AMap Overseas Open Platform",
        "ai-translation",
        "UnifyAI Gateway",
        "iRuiDong",
    ]
    assert {key: found["Salesforce Products"][key] for key in ("url", "publisher", "delivery")} == {
        "url": f"{HOST}/products/201064003/sgcmgj00037005.html",
        "publisher": "Salesforce resale on Alibaba Cloud",
        "delivery": "saas",
    }
    assert found["Salesforce Products"]["marketplace_categories"] == ["Business Software", "CRM"]
    assert found["Salesforce Products"]["description"] == "Salesforce product resold by Alibaba Cloud"
    assert found["iRuiDong"]["marketplace_categories"] == ["Business Software", "Application Stacks"]


async def test_extracts_a_next_result_page(
    crawler: AlibabaMarketplaceCrawler,
    crawl_page: CrawlPage,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "PAGE_SIZE", 8)
    caplog.set_level(logging.DEBUG)

    results = await crawl_page(crawler, result_page(fixture("page7"), 7))

    assert requests(results) == []
    found = software(results)
    assert {name: item["delivery"] for name, item in found.items()} == {
        "Haivision Media Gateway (BYOL)": "virtual-machine",
        "WhatsApp/FB/WeChat Chat Commerce and AI (Pay As You Go)": "saas",
        (
            "Enterprise Knowledge Graph - Smart Global Stock Market China Hong Kong Stock Exchange Data Query - iCREDIT"
        ): "api",
        "TYPO3 - Preconfigured, Hardened, Ready in Minutes": "virtual-machine",
        "ManageEngine ServiceDesk Plus": "virtual-machine",
        "Human Resources Management": "saas",
    }
    assert found["Human Resources Management"]["marketplace_categories"] == ["Business Software", "ERP"]
    assert "Skipping the product 'Cloudverse FinOps Platform' (service)." in caplog.text


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Human Resources Management", "hris"),
        ("TYPO3 - Preconfigured, Hardened, Ready in Minutes", "cms"),
        ("ManageEngine ServiceDesk Plus", "crm"),
    ],
)
async def test_classifies_the_software(
    crawler: AlibabaMarketplaceCrawler,
    crawl_page: CrawlPage,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    kind: str,
) -> None:
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "PAGE_SIZE", 8)

    types = software(await crawl_page(crawler, result_page(fixture("page7"), 7)))[name]["types"]

    assert isinstance(types, list)
    assert kind in types


@pytest.mark.parametrize(("number", "size"), [(6, 8), (7, 50)])
async def test_raises_when_the_page_is_not_shown(
    crawler: AlibabaMarketplaceCrawler,
    crawl_page: CrawlPage,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    number: int,
    size: int,
) -> None:
    monkeypatch.setattr(AlibabaMarketplaceCrawler, "PAGE_SIZE", size)

    with pytest.raises(CatalogueFormatError, match=f"the page {number} is not shown"):
        await crawl_page(crawler, result_page(fixture("page7"), number))

    assert any(record.levelno == logging.ERROR and "shows the page 7" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("info", "href", "delivery"),
    [
        ("<li>Delivery Method: Container</li>", "/products/56720001/sgcmjj00000001.html", "virtual-machine"),
        ("", "/products/56720001/sgcmgj00000001.html", "saas"),
        ("<li>Pricing Plan: Free</li>", "/products/56720001/sgcmapi00000001.html", "api"),
        ("", "/products/56720001/other00000001.html", "other"),
        ("", "/store/1.html", "other"),
    ],
)
async def test_reads_the_delivery_from_the_product_code(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, info: str, href: str, delivery: str
) -> None:
    found = software(await crawl_page(crawler, result_page(cards_page(card(info=info, href=href)), 1)))

    assert found["Tool"]["delivery"] == delivery


async def test_skips_a_service_product_code(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    service = card(name="Help", info="", href="/products/56720001/sgcmfw00000001.html")

    found = software(await crawl_page(crawler, result_page(cards_page(service, card(), total=2), 1)))

    assert list(found) == ["Tool"]
    assert "Skipping the product 'Help' (service)." in caplog.text


async def test_tolerates_incomplete_cards(
    crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    cards = [
        card(href=""),
        card(
            name="Bare", href="/products/999/sgcmjj00000002.html", extra='<div class="list-item-describe">Bare.</div>'
        ),
        card(name="Mute", href="/products/56720001/sgcmjj00000003.html", extra=""),
    ]

    found = software(await crawl_page(crawler, result_page(cards_page(*cards, total=3), 1)))

    assert list(found) == ["Bare"]
    assert found["Bare"]["publisher"] is None
    assert found["Bare"]["marketplace_categories"] == ["Business Software"]
    assert "Skipping a product card without link." in caplog.text
    assert "Unknown leaf category 999 of the product 'Bare'." in caplog.text
    assert "Skipping the invalid marketplace entry 'Mute'" in caplog.text


async def test_reads_a_page_without_pagination(crawler: AlibabaMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    with pytest.raises(CatalogueFormatError, match="the page 1 is not shown"):
        await crawl_page(crawler, result_page(cards_page(card(), total=0), 1))


async def test_shows_the_first_page_by_fifty(crawler: AlibabaMarketplaceCrawler) -> None:
    browser = browser_page(jump_count=1)

    await crawler._show_page(1, browser)

    assert browser.locator.call_args_list == [
        call(".next-pagination-size-selector-dropdown"),
        call(".next-menu-item", has_text="50"),
    ]
    browser.wait_for_function.assert_awaited_once_with(AlibabaMarketplaceCrawler.SIZE_APPLIED, arg=[CARD, 50])


async def test_jumps_to_a_page(crawler: AlibabaMarketplaceCrawler) -> None:
    browser = browser_page(jump_count=1)

    await crawler._show_page(12, browser)

    browser.locator.return_value.fill.assert_awaited_once_with("12")
    assert call(".next-pagination-jump-go") in browser.locator.call_args_list
    browser.wait_for_function.assert_awaited_with(AlibabaMarketplaceCrawler.PAGE_SHOWN, arg=[12, "First product"])


async def test_clicks_a_page_without_jump_box(crawler: AlibabaMarketplaceCrawler) -> None:
    browser = browser_page(jump_count=0)

    await crawler._show_page(2, browser)

    browser.locator.return_value.fill.assert_not_awaited()
    assert browser.locator.call_args_list[-1] == call("button.next-pagination-item[aria-label^='Page 2,']")
    assert browser.wait_for_function.await_count == 2
