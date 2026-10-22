from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.selectel.crawler import SelectelCrawler
from crawler.exception import EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MakeResponse = Callable[[str, str], Response]
SITEMAP_URL = "https://selectel.ru/sitemap-pages.xml"
LINK = (
    '<div class="menu-link"><a class="menu-link__title" href="{href}"><span class="menu-link__title-text">{name}</span>'
    '</a><div class="menu-link__description">{description}</div></div>'
)


def page(content: str) -> Response:
    return Response(
        url=SelectelCrawler.catalogue_url,
        content=content,
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def menu(title: str, groups: Dict[str, str]) -> str:
    inner = "".join(
        f'<div class="nav-dropdown__body-inner"><button class="nav-dropdown__return-btn '
        f'nav-dropdown__return-btn--subcategory h5">{group}</button>{links}</div>'
        for group, links in groups.items()
    )
    return f'<li class="main-nav__list-item"><button class="main-nav__list-btn">{title}</button>{inner}</li>'


def header(*menus: str) -> Response:
    return page(f'<header><ul class="main-nav__list">{"".join(menus)}</ul></header>')


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


async def fixture_products(make_response: MakeResponse, crawl_page: CrawlPage) -> List[Dict[str, JsonValue]]:
    return products(
        await crawl_page(SelectelCrawler(), make_response(SelectelCrawler.catalogue_url, "selectel_services.html"))
    )


def test_configuration() -> None:
    crawler = SelectelCrawler()

    assert crawler.name == "selectel"
    assert SelectelCrawler.catalogue_url == "https://selectel.ru/services/"
    assert SelectelCrawler.complement_urls == ()
    assert SelectelCrawler.dates_sitemaps == (SITEMAP_URL,)
    assert SelectelCrawler.name_prefixes == ("Selectel ",)
    assert crawler.allowed_domains == {"selectel.ru"}


async def test_the_sitemap_is_requested_before_the_catalogue() -> None:
    requests = [request async for request in SelectelCrawler().start_requests()]

    assert [request.url for request in requests] == [SITEMAP_URL, SelectelCrawler.catalogue_url]
    assert requests[0].meta == {SelectelCrawler.PAGE_DATES: SITEMAP_URL}


async def test_extracts_the_products_and_services_menus(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await fixture_products(make_response, crawl_page)

    assert [result["name"] for result in results] == [
        "Token Factory",
        "ИИ-Роутер",
        "Серверы с GPU",  # noqa: RUF001
        "Выделенные серверы",
        "VPS/VDS-серверы",
        "Enterprise-grade сервер",
        "Защита от DDoS",
        "Аппаратный межсетевой экран",
        "Виртуальный межсетевой экран",
        "Система обнаружения вторжений (IPS/IDS)",
        "CDN",
        "Инфраструктура для AI",
        "Серверы с GPU на вашей площадке",  # noqa: RUF001
    ]
    assert results[0] == {
        "name": "Token Factory",
        "description": "Сервис инференса актуальных открытых ИИ-моделей, развернутых в российских дата-центрах "
        "Selectel с оплатой за использованные токены",  # noqa: RUF001
        "pricing_policy": [],
        "url": "https://selectel.ru/services/cloud/token-factory/",
        "catalogue_categories": ["Продукты", "Искусственный интеллект"],
    }
    assert results[11] == {
        "name": "Инфраструктура для AI",
        "description": "Продукты для построения решений для AI и ML",
        "pricing_policy": [],
        "url": "https://selectel.ru/solutions/artificial-intelligence-machine-learning/",
        "catalogue_categories": ["Услуги", "ИИ-решения"],
    }


async def test_products_are_filed_under_the_menu_then_the_group(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await fixture_products(make_response, crawl_page)

    categories = {result["name"]: result.get("catalogue_categories") for result in results}
    assert categories["VPS/VDS-серверы"] == ["Продукты", "Серверы и вычисления"]
    assert categories["Аппаратный межсетевой экран"] == ["Продукты", "Безопасность"]
    assert categories["CDN"] == ["Продукты", "Организация сети"]
    assert categories["Серверы с GPU на вашей площадке"] == ["Услуги", "ИИ-решения"]  # noqa: RUF001


async def test_products_listed_in_several_groups_gather_them(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await fixture_products(make_response, crawl_page)

    categories = {result["name"]: result.get("catalogue_categories") for result in results}
    assert categories["Серверы с GPU"] == ["Продукты", "Искусственный интеллект", "Серверы и вычисления"]  # noqa: RUF001
    assert categories["Защита от DDoS"] == ["Продукты", "Безопасность", "Организация сети"]
    assert [result["name"] for result in results].count("Защита от DDoS") == 1


async def test_menus_and_groups_which_are_not_categories_are_not_read(
    make_response: MakeResponse, crawl_page: CrawlPage
) -> None:
    results = await fixture_products(make_response, crawl_page)

    names = {result["name"] for result in results}
    assert "Облачные серверы" not in names
    assert "GameDev" not in names
    assert "История компании" not in names
    labels = [result.get("catalogue_categories") for result in results]
    assert all(isinstance(label, list) and "Популярные" not in label for label in labels)


async def test_status_badges_and_relative_links(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await fixture_products(make_response, crawl_page)

    router = next(result for result in results if result["url"] == "https://promo.selectel.ru/ai-router")
    assert router["name"] == "ИИ-Роутер"
    assert results[0]["url"] == "https://selectel.ru/services/cloud/token-factory/"


async def test_page_sections_are_distinct_products(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    results = await fixture_products(make_response, crawl_page)

    urls = {result["name"]: result["url"] for result in results}
    assert urls["Аппаратный межсетевой экран"] == (
        "https://selectel.ru/services/additional/firewall/?section=hardwareFirewall"
    )
    assert urls["Виртуальный межсетевой экран"] == (
        "https://selectel.ru/services/additional/firewall/?section=virtualFirewall"
    )
    assert urls["Система обнаружения вторжений (IPS/IDS)"] == "https://selectel.ru/services/additional/firewall/"
    assert urls["Enterprise-grade сервер"] == "https://selectel.ru/services/dedicated/?tab=enterprise"


async def test_products_are_dated_by_the_page_sitemap(make_response: MakeResponse, crawl_page: CrawlPage) -> None:
    crawler = SelectelCrawler()
    sitemap = make_response(SITEMAP_URL, "selectel_sitemap_pages.xml")
    sitemap.meta[SelectelCrawler.PAGE_DATES] = SITEMAP_URL

    assert await crawl_page(crawler, sitemap) == []
    results = products(
        await crawl_page(crawler, make_response(SelectelCrawler.catalogue_url, "selectel_services.html"))
    )

    dated = {
        result["name"]: (result["updated_at"], result["updated_caveat"]) for result in results if "updated_at" in result
    }
    assert dated == {"Защита от DDoS": ("2025-08-08T15:13:21Z", "page-modified")}


async def test_invalid_menu_links_are_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    links = "".join(
        [
            LINK.format(href="/services/nameless/", name="", description="Без названия"),
            LINK.format(href="/services/iam/", name="IAM", description=""),
            '<div class="menu-link"><span class="menu-link__title-text">Метрики</span>'
            '<div class="menu-link__description">Контроль ресурсов</div></div>',
            LINK.format(href="https://selectel.ru/services/logs/", name="Сервис логов", description="Хранение логов"),
        ]
    )

    results = await crawl_page(SelectelCrawler(), header(menu("Продукты", {"Управление и мониторинг": links})))

    categories = ["Продукты", "Управление и мониторинг"]
    assert results == [
        {
            "name": "Метрики",
            "description": "Контроль ресурсов",
            "pricing_policy": [],
            "url": None,
            "catalogue_categories": categories,
        },
        {
            "name": "Сервис логов",
            "description": "Хранение логов",
            "pricing_policy": [],
            "url": "https://selectel.ru/services/logs/",
            "catalogue_categories": categories,
        },
    ]
    assert any(record.levelname == "WARNING" and "IAM" in record.message for record in caplog.records)
    assert any(record.levelname == "WARNING" and "''" in record.message for record in caplog.records)


async def test_page_without_menu_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(SelectelCrawler(), page("<html><body></body></html>"))

    assert any(record.levelname == "ERROR" and "holds no product" in record.message for record in caplog.records)


async def test_page_with_only_skipped_menus_is_an_error(crawl_page: CrawlPage) -> None:
    links = LINK.format(href="https://selectel.ru/careers/", name="Вакансии", description="Работа в Selectel")

    with pytest.raises(EmptyCatalogueError):
        await crawl_page(SelectelCrawler(), header(menu("Selectel", {"Карьера": links})))
