from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Tuple, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import CatalogueFormatError
from crawler.stats.synergy import SynergyResearchCrawler
from models.cloud.enums import MarketRegion, MarketSegment
from models.stats.market_report import MarketReport

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
# A share: the player, the share, the band (if any), whether it is approximate and the aggregate including it.
Share = Tuple[str, float, Optional[Tuple[float, float]], bool, Optional[str]]

STATS_FIXTURES = Path(__file__).parents[2] / "fixtures" / "stats"
ARTICLE_URL = "https://www.srgresearch.com/articles/an-article"
CIS = MarketSegment.CLOUD_INFRASTRUCTURE.value
PUBLIC = MarketSegment.PUBLIC_IAAS_PAAS.value
SIZE_SENTENCE = (
    "Synergy estimates that quarterly cloud infrastructure service revenues (including IaaS, PaaS and hosted private "
    "cloud services) were $90.6 billion."
)


def page(url: str, content: Union[str, bytes]) -> Response:
    return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def fixture_page(url: str, fixture: str) -> Response:
    return page(url, (STATS_FIXTURES / fixture).read_bytes())


def fixture_text(fixture: str) -> str:
    return (STATS_FIXTURES / fixture).read_text(encoding="utf-8")


def article(body: str, dateline: str = "RENO, NV, February 6, 2025", alt: str = "", title: str = "A title") -> Response:
    heading = f"<h2>{title}</h2>" if title else ""
    image = f'<img src="chart.jpg" alt="{alt}">' if alt else ""
    html = f'<html><body><div class="article">{heading}<div>{dateline}</div><p>{body}</p>{image}</div></body></html>'
    return page(ARTICLE_URL, html)


def reports(results: List[Union[Dict[str, JsonValue], Request]]) -> List[MarketReport]:
    return [MarketReport.model_validate(result) for result in results if isinstance(result, dict)]


def report_of(results: List[Union[Dict[str, JsonValue], Request]], period: str, segment: str = CIS) -> MarketReport:
    return next(report for report in reports(results) if report.period == period and report.segment == segment)


def shares(report: MarketReport) -> List[Share]:
    return [
        (
            share.player.value,
            share.share_pct,
            (share.share_low_pct, share.share_high_pct)
            if share.share_low_pct is not None and share.share_high_pct is not None
            else None,
            share.approximate,
            share.part_of.value if share.part_of else None,
        )
        for share in report.shares
    ]


def slugs(results: List[Union[Dict[str, JsonValue], Request]]) -> List[str]:
    return [result.url.rsplit("/", 1)[1] for result in results if isinstance(result, Request)]


def logged(caplog: pytest.LogCaptureFixture, level: str, text: str) -> bool:
    return any(record.levelname == level and text in record.getMessage() for record in caplog.records)


def test_configuration() -> None:
    crawler = SynergyResearchCrawler()

    assert crawler.name == "synergy"
    assert SynergyResearchCrawler.source == "Synergy Research Group"
    assert SynergyResearchCrawler.download_delay == 1.5
    assert SynergyResearchCrawler.catalogue_url == "https://www.srgresearch.com/articles"
    assert SynergyResearchCrawler.complement_urls == (
        "https://web.archive.org/cdx/search/cdx?url=srgresearch.com/articles/&matchType=prefix&fl=original"
        "&collapse=urlkey&filter=statuscode:200&output=json",
    )
    assert crawler.allowed_domains == {"www.srgresearch.com", "web.archive.org"}
    assert crawler.requested_slugs == set()


async def test_listing_requests_the_cloud_market_articles(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()

    results = await crawl_page(crawler, fixture_page(crawler.ARTICLES_URL, "synergy_listing.html"))

    requested = slugs(results)
    assert len(requested) == 18
    assert requested[:3] == [
        "q2-cloud-market-passes-143-billion-highest-growth-rate-in-eight-years",
        "cloud-market-annual-revenue-run-rate-topped-half-a-trillion-dollars-in-q1-as-growth-surge-continues",
        "genai-helps-drive-quarterly-cloud-revenues-to-119-billion-as-growth-rate-jumped-yet-again-in-q4",
    ]
    assert "european-cloud-providers-local-market-share-now-holds-steady-at-15" in requested
    assert (
        "cloud-market-share-trends-big-three-together-hold-63-while-oracle-and-the-neoclouds-inch-higher" in requested
    )
    assert "hyperscale-operators-to-account-for-67-of-all-data-center-capacity-by-2031" not in requested
    assert all(isinstance(result, Request) for result in results)
    assert all(
        isinstance(result, Request) and result.url.startswith("https://www.srgresearch.com/articles/")
        for result in results
    )


async def test_listing_requests_each_article_once(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    crawler = SynergyResearchCrawler()
    links = (
        '<li><a class="text-body" href="/research">Cloud Market Research</a></li>'
        '<li><a class="text-body" href="/articles/q1-cloud-market">Q1 Cloud Market</a></li>'
        '<li><a class="text-body" href="/articles/q1-cloud-market/">Q1 Cloud Market Again</a></li>'
    )
    listing = page(crawler.ARTICLES_URL + "/", f'<ul class="bar-style">{links}</ul>')

    with caplog.at_level(logging.DEBUG):
        results = await crawl_page(crawler, listing)

    assert slugs(results) == ["q1-cloud-market"]
    assert logged(caplog, "DEBUG", "'Cloud Market Research', not a cloud market article")
    assert logged(caplog, "DEBUG", "Not requesting the synergy article q1-cloud-market again")


async def test_listing_without_article_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    crawler = SynergyResearchCrawler()

    with pytest.raises(CatalogueFormatError, match="lists no article"):
        await crawl_page(crawler, page(crawler.ARTICLES_URL, "<html><body><ul></ul></body></html>"))

    assert logged(caplog, "ERROR", "press releases page https://www.srgresearch.com/articles lists no article")


async def test_archive_requests_the_older_articles_not_listed(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()
    await crawl_page(crawler, fixture_page(crawler.ARTICLES_URL, "synergy_listing.html"))

    results = await crawl_page(crawler, fixture_page(crawler.CDX_URL, "synergy_cdx.json"))

    assert slugs(results) == [
        "2015-review-shows-110-billion-cloud-market-growing-28-annually",
        "amazon-and-microsoft-maintain-their-grip-market-others-are-also-growing-rapidly",
        "quarterly-cloud-spending-blows-past-30b-incremental-growth-continues-rise",
        "cisco-and-hp-tied-cloud-infrastructure-equipment-leadership-q1",
        "european-cloud-providers-double-in-size-but-lose-market-share",
    ]
    assert all(
        isinstance(result, Request) and result.url.startswith("https://www.srgresearch.com/articles/")
        for result in results
    )


async def test_archive_skips_the_malformed_rows(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()
    rows = (
        '[["original"], [], [1], "https://www.srgresearch.com/articles/q1-cloud-market", ["/articles/q2-cloud-market"]]'
    )

    results = await crawl_page(crawler, page(crawler.CDX_URL, rows))

    assert slugs(results) == ["q2-cloud-market"]


@pytest.mark.parametrize(("body", "reason"), [('{"rows": []}', "not a JSON array"), ("<html></html>", "is not JSON")])
async def test_archive_listing_not_json_array_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, body: str, reason: str
) -> None:
    crawler = SynergyResearchCrawler()

    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(crawler, page(crawler.CDX_URL, body))

    assert any(record.levelname == "ERROR" and reason in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("fixture", "period", "size", "twelve_month", "growth", "expected", "methodology_break"),
    [
        (
            "synergy_q2_2026.html",
            "2026Q2",
            143.4,
            500.0,
            43.0,
            [
                ("amazon", 28.0, None, False, None),
                ("microsoft", 20.0, None, False, None),
                ("google", 15.0, None, False, None),
            ],
            False,
        ),
        (
            "synergy_q1_2026.html",
            "2026Q1",
            128.6,
            455.0,
            35.0,
            [
                ("amazon", 28.0, None, False, None),
                ("microsoft", 21.0, None, False, None),
                ("google", 14.0, None, False, None),
            ],
            False,
        ),
        (
            "synergy_q4_2025.html",
            "2025Q4",
            119.1,
            419.0,
            30.0,
            [
                ("amazon", 28.0, None, False, None),
                ("microsoft", 21.0, None, False, None),
                ("google", 14.0, None, False, None),
            ],
            False,
        ),
        (
            "synergy_q3_2025.html",
            "2025Q3",
            106.9,
            390.0,
            28.0,
            [
                ("amazon", 29.0, None, False, None),
                ("microsoft", 20.0, None, False, None),
                ("google", 13.0, None, False, None),
            ],
            False,
        ),
        (
            "synergy_share_trend_2025.html",
            "2025Q3",
            106.9,
            390.0,
            None,
            [
                ("big-three", 63.0, None, False, None),
                ("amazon", 29.0, None, False, "big-three"),
                ("microsoft", 20.0, None, False, "big-three"),
                ("google", 13.0, None, False, "big-three"),
            ],
            False,
        ),
        (
            "synergy_q3_2024.html",
            "2024Q3",
            83.8,
            313.0,
            23.0,
            [
                ("amazon", 31.0, None, False, None),
                ("microsoft", 20.0, None, False, None),
                ("google", 13.0, None, False, None),
            ],
            True,
        ),
        (
            "synergy_q2_2023.html",
            "2023Q2",
            64.8,
            247.0,
            18.0,
            [
                ("big-three", 65.0, None, False, None),
                ("amazon", 33.0, (32.0, 34.0), False, "big-three"),
                ("microsoft", 22.0, None, False, "big-three"),
                ("google", 11.0, None, False, "big-three"),
            ],
            False,
        ),
        (
            "synergy_q4_2022.html",
            "2022Q4",
            61.6,
            227.0,
            21.0,
            [
                ("big-three", 66.0, None, False, None),
                ("amazon", 33.0, (32.0, 34.0), False, "big-three"),
                ("microsoft", 23.0, None, False, "big-three"),
                ("google", 11.0, None, False, "big-three"),
            ],
            False,
        ),
    ],
)
async def test_worldwide_release(
    crawl_page: CrawlPage,
    fixture: str,
    period: str,
    size: float,
    twelve_month: float,
    growth: Optional[float],
    expected: List[Share],
    methodology_break: bool,
) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, fixture))

    report = report_of(results, period)
    assert report.region is MarketRegion.WORLDWIDE
    assert report.currency == "USD"
    assert (report.market_size_bn, report.twelve_month_bn, report.growth_pct) == (size, twelve_month, growth)
    assert shares(report) == expected
    assert report.methodology_break is methodology_break
    assert report.source_url == ARTICLE_URL


async def test_release_source_fields(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_q2_2026.html"))

    report = report_of(results, "2026Q2")
    assert report.title == "Q2 Cloud Market Passes $143 Billion; Highest Growth Rate in Eight Years"
    assert report.published == date(2026, 7, 30)
    others = report.others()
    assert others is not None
    assert others.share_pct == 37.0


@pytest.mark.parametrize(
    ("fixture", "period", "growth", "big_three", "methodology_break"),
    [
        ("synergy_q2_2026.html", "2026Q2", 47.0, [("big-three", 67.0, None, False, None)], False),
        ("synergy_q3_2024.html", "2024Q3", 24.0, [("big-three", 68.0, None, False, None)], True),
        ("synergy_share_trend_2025.html", "2025Q3", 30.0, [], False),
    ],
)
async def test_public_iaas_paas_report(
    crawl_page: CrawlPage,
    fixture: str,
    period: str,
    growth: float,
    big_three: List[Share],
    methodology_break: bool,
) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, fixture))

    report = report_of(results, period, PUBLIC)
    assert (report.market_size_bn, report.growth_pct, report.methodology_break) == (None, growth, methodology_break)
    assert shares(report) == big_three
    assert report.mentions == []


async def test_release_without_public_figures(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), article(SIZE_SENTENCE))

    assert [(report.period, report.segment) for report in reports(results)] == [
        ("2024Q4", MarketSegment.CLOUD_INFRASTRUCTURE)
    ]
    assert report_of(results, "2024Q4").twelve_month_bn is None


async def test_mentions_are_the_providers_without_share(crawl_page: CrawlPage) -> None:
    release = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_q2_2026.html"))
    trend = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_share_trend_2025.html"))

    assert [(mention.name, mention.rank) for mention in report_of(release, "2026Q2").mentions] == [
        ("CoreWeave", None),
        ("OpenAI", None),
        ("Oracle", None),
        ("Crusoe", None),
        ("Nebius", None),
        ("Anthropic", None),
        ("Nscale", None),
    ]
    mentions = {mention.name: mention.rank for mention in report_of(trend, "2025Q3").mentions}
    assert mentions["Alibaba"] == 4
    assert "Google" not in mentions


async def test_ranked_player_without_share_is_mentioned(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    body = f"{SIZE_SENTENCE} Amazon saw its worldwide market share drop to 31%, ahead of second-placed Microsoft."

    with caplog.at_level(logging.DEBUG):
        results = await crawl_page(SynergyResearchCrawler(), article(body))

    report = report_of(results, "2024Q4")
    assert shares(report) == [("amazon", 31.0, None, False, None)]
    assert [(mention.name, mention.rank) for mention in report.mentions] == [("Microsoft", 2)]


async def test_ranked_player_with_share_is_not_mentioned(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    body = f"{SIZE_SENTENCE} Amazon saw its worldwide market share drop to 31%, ahead of second-ranked Amazon."

    with caplog.at_level(logging.DEBUG):
        results = await crawl_page(SynergyResearchCrawler(), article(body))

    assert report_of(results, "2024Q4").mentions == []
    assert logged(caplog, "DEBUG", "Not mentioning Amazon, which has a market share")


async def test_approximate_band_share(crawl_page: CrawlPage) -> None:
    body = f"{SIZE_SENTENCE} Amazon market share stayed at around 34-32%. Google share stood at 11%."

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    assert shares(report_of(results, "2024Q4")) == [
        ("amazon", 33.0, (32.0, 34.0), True, None),
        ("google", 11.0, None, False, None),
    ]


@pytest.mark.parametrize(
    "sentence",
    [
        "Their Q4 worldwide market shares were 20%, 30% and 10% respectively.",
        "Their Q4 worldwide market shares were 25%, 8% and 1% respectively.",
        "Their Q4 worldwide market shares were 50%, 20% and 10% respectively.",
    ],
    ids=["not-descending", "too-small", "too-large"],
)
async def test_implausible_shares_are_dropped(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, sentence: str
) -> None:
    results = await crawl_page(SynergyResearchCrawler(), article(f"{SIZE_SENTENCE} {sentence}"))

    report = report_of(results, "2024Q4")
    assert report.shares == []
    assert report.market_size_bn == 90.6
    assert logged(caplog, "WARNING", "Dropping the implausible synergy shares")


async def test_implausible_shares_keep_the_big_three(crawl_page: CrawlPage) -> None:
    body = (
        f"{SIZE_SENTENCE} Their Q4 worldwide market shares were 20%, 30% and 10% respectively. In aggregate the three "
        "leaders accounted for 60% of the worldwide market."
    )

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    assert shares(report_of(results, "2024Q4")) == [("big-three", 60.0, None, False, None)]


async def test_europe_2025(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_europe_2025.html"))

    assert [(report.period, report.region, report.currency) for report in reports(results)] == [
        ("2024", MarketRegion.EUROPE, "EUR"),
        ("2025H1", MarketRegion.EUROPE, "EUR"),
    ]
    year, half = reports(results)
    assert (year.market_size_bn, year.twelve_month_bn) == (61.0, None)
    assert shares(year) == [
        ("big-three", 70.0, None, False, None),
        ("european-providers", 15.0, None, True, None),
        ("sap", 2.0, None, False, "european-providers"),
        ("deutsche-telekom", 2.0, None, False, "european-providers"),
    ]
    assert [mention.name for mention in year.mentions] == ["OVHcloud", "Telecom Italia", "Orange"]
    assert (half.market_size_bn, half.shares, half.mentions) == (36.0, [], [])
    others = year.others()
    assert others is not None
    assert others.share_pct == 15.0


async def test_europe_2022(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_europe_2022.html"))

    (report,) = reports(results)
    assert (report.period, report.market_size_bn, report.twelve_month_bn) == ("2022Q2", 10.4, 27.0)
    assert shares(report) == [
        ("big-three", 72.0, None, False, None),
        ("european-providers", 13.0, None, False, None),
        ("sap", 2.0, None, False, "european-providers"),
        ("deutsche-telekom", 2.0, None, False, "european-providers"),
    ]


async def test_europe_half_year_only(crawl_page: CrawlPage) -> None:
    content = fixture_text("synergy_europe_2025.html")
    content = content.replace("the European cloud market grew", "the cloud market in Europe grew")
    content = content.replace(
        "SAP and Deutsche Telekom are the leaders, each accounting", "Deutsche Telekom is the leader, accounting"
    )
    content = content.replace("European cloud providers&rsquo; market share", "their share")

    results = await crawl_page(SynergyResearchCrawler(), page(ARTICLE_URL, content))

    (report,) = reports(results)
    assert (report.period, report.market_size_bn) == ("2025H1", 36.0)
    assert shares(report) == [("big-three", 70.0, None, False, None), ("deutsche-telekom", 2.0, None, False, None)]
    assert [mention.name for mention in report.mentions] == ["OVHcloud", "Telecom Italia", "Orange"]


async def test_europe_without_figures(crawl_page: CrawlPage) -> None:
    body = "The European cloud market keeps growing, with no figure given this time."

    assert reports(await crawl_page(SynergyResearchCrawler(), article(body))) == []


@pytest.mark.parametrize(
    ("first_year", "variable", "fixture", "message"),
    [
        (None, None, "synergy_not_cloud.html", "it gives no cloud market figure"),
        (2021, None, "synergy_q2_2020.html", "2020Q2 report"),
        (None, "2021", "synergy_q2_2020.html", "2020Q2 report"),
    ],
    ids=["not-cloud", "before-first-year", "before-first-year-variable"],
)
async def test_articles_without_kept_figures(
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    first_year: Optional[int],
    variable: Optional[str],
    fixture: str,
    message: str,
) -> None:
    if variable is not None:
        monkeypatch.setenv(SynergyResearchCrawler.FIRST_YEAR_VARIABLE, variable)
    with caplog.at_level(logging.DEBUG):
        results = await crawl_page(SynergyResearchCrawler(first_year=first_year), fixture_page(ARTICLE_URL, fixture))

    assert results == []
    assert logged(caplog, "DEBUG", message)


@pytest.mark.parametrize(("variable", "expected"), [(None, 2013), ("2016", 2016), ("soon", 2013), ("", 2013)])
def test_first_year_is_configurable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, variable: Optional[str], expected: int
) -> None:
    monkeypatch.delenv(SynergyResearchCrawler.FIRST_YEAR_VARIABLE, raising=False)
    if variable is not None:
        monkeypatch.setenv(SynergyResearchCrawler.FIRST_YEAR_VARIABLE, variable)

    assert SynergyResearchCrawler().first_year == expected
    assert SynergyResearchCrawler(first_year=2019).first_year == 2019
    assert logged(caplog, "WARNING", "is not a year") is (variable == "soon")


@pytest.mark.parametrize(
    ("fixture", "period", "size", "twelve_month", "growth", "expected", "mentions", "methodology_break"),
    [
        (
            "synergy_q3_2014.html",
            "2014Q3",
            4.0,
            14.5,
            None,
            [
                ("amazon", 27.0, None, False, None),
                ("microsoft", 10.0, None, True, None),
                ("ibm", 7.0, None, False, None),
            ],
            ["Rackspace"],
            True,
        ),
        ("synergy_q1_2016.html", "2016Q1", 7.0, None, None, [("amazon", 31.0, None, False, None)], ["IBM"], True),
        (
            "synergy_q1_2018.html",
            "2018Q1",
            15.0,
            None,
            51.0,
            [("amazon", 33.0, None, True, None), ("ibm", 8.0, None, True, None)],
            ["Alibaba"],
            False,
        ),
        (
            "synergy_q2_2020.html",
            "2020Q2",
            30.5,
            111.0,
            None,
            [
                ("amazon", 33.0, None, True, None),
                ("microsoft", 18.0, None, False, None),
                ("google", 9.0, None, False, None),
            ],
            ["Alibaba", "Tencent", "Baidu"],
            False,
        ),
        (
            "synergy_q3_2019.html",
            "2019Q3",
            24.0,
            89.0,
            37.0,
            [],
            ["Alibaba", "Salesforce", "IBM", "Oracle", "Tencent", "Rackspace"],
            False,
        ),
    ],
)
async def test_older_worldwide_release(
    crawl_page: CrawlPage,
    fixture: str,
    period: str,
    size: float,
    twelve_month: Optional[float],
    growth: Optional[float],
    expected: List[Share],
    mentions: List[str],
    methodology_break: bool,
) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, fixture))

    report = report_of(results, period)
    assert (report.market_size_bn, report.twelve_month_bn, report.growth_pct) == (size, twelve_month, growth)
    assert shares(report) == expected
    assert [mention.name for mention in report.mentions] == mentions
    assert report.methodology_break is methodology_break


async def test_shares_given_on_public_iaas_paas_go_to_its_report(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), fixture_page(ARTICLE_URL, "synergy_q3_2019.html"))

    public = report_of(results, "2019Q3", PUBLIC)
    assert (public.market_size_bn, public.growth_pct, public.methodology_break) == (20.0, 40.0, False)
    assert shares(public) == [("amazon", 40.0, None, True, None)]
    assert report_of(results, "2019Q3").shares == []


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Behind them Oracle is ranked fourth with a 3% market share.", [("oracle", 3.0, None, False, None)]),
        (
            "They are followed by Alibaba (4%) and Huawei Cloud (2.5%).",
            [
                ("alibaba", 4.0, None, False, None),
                ("huawei", 2.5, None, False, None),
            ],
        ),
        ("Tencent market share has nudged up to around 2%.", [("tencent", 2.0, None, True, None)]),
        ("IBM's share was 5%.", [("ibm", 5.0, None, False, None)]),
    ],
    ids=["with-share", "in-brackets", "share-at", "share-was"],
)
async def test_other_players_shares(crawl_page: CrawlPage, sentence: str, expected: List[Share]) -> None:
    body = f"{SIZE_SENTENCE} Their Q4 worldwide market shares were 30%, 20% and 13% respectively. {sentence}"

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    report = report_of(results, "2024Q4")
    assert shares(report)[3:] == expected
    assert all(mention.name not in sentence for mention in report.mentions), "a player with a share is not mentioned"


async def test_other_players_are_not_part_of_the_big_three(crawl_page: CrawlPage) -> None:
    body = (
        f"{SIZE_SENTENCE} Their Q4 worldwide market shares were 30%, 20% and 13% respectively. In aggregate the three "
        "leaders accounted for 63% of the worldwide market. They are followed by Alibaba (4%)."
    )

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    report = report_of(results, "2024Q4")
    assert shares(report)[-1] == ("alibaba", 4.0, None, False, None)
    others = report.others()
    assert others is not None
    assert others.share_pct == 33.0


@pytest.mark.parametrize(
    "sentence",
    ["They are followed by Alibaba (40%).", "They are followed by Alibaba (30%), Oracle (12%) and IBM (10%)."],
    ids=["above-the-leader", "over-100"],
)
async def test_implausible_other_players_drop_the_shares(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, sentence: str
) -> None:
    body = f"{SIZE_SENTENCE} Their Q4 worldwide market shares were 30%, 20% and 13% respectively. {sentence}"

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    assert report_of(results, "2024Q4").shares == []
    assert logged(caplog, "WARNING", "Dropping the implausible synergy shares")


async def test_page_without_article_is_an_error(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(CatalogueFormatError, match="article body"):
        await crawl_page(SynergyResearchCrawler(), page(ARTICLE_URL, "<html><body><p>Moved.</p></body></html>"))

    assert logged(caplog, "ERROR", f"The synergy page {ARTICLE_URL} has no article body")


@pytest.mark.parametrize(
    ("dateline", "reason", "message"),
    [
        ("Published on February 6, 2025", "dateline", "has no dateline"),
        ("RENO, NV, Febuary 6, 2025", "is invalid", "has an invalid date 'Febuary 6, 2025'"),
    ],
)
async def test_release_without_valid_dateline_is_an_error(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, dateline: str, reason: str, message: str
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(SynergyResearchCrawler(), article(SIZE_SENTENCE, dateline=dateline))

    assert logged(caplog, "ERROR", message)


@pytest.mark.parametrize(
    ("published", "period"),
    [
        (date(2026, 2, 5), "2025Q4"),
        (date(2026, 4, 29), "2026Q1"),
        (date(2026, 7, 30), "2026Q2"),
        (date(2025, 11, 19), "2025Q3"),
        (date(2023, 1, 23), "2022Q4"),
    ],
)
def test_quarter_is_the_one_before_the_publication(published: date, period: str) -> None:
    assert SynergyResearchCrawler()._quarter(published) == period


@pytest.mark.parametrize(("alt", "warned"), [("CIS Q424", False), ("CIS Q125", True), ("CIS Share Trend", False)])
async def test_chart_quarter_is_cross_checked(
    crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture, alt: str, warned: bool
) -> None:
    results = await crawl_page(SynergyResearchCrawler(), article(SIZE_SENTENCE, alt=alt))

    assert report_of(results, "2024Q4").market_size_bn == 90.6
    assert logged(caplog, "WARNING", "charts 2025Q1 but was published after 2024Q4") is warned


async def test_invalid_report_is_skipped(crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture) -> None:
    body = SIZE_SENTENCE.replace("$90.6", "$0")

    results = await crawl_page(SynergyResearchCrawler(), article(body))

    assert results == []
    assert logged(caplog, "WARNING", f"Skipping the invalid synergy 2024Q4 report of {ARTICLE_URL}")


async def test_article_without_title_is_named_after_its_url(crawl_page: CrawlPage) -> None:
    results = await crawl_page(SynergyResearchCrawler(), article(SIZE_SENTENCE, title=""))

    assert report_of(results, "2024Q4").title == ARTICLE_URL


@pytest.mark.parametrize(
    "fixtures",
    [
        ("synergy_share_trend_2025.html", "synergy_q3_2025.html"),
        ("synergy_q3_2025.html", "synergy_share_trend_2025.html"),
    ],
    ids=["trend-first", "release-first"],
)
async def test_reports_of_the_same_quarter_are_merged(crawl_page: CrawlPage, fixtures: Tuple[str, str]) -> None:
    crawler = SynergyResearchCrawler()
    first, second = fixtures
    await crawl_page(crawler, fixture_page(f"{ARTICLE_URL}-1", first))

    results = await crawl_page(crawler, fixture_page(f"{ARTICLE_URL}-2", second))

    assert results
    report = crawler.reports[("2025Q3", MarketRegion.WORLDWIDE, MarketSegment.CLOUD_INFRASTRUCTURE)]
    assert shares(report)[0] == ("big-three", 63.0, None, False, None)
    assert (report.market_size_bn, report.growth_pct) == (106.9, 28.0)
    names = [mention.name for mention in report.mentions]
    assert {"Alibaba", "CoreWeave", "Oracle"} <= set(names)
    assert len(names) == len(set(names))
    public = crawler.reports[("2025Q3", MarketRegion.WORLDWIDE, MarketSegment.PUBLIC_IAAS_PAAS)]
    assert (public.growth_pct, shares(public)) == (30.0, [("big-three", 67.0, None, False, None)])


async def test_merge_takes_the_figures_missing_from_the_report_with_most_shares(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()
    sizes = f"{SIZE_SENTENCE} Their Q4 worldwide market shares were 30%, 21% and 12% respectively."
    growth = "Q4 spending was $91 billion worldwide, up $17 billion or 22% from the fourth quarter of 2023."
    await crawl_page(crawler, article(f"{sizes} Oracle and Alibaba keep growing."))

    results = await crawl_page(crawler, article(f"{SIZE_SENTENCE} {growth} Amazon and Alibaba lead CoreWeave."))

    (report,) = reports(results)
    assert len(report.shares) == 3
    assert report.growth_pct == 22.0
    assert [mention.name for mention in report.mentions] == ["Oracle", "Alibaba", "CoreWeave"]


async def test_same_article_twice_streams_nothing_new(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()
    await crawl_page(crawler, fixture_page(ARTICLE_URL, "synergy_q2_2026.html"))

    assert await crawl_page(crawler, fixture_page(ARTICLE_URL, "synergy_q2_2026.html")) == []


async def test_article_text_excludes_the_company_boilerplate(crawl_page: CrawlPage) -> None:
    sales = (
        '<div id="sales-info"><p>Contact sales. Their Q4 worldwide market shares were 30%, 21% and 12% respectively.'
        "</p></div>"
    )
    html = (
        f'<html><body><div class="article"><h2>Title</h2><p>RENO, NV, February 6, 2025 {SIZE_SENTENCE}</p>{sales}'
        "<script>var oracle = 'Oracle';</script></div></body></html>"
    )

    results = await crawl_page(SynergyResearchCrawler(), page(ARTICLE_URL, html))

    report = report_of(results, "2024Q4")
    assert (report.shares, report.mentions) == ([], [])


async def test_archive_requests_the_older_titles(crawl_page: CrawlPage) -> None:
    crawler = SynergyResearchCrawler()
    rows = (
        '[["original"], ["https://www.srgresearch.com/articles/aws-remains-dominant-despite-microsoft-and-google-growth"],'
        ' ["https://www.srgresearch.com/articles/ibm-microsoft-and-google-still-playing-catch-amazon-iaaspaas-market"],'
        ' ["https://www.srgresearch.com/articles/chasing-pack-gain-market-share-q1-amazon-maintains-clear-lead"],'
        ' ["https://www.srgresearch.com/articles/microsoft-charges-ahead-saas-market"]]'
    )

    results = await crawl_page(crawler, page(crawler.CDX_URL, rows))

    assert slugs(results) == [
        "aws-remains-dominant-despite-microsoft-and-google-growth",
        "ibm-microsoft-and-google-still-playing-catch-amazon-iaaspaas-market",
        "chasing-pack-gain-market-share-q1-amazon-maintains-clear-lead",
    ]
