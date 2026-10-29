from __future__ import annotations

from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.exoscale.crawler import ExoscaleCrawler
from models.cloud.enums import DateCaveat
from models.cloud.products.product import CloudProduct

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]


def products(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    """Keep the products a crawler yielded (its follow-up requests left out)."""
    return [result for result in results if isinstance(result, dict)]


SITE = "https://www.exoscale.com"


def page(url: str, content: str, status: int = 200) -> Response:
    return Response(url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={})


def card(date: str, title: str, *tags: str) -> str:
    links = "".join(f"<a href=/tags/{tag}/ class=tag>{tag.upper()}</a>" for tag in tags)
    return (
        f"<div class=changelog-card><div class=card-content><div class=card-meta><time>{date}</time></div>"
        f"<h2 class=card-title><a href=/entry/>{title}</a></h2><div class=card-description>Text.</div>"
        f"<div class=card-footer><div class=card-tags>{links}</div><a href=/entry/ class=card-link>Read More</a>"
        "</div></div></div>"
    )


def changelog(*cards: str) -> Response:
    content = f"<h2 class=changelog-title>Exoscale Changelog</h2><div class=cards-grid>{''.join(cards)}</div>"
    return page(ExoscaleCrawler.CHANGELOG_URL, content)


CHANGELOG = changelog(
    card("Oct 7, 2026", "KMS now supports asymmetric encryption and digital signatures", "security", "kms"),
    card("Jul 2, 2026", "Exoscale Key Management Service (KMS) is now available", "new", "security"),
    card("Aug 14, 2026", "New on the Marketplace: Anapaya EDGE for secure SCION connectivity", "new", "marketplace"),
    card("Mar 10, 2022", "OpenSearch dashboards upgrade", "update", "dbaas"),
    card("Jan 28, 2022", "Managed OpenSearch now available", "new"),
    card("Jan 5, 2022", "OpenSearch maintenance window", "announcement"),
    card("Jul 28, 2025", "DNS: Discontinuing the SPF Record (Type 99)", "update", "dns"),
    card("Mar 31, 2021", "SKS has reached General Availability", "new", "sks"),
    card("Not a date", "Managed Grafana now available", "new"),
    card("Mar 28, 2018", "Object Storage launch"),
)


def menu_page(*entries: Tuple[str, str]) -> Response:
    items = "".join(
        f'<a class="mega__item" href="{href}"><b>{name}</b><span>A product.</span></a>' for name, href in entries
    )
    return page(ExoscaleCrawler.catalogue_url, f'<nav><div id="dropdown-products">{items}</div></nav>')


def product(name: str, url: Optional[str] = None) -> CloudProduct:
    return CloudProduct(name=name, description="A product.", url=url)


def entries() -> List[Tuple[datetime, str, Tuple[str, ...]]]:
    return ExoscaleCrawler()._changelog_entries(CHANGELOG)


def test_configuration() -> None:
    assert ExoscaleCrawler.dates_launches is True
    assert ExoscaleCrawler.launch_feed_start == datetime(2018, 6, 1, tzinfo=UTC)
    assert ExoscaleCrawler().changelog is None


def test_changelog_entries_are_dated_with_their_tag_keys() -> None:
    read = entries()

    assert len(read) == 9
    assert read[0] == (
        datetime(2026, 10, 7, tzinfo=UTC),
        "KMS now supports asymmetric encryption and digital signatures",
        ("security", "kms"),
    )
    assert "Managed Grafana now available" not in [title for _, title, _ in read]


def test_launch_is_the_earliest_launch_like_entry_naming_the_product() -> None:
    launched = ExoscaleCrawler()._first_launch(entries(), product("OpenSearch", f"{SITE}/dbaas/opensearch/"))

    assert launched == datetime(2022, 1, 28, tzinfo=UTC)


def test_a_product_is_named_by_its_name_or_by_its_page_slug_as_a_tag_or_a_title_word() -> None:
    crawler = ExoscaleCrawler()
    kms = product("Key Management Service", "https://community.exoscale.com/product/security/kms/")
    sks = product("Managed Kubernetes", f"{SITE}/sks/")

    assert crawler._first_launch(entries(), kms) == datetime(2026, 7, 2, tzinfo=UTC)
    assert crawler._first_launch(entries(), sks) == datetime(2021, 3, 31, tzinfo=UTC)
    assert crawler._first_launch(entries(), product("Exoscale Object Storage")) == datetime(2018, 3, 28, tzinfo=UTC)


def test_a_mere_update_or_a_partner_entry_dates_nothing() -> None:
    crawler = ExoscaleCrawler()

    assert crawler._first_launch(entries(), product("DNS", f"{SITE}/dns/")) is None
    assert crawler._first_launch(entries(), product("Scion Network", f"{SITE}/scion-network/")) is None
    assert crawler._first_launch(entries(), product("Grafana", f"{SITE}/grafana/")) is None


def test_names_are_matched_on_whole_words() -> None:
    crawler = ExoscaleCrawler()
    words = changelog(card("Jan 28, 2020", "Williams release", "new"))

    assert crawler._first_launch(crawler._changelog_entries(words), product("IAM")) is None


async def test_a_launch_before_the_feed_start_may_be_older(dated_source: MagicMock) -> None:
    dated_source.get.return_value = CHANGELOG
    crawler = ExoscaleCrawler()

    assert await crawler._launch_source(product("Object Storage", f"{SITE}/object-storage/")) == (
        datetime(2018, 3, 28, tzinfo=UTC),
        DateCaveat.FEED_START,
    )
    assert await crawler._launch_source(product("OpenSearch")) == (
        datetime(2022, 1, 28, tzinfo=UTC),
        DateCaveat.FIRST_ANNOUNCEMENT,
    )


async def test_a_changelog_without_entries_dates_nothing(dated_source: MagicMock) -> None:
    dated_source.get.return_value = page(ExoscaleCrawler.CHANGELOG_URL, "<h1>Page not found</h1>")
    crawler = ExoscaleCrawler()

    assert await crawler._launch_source(product("OpenSearch")) is None
    assert crawler.changelog == []


async def test_crawler_dates_the_products_from_a_single_changelog_fetch(
    crawl_page: CrawlPage, dated_source: MagicMock
) -> None:
    dated_source.get.return_value = CHANGELOG
    crawler = ExoscaleCrawler()
    menu = menu_page(("OpenSearch", "/dbaas/opensearch/"), ("Key Management Service", "/kms/"), ("DNS", "/dns/"))

    results = products(await crawl_page(crawler, menu))

    assert dated_source.get.call_count == 1
    assert dated_source.get.call_args.args[0] == "https://changelog.exoscale.com/"
    dated = {result["name"]: result.get("added_at") for result in results if isinstance(result, dict)}
    assert dated == {
        "OpenSearch": "2022-01-28T00:00:00Z",
        "Key Management Service": "2026-07-02T00:00:00Z",
        "DNS": None,
    }
    assert crawler.undated == {"DNS"}


async def test_a_missing_changelog_leaves_the_products_undated(crawl_page: CrawlPage) -> None:
    crawler = ExoscaleCrawler()

    results = products(await crawl_page(crawler, menu_page(("OpenSearch", "/dbaas/opensearch/"))))

    assert [result["name"] for result in results if isinstance(result, dict)] == ["OpenSearch"]
    assert "added_at" not in results[0]
    assert crawler.undated == {"OpenSearch"}


async def test_a_new_crawl_reads_the_changelog_again_unless_resumed(dated_source: MagicMock) -> None:
    dated_source.get.return_value = CHANGELOG
    crawler = ExoscaleCrawler()
    await crawler._launch_source(product("OpenSearch"))

    await crawler.on_start(resuming=True)
    assert crawler.changelog is not None
    await crawler.on_start(resuming=False)
    assert crawler.changelog is None
