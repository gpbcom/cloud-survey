from __future__ import annotations

import json
from datetime import date
from typing import Awaitable, Callable, Dict, List, Union
from urllib.parse import parse_qs, urlparse

from pydantic import JsonValue
from scrapling.spiders import Request, Response

from conftest import FIXTURES_DIR
from crawler.cloud.base import BaseCloudCrawler
from crawler.markets.idc.crawler import IdcCrawler
from crawler.markets.press.sentence_reader import PressSentenceReader
from crawler.markets.press.table_reader import PressTableReader
from crawler.markets.trendforce.crawler import TrendForceCrawler
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import Granularity
from models.markets.facts.release_share import ReleaseShare
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MarketPage = Callable[[str, str, Dict[str, JsonValue]], Response]
Q = Granularity.QUARTER
RELEASE = "https://www.trendforce.com/presscenter/news/20260909-13225.html"
NAMES = ["TSMC", "Samsung", "SK hynix", "Micron", "Intel", "Hynix"]


def release_meta(title: str, published: str, family: int) -> Dict[str, JsonValue]:
    return {
        "trendforce_kind": "release",
        "trendforce_title": title,
        "trendforce_published": published,
        "trendforce_family": family,
    }


def shares(items: List[Union[Dict[str, JsonValue], Request]]) -> List[ReleaseShare]:
    return [ReleaseShare.model_validate(item) for item in items if isinstance(item, dict)]


class TestSentenceReader:
    def test_shares_go_to_the_company_named_or_referred_to(self) -> None:
        text = (
            "TSMC kept the lead, capturing a 72.5% market share. Samsung ranked second. Its market share fell to "
            "5.9% as rivals grew. The own brand market share grew to 17.4%. Taiwanese vendors' share rose to 13.6%. "
            "Micron's revenue increased 9.6% QoQ."
        )

        read = PressSentenceReader().read(text, NAMES, (date(2026, 4, 1), Q))

        assert [(label, value) for label, _, _, value in read] == [("TSMC", 72.5), ("Samsung", 5.9)]

    def test_group_shares_changes_and_totals_are_not_read(self) -> None:
        text = (
            "Samsung revenue fell. Korean vendors\u2019 market share reached 63.7%. In total, these two South Korean "
            "manufacturers account for a market share of 70.8%. Micron took 0.5% market share growth. "
            "Its revenue share stood at 100%. Elpida came third with 12.0% market share. Winbond stays cautious, "
            "and by country, Korean vendors\u2019 market share reached 63.7%."
        )

        read = PressSentenceReader().read(text, [*NAMES, "Elpida"], (date(2012, 4, 1), Q))

        assert [(label, value) for label, _, _, value in read] == [("Elpida", 12.0)]

    def test_a_share_takes_the_period_stated_after_or_before_it(self) -> None:
        text = "Samsung led with 38.6% market share. As for 2009 yearly basis, Samsung held 37.9% market share. Intel recorded 6.9% market share in 2009."  # noqa: E501

        read = {
            (label, day): value
            for label, day, _, value in PressSentenceReader().read(text, NAMES, (date(2009, 10, 1), Q))
        }

        assert read == {
            ("Samsung", date(2009, 10, 1)): 38.6,
            ("Samsung", date(2009, 1, 1)): 37.9,
            ("Intel", date(2009, 1, 1)): 6.9,
        }

    def test_a_period_summing_above_100_is_left_out(self) -> None:
        text = "TSMC holds 70% market share. Samsung holds 40% market share."

        assert PressSentenceReader().read(text, NAMES, (date(2026, 4, 1), Q)) == []


class TestTableReader:
    def test_every_share_column_of_a_company_table_is_read(self) -> None:
        fragment = (
            "<table><tr><td>Top 5 Companies, Worldwide Traditional PC Shipments</td></tr>"
            "<tr><th>Company</th><th>2Q26 Shipments</th><th>2Q26 Market Share</th><th>2Q25 Market Share</th></tr>"
            "<tr><td>1. Lenovo</td><td>16.6</td><td>24.4%</td><td>23.7%</td></tr>"
            "<tr><td>3.Dell Technologies*</td><td>9.3</td><td>13.6%</td><td></td></tr>"
            "<tr><td>Total</td><td>68.2</td><td>100.0%</td><td>100.0%</td></tr></table>"
            "<table><tr><th>Region</th><th>2Q26 Share</th></tr><tr><td>EMEA</td><td>30%</td></tr></table>"
        )

        tables = PressTableReader().read(fragment)

        assert len(tables) == 1
        caption, read = tables[0]
        assert caption == "Top 5 Companies, Worldwide Traditional PC Shipments"
        assert read == [
            ("Lenovo", date(2026, 4, 1), Q, 24.4),
            ("Lenovo", date(2025, 4, 1), Q, 23.7),
            ("Dell Technologies", date(2026, 4, 1), Q, 13.6),
        ]
        assert PressTableReader().read(fragment, complete=True) == [], "the columns sum to 38% and 23.7%: partial"


class TestTrendForce:
    async def test_the_listing_leads_to_the_matching_releases_and_the_next_page(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            TrendForceCrawler.LISTING_URL.format(page=1),
            "trendforce-listing.html",
            {"trendforce_kind": "listing", "trendforce_page": 1},
        )

        requests = [
            item for item in await crawl_page(TrendForceCrawler(markets_catalog), page) if isinstance(item, Request)
        ]

        assert requests[-1].url.endswith("page=2")
        assert all(request.meta["trendforce_kind"] == "release" for request in requests[:-1])

    async def test_a_listing_older_than_the_scope_ends_the_walk(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            TrendForceCrawler.LISTING_URL.format(page=1),
            "trendforce-listing.html",
            {"trendforce_kind": "listing", "trendforce_page": 1},
        )

        requests = await crawl_page(TrendForceCrawler(markets_catalog, CrawlScope(since="2030-01")), page)

        assert requests == []

    async def test_a_foundry_release_gives_the_shares_its_sentences_state(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        title = "Global Foundry Revenue Approaches US$53.49 Billion in 2Q26 as SMIC Narrows Market Share Gap with Samsung, Says TrendForce"  # noqa: E501
        crawler = TrendForceCrawler(markets_catalog)
        family = crawler._family(title)
        assert family is not None
        page = market_page(RELEASE, "trendforce-foundry-2q26.html", release_meta(title, "2026-09-09", family[0]))

        read = shares(await crawl_page(crawler, page))

        assert {share.segment for share in read} == {"foundry"}
        assert {share.period for share in read} == {date(2026, 4, 1)}
        assert [(share.label, share.value) for share in read] == [
            ("TSMC", 72.5),
            ("Samsung", 5.9),
            ("SMIC", 5.4),
            ("UMC", 3.9),
            ("GlobalFoundries", 3.2),
        ]

    async def test_older_releases_give_their_quarter_and_their_year(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        title = "4Q09 and 2009 Sales Ranking of Branded NAND Flash IC Makers"
        crawler = TrendForceCrawler(markets_catalog)
        family = crawler._family(title)
        assert family is not None
        page = market_page(RELEASE, "trendforce-nand-4q09.html", release_meta(title, "2010-02-01", family[0]))

        read = {
            (share.label, share.period, share.granularity): share.value
            for share in shares(await crawl_page(crawler, page))
        }

        assert read[("Samsung", date(2009, 10, 1), Q)] == 38.6
        assert read[("Samsung", date(2009, 1, 1), Granularity.YEAR)] == 37.9

    async def test_a_share_of_no_company_is_not_read(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        title = "Q109 Revenue of WW DRAM Industry Declined 22.3%, say DRAMeXchange"
        crawler = TrendForceCrawler(markets_catalog)
        family = crawler._family(title)
        assert family is not None
        page = market_page(RELEASE, "trendforce-dram-1q09.html", release_meta(title, "2009-05-12", family[0]))

        read = shares(await crawl_page(crawler, page))

        assert [(share.label, share.value) for share in read] == [("Micron", 15.3)]


class TestIdc:
    async def test_one_search_per_term_since_the_scope(self, markets_catalog: MarketsCatalog) -> None:
        requests = [
            request async for request in IdcCrawler(markets_catalog, CrawlScope(since="2025-01")).start_requests()
        ]

        queries = [parse_qs(urlparse(request.url).query) for request in requests]
        assert [query["search"][0] for query in queries] == ["smartphone", "PC", "tablet"]
        assert {query["after"][0] for query in queries} == {"2025-01-01T00:00:00"}

    async def test_each_table_goes_to_its_family(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(IdcCrawler.API_URL, "idc-press-releases.json", {"idc_search": "PC", "idc_page": 1})

        items = await crawl_page(IdcCrawler(markets_catalog), page)

        read = shares(items)
        families = {(share.segment, share.area) for share in read}
        assert families == {("pcs", "ww"), ("smartphones", "ww"), ("tablets", "IN"), ("smartphones", "IN")}
        lenovo = {share.period: share.value for share in read if share.segment == "pcs" and share.label == "Lenovo"}
        assert len(lenovo) == 2, "the quarter and the quarter a year before"
        assert not [item for item in items if isinstance(item, Request)], (
            "a page of fewer than 100 releases is the last"
        )
        assert all(not share.label[0].isdigit() for share in read)

    def test_a_caption_naming_a_product_wins_over_the_title(self, markets_catalog: MarketsCatalog) -> None:
        crawler = IdcCrawler(markets_catalog)
        title = "Tablets Grow While Chromebooks Fall in Q3 2025"

        tablet = crawler._family(title, "Top Five Tablet Companies, Worldwide Shipments")
        chromebook = crawler._family(title, "Top Five Chromebook Companies, Worldwide Shipments")
        plain = crawler._family("Tablet Market Levels Off in 3Q 2025", "Worldwide Shipments")

        assert tablet is not None
        assert tablet[1].segment == "tablets"
        assert chromebook is None
        assert plain is not None
        assert plain[1].segment == "tablets"

    async def test_a_full_page_asks_the_next_one(self, markets_catalog: MarketsCatalog, crawl_page: CrawlPage) -> None:
        posts = json.loads((FIXTURES_DIR / "markets" / "idc-press-releases.json").read_text(encoding="utf-8"))
        full = [{**posts[0], "id": index} for index in range(IdcCrawler.PER_PAGE)]
        page = Response(
            url=IdcCrawler.API_URL,
            content=json.dumps(full).encode(),
            status=200,
            reason="OK",
            cookies={},
            headers={},
            request_headers={},
            meta={"idc_search": "PC", "idc_page": 1},
        )

        requests = [item for item in await crawl_page(IdcCrawler(markets_catalog), page) if isinstance(item, Request)]

        assert len(requests) == 1
        assert parse_qs(urlparse(requests[0].url).query)["page"] == ["2"]
