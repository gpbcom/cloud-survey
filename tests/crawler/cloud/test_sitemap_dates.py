from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Type, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ovh.crawler import OVHcloudCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler

SitemapCrawler = Union[Type[STACKITCrawler], Type[TCloudPublicCrawler], Type[OVHcloudCrawler]]


@pytest.mark.parametrize(
    ("sitemap_crawler", "fixture"),
    [
        (STACKITCrawler, "stackit_sitemap.xml"),
        (TCloudPublicCrawler, "tcloud_sitemap.xml"),
        (OVHcloudCrawler, "ovh_sitemap.xml"),
    ],
)
async def test_sitemap_is_read_first_for_the_dates_then_for_the_pages(
    sitemap_crawler: SitemapCrawler,
    fixture: str,
    make_response: Callable[[str, str], Response],
    crawl_page: Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]],
) -> None:
    crawler = sitemap_crawler()
    starts = [request async for request in crawler.start_requests()]
    dates = make_response(sitemap_crawler.SITEMAP_URL, fixture)
    dates.meta[BaseCloudCrawler.PAGE_DATES] = sitemap_crawler.SITEMAP_URL

    assert (starts[0].url, starts[0].meta) == (
        sitemap_crawler.SITEMAP_URL,
        {BaseCloudCrawler.PAGE_DATES: sitemap_crawler.SITEMAP_URL},
    )
    assert await crawl_page(crawler, dates) == []
    assert crawler.page_dates
    pages = await crawl_page(crawler, make_response(sitemap_crawler.SITEMAP_URL, fixture))
    assert pages
    assert all(isinstance(request, Request) for request in pages)
