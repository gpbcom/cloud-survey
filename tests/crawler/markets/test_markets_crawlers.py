from __future__ import annotations

import itertools
import json
from datetime import date
from typing import Awaitable, Callable, Dict, List, Union
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import UnknownCrawlerTargetError
from crawler.factory import CrawlerFactory
from crawler.markets.fred.crawler import FredCrawler
from crawler.markets.google_finance.crawler import GoogleFinanceCrawler
from crawler.markets.statcounter.crawler import StatCounterCrawler
from crawler.markets.worldbank.crawler import WorldBankCrawler
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import Device, MarketFeed, StatCounterStat, WeightIndicator
from models.markets.facts.fx_observation import FxObservation
from models.markets.facts.price_point import PricePoint
from models.markets.facts.share_observation import ShareObservation
from models.markets.facts.weight_observation import WeightObservation
from models.markets.markets_catalog import MarketsCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MarketPage = Callable[[str, str, Dict[str, JsonValue]], Response]
STATCOUNTER = "https://gs.statcounter.com/chart.php?csv=1"


def statcounter_meta(stat: str, area: str, device: str, first: str) -> Dict[str, JsonValue]:
    return {"statcounter_stat": stat, "statcounter_area": area, "statcounter_device": device, "statcounter_from": first}


class TestStatCounter:
    async def test_one_csv_per_area_segment_and_device(self, markets_catalog: MarketsCatalog) -> None:
        crawler = StatCounterCrawler(markets_catalog, CrawlScope(areas="US,eu27,XX", since="2026-01"))

        requests = [request async for request in crawler.start_requests()]

        devices = sum(len(segment.devices) for segment in markets_catalog.statcounter_segments())
        assert len(requests) == devices, "the union and the unknown area are left out"
        query = parse_qs(urlparse(requests[0].url).query)
        assert query["region_hidden"] == ["US"]
        assert query["csv"] == ["1"]
        assert query["fromInt"] == ["202601"]
        assert query["device_hidden"] == ["desktop+mobile+tablet+console"]
        chatbots = [request for request in requests if request.meta["statcounter_stat"] == "ai_chatbot"]
        assert {request.meta["statcounter_from"] for request in chatbots} == {"2026-01"}

    async def test_the_ai_chatbots_start_in_april_2025(self, markets_catalog: MarketsCatalog) -> None:
        requests = [
            request async for request in StatCounterCrawler(markets_catalog, CrawlScope(areas="ww")).start_requests()
        ]

        firsts = {request.meta["statcounter_stat"]: request.meta["statcounter_from"] for request in requests}
        assert firsts["ai_chatbot"] == "2025-04"
        assert firsts["search_engine"] == "2009-01"

    async def test_the_shares_are_read_without_zeros_and_padding(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            STATCOUNTER, "statcounter-us-search.csv", statcounter_meta("search_engine", "US", "all", "2024-01")
        )

        shares = [
            ShareObservation.model_validate(item)
            for item in await crawl_page(StatCounterCrawler(markets_catalog), page)
        ]

        assert shares
        assert min(share.month for share in shares) == date(2024, 1, 1), "the months before are left out"
        assert all(share.value > 0 for share in shares)
        assert {share.stat for share in shares} == {StatCounterStat.SEARCH_ENGINE}
        assert {share.area for share in shares} == {"US"}
        assert {share.device for share in shares} == {Device.ALL}
        google = [share for share in shares if share.label == "Google"]
        assert len(google) == len({share.month for share in shares})
        assert all(70 < share.value < 95 for share in google)

    async def test_the_whole_history_is_read_from_2009(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            STATCOUNTER, "statcounter-europe-mobile-os.csv", statcounter_meta("os_combined", "eu", "mobile", "2009-01")
        )

        shares = [
            ShareObservation.model_validate(item)
            for item in await crawl_page(StatCounterCrawler(markets_catalog), page)
        ]

        months = {share.month for share in shares}
        assert min(months) == date(2009, 1, 1)
        assert len(months) >= 200, "monthly points enough to correlate"
        symbian = {share.month: share.value for share in shares if share.label == "SymbianOS"}
        assert symbian[date(2009, 1, 1)] > 30, "Symbian led Europe's mobile OS in 2009"

    async def test_a_page_that_is_not_a_csv_gives_nothing(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            STATCOUNTER, "worldbank-internet-users.json", statcounter_meta("browser", "US", "all", "2009-01")
        )

        assert await crawl_page(StatCounterCrawler(markets_catalog), page) == []


class TestGoogleFinance:
    async def test_one_rpc_per_listing(self, markets_catalog: MarketsCatalog) -> None:
        crawler = GoogleFinanceCrawler(markets_catalog, CrawlScope(listings="TPE:2330,XXX:YYY"))

        requests = [request async for request in crawler.start_requests()]

        assert len(requests) == 1
        request = requests[0]
        assert request._session_kwargs["method"] == "POST"
        assert request._session_kwargs["headers"]["X-Same-Domain"] == "1"
        assert "SOCS=" in request._session_kwargs["headers"]["Cookie"]
        envelope = json.loads(parse_qs(request._session_kwargs["data"])["f.req"][0])
        assert envelope[0][0][0] == "c2u4wc"
        assert json.loads(envelope[0][0][1])[:2] == [[[None, ["2330", "TPE"]]], 8]
        assert parse_qs(urlparse(request.url).query)["source-path"] == ["/finance/beta/quote/2330:TPE"]

    async def test_the_weekly_closes_are_decoded(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(
            "https://www.google.com/finance/beta/_/FinHubUi/data/batchexecute",
            "google-finance-tsmc.txt",
            {"google_finance_listing": "TPE:2330", "google_finance_candidate": 0},
        )

        prices = [
            PricePoint.model_validate(item) for item in await crawl_page(GoogleFinanceCrawler(markets_catalog), page)
        ]

        assert len(prices) > 1000
        assert prices[0].day == date(2000, 1, 7)
        assert prices[0].close == pytest.approx(64.88)
        assert {price.currency for price in prices} == {"TWD"}
        assert {price.listing for price in prices} == {"TPE:2330"}
        assert all(later.day > earlier.day for earlier, later in itertools.pairwise(prices))
        assert prices[0].volume == 181337366

    async def test_no_series_asks_the_next_exchange_code(
        self, markets_catalog: MarketsCatalog, crawl_page: CrawlPage
    ) -> None:
        catalog = markets_catalog.model_copy(
            update={
                "listings": [
                    *markets_catalog.listings,
                    markets_catalog.listings[0].model_copy(update={"symbol": "FWB:SAP", "company": "sap"}),
                ]
            }
        )
        empty = Response(
            url="https://www.google.com/finance/beta/_/FinHubUi/data/batchexecute",
            content=b')]}\'\n\n25\n[["wrb.fr","c2u4wc","[]"]]\n',
            status=200,
            reason="OK",
            cookies={},
            headers={},
            request_headers={},
            meta={"google_finance_listing": "FWB:SAP", "google_finance_candidate": 0},
        )

        results = await crawl_page(GoogleFinanceCrawler(catalog), empty)

        assert len(results) == 1
        assert isinstance(results[0], Request)
        assert "SAP%3AFRA" in results[0].url, "FWB is filed under ETR, then FRA"

    async def test_the_consent_wall_gives_nothing(self, markets_catalog: MarketsCatalog, crawl_page: CrawlPage) -> None:
        wall = Response(
            url="https://consent.google.com/ml?continue=x",
            content=b"<html>Before you continue</html>",
            status=200,
            reason="OK",
            cookies={},
            headers={},
            request_headers={},
            meta={"google_finance_listing": "NYSE:IBM", "google_finance_candidate": 0},
        )

        results = await crawl_page(GoogleFinanceCrawler(markets_catalog), wall)

        assert [item for item in results if isinstance(item, dict)] == []


class TestFredAndWorldBank:
    async def test_one_csv_per_currency_since_the_scope(self, markets_catalog: MarketsCatalog) -> None:
        requests = [
            request async for request in FredCrawler(markets_catalog, CrawlScope(since="2026-08")).start_requests()
        ]

        assert [request.meta["fred_series"] for request in requests] == [
            entry.series for entry in markets_catalog.currencies
        ]
        assert parse_qs(urlparse(requests[0].url).query)["cosd"] == ["2026-08-01"]

    async def test_the_rates_are_read_as_quoted(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        page = market_page(FredCrawler.URL, "fred-dexjpus.csv", {"fred_series": "DEXJPUS"})

        rates = [FxObservation.model_validate(item) for item in await crawl_page(FredCrawler(markets_catalog), page)]

        assert rates
        assert {rate.series for rate in rates} == {"DEXJPUS"}
        assert rates[0].day == date(2026, 8, 3)
        assert rates[0].value == pytest.approx(156.96)

    async def test_the_union_members_are_weighted(
        self, markets_catalog: MarketsCatalog, market_page: MarketPage, crawl_page: CrawlPage
    ) -> None:
        requests = [request async for request in WorldBankCrawler(markets_catalog).start_requests()]
        page = market_page(requests[0].url, "worldbank-internet-users.json", {"worldbank_indicator": "IT.NET.USER.ZS"})

        weights = [
            WeightObservation.model_validate(item) for item in await crawl_page(WorldBankCrawler(markets_catalog), page)
        ]

        assert len(requests) == 2
        assert "AT;BE;BG" in requests[0].url
        assert ";US;" in requests[0].url, "the home countries of the providers"
        assert ";CN;" in requests[0].url
        assert {weight.indicator for weight in weights} == {WeightIndicator.INTERNET_USERS}
        assert {weight.country for weight in weights} == {"DE", "FR", "MT"}
        assert all(weight.year < 2025 for weight in weights if weight.country == "DE"), "the null years are left out"


def test_the_factory_builds_every_markets_crawler(
    markets_catalog: MarketsCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = CrawlerFactory()

    assert isinstance(factory.get_markets(MarketFeed.STATCOUNTER, markets_catalog), StatCounterCrawler)
    assert list(factory.MARKETS_MAP) == [
        MarketFeed.FRED,
        MarketFeed.WORLD_BANK,
        MarketFeed.GOOGLE_FINANCE,
        MarketFeed.STATCOUNTER,
        MarketFeed.TRENDFORCE,
        MarketFeed.IDC,
    ]
    monkeypatch.setattr(factory, "MARKETS_MAP", {MarketFeed.STATCOUNTER: StatCounterCrawler})
    with pytest.raises(UnknownCrawlerTargetError):
        factory.get_markets(MarketFeed.FRED, markets_catalog)
