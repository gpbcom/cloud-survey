from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.oracle.marketplace import OracleMarketplaceCrawler
from crawler.exception import CatalogueFormatError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
API_URL = "https://public.marketplace.us-ashburn-1.oci.oraclecloud.com/20180828"
META_ID = "ocid1.mktpublisting.oc1.iad.amaaaaaavnsf4tqan47ctumwtmukuidegxt22vmcq5pvl4zi5dkuif7puloa"
TPAY_ID = "ocid1.mktpublisting.oc1.iad.amaaaaaapemeveaaabrlull3v4kijruiyiszplddp4b7hkkzkkg777h6czgq"
AGENT_ID = "ocid1.mktpublisting.oc1.iad.amaaaaaaxvowp3ianwseckum2w2jxia5nbikzskbqirzacp6yaada35uwaxa"


@pytest.fixture(scope="module")
def classifier() -> SoftwareClassifier:
    return SoftwareClassifier()


@pytest.fixture
def crawler(classifier: SoftwareClassifier) -> OracleMarketplaceCrawler:
    return OracleMarketplaceCrawler(classifier=classifier)


@pytest.fixture(autouse=True)
def no_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OracleMarketplaceCrawler, "page_limit", None)


def page(url: str, content: Union[str, bytes], meta: Dict[str, JsonValue], status: int = 200) -> Response:
    return Response(
        url=url, content=content, status=status, reason="OK", cookies={}, headers={}, request_headers={}, meta=meta
    )


def listings_page(number: int, content: Optional[JsonValue] = None) -> Response:
    body = (FIXTURES / f"oracle_listings_page{number}.json").read_bytes() if content is None else json.dumps(content)
    return page(f"{API_URL}/listings?limit=120&page={number}", body, {"page": number})


def detail(identifier: str, content: Union[str, bytes], status: int = 200) -> Response:
    return page(f"{API_URL}/listings/{identifier}", content, {"detail": identifier, "may_be_empty": True}, status)


def detail_fixture(identifier: str, fixture: str) -> Response:
    return detail(identifier, (FIXTURES / f"oracle_listing_{fixture}.json").read_bytes())


def requests(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Request]:
    return [result for result in results if isinstance(result, Request)]


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def listing(name: str, **fields: JsonValue) -> Dict[str, JsonValue]:
    entry: Dict[str, JsonValue] = {"id": f"id-{name}", "name": name, "listingType": "OCI_APPLICATION", "products": []}
    return entry | fields


def test_configuration(crawler: OracleMarketplaceCrawler) -> None:
    assert crawler.name == "oracle-marketplace"
    assert OracleMarketplaceCrawler.catalogue_url == f"{API_URL}/listings?limit=120&page=1"
    assert OracleMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"public.marketplace.us-ashburn-1.oci.oraclecloud.com"}


async def test_starts_with_the_first_listings_page(crawler: OracleMarketplaceCrawler) -> None:
    started = [request async for request in crawler.start_requests()]

    assert [(request.url, request.sid, request.priority, request.meta) for request in started] == [
        (f"{API_URL}/listings?limit=120&page=1", "oracle-marketplace-http", 10, {"page": 1})
    ]


async def test_requests_the_details_of_the_software_and_the_next_pages(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    found = requests(await crawl_page(crawler, listings_page(1)))

    details = [request for request in found if "detail" in request.meta]
    assert [request.url.removeprefix(f"{API_URL}/listings/") for request in details] == [
        META_ID,
        TPAY_ID,
        AGENT_ID,
        "ocid1.mktpublisting.oc1.iad.amaaaaaaa3tmauiae726dx4gqsjn24cqxz2oxgunvmp7nmybl36tr2dtpdia",
        "ocid1.mktpublisting.oc1.iad.amaaaaaac2u4zjyadqutnu6o4pr54h5c6ctigrnrtenr63qwk4pr7gqykpgq",
    ]
    assert all(request.meta["may_be_empty"] is True and request.priority == 0 for request in details)
    assert all(
        request._session_kwargs["headers"] == {"Referer": "https://marketplace.oracle.com/"} for request in found
    )
    pages = [request for request in found if "page" in request.meta]
    assert [request.url for request in pages] == [f"{API_URL}/listings?limit=120&page={n}" for n in range(2, 32)]
    assert all(request.priority == 10 and request.sid == "oracle-marketplace-http" for request in pages)
    assert (
        "Skipping the listing 'EEMC \u2013 Oracle Hospitality & Food and Beverage Solutions' (listing type"
        in caplog.text
    )


async def test_does_not_request_more_pages_from_a_next_page(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    found = requests(await crawl_page(crawler, listings_page(2)))

    assert [request.meta for request in found if "page" in request.meta] == []
    assert len(found) == 3
    assert "Skipping the listing 'Check Point Secure AI Advisory' (service)." in caplog.text


async def test_honours_the_page_limit(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(OracleMarketplaceCrawler, "page_limit", 2)

    found = requests(await crawl_page(crawler, listings_page(1)))

    assert [request.meta["page"] for request in found if "page" in request.meta] == [2]


@pytest.mark.parametrize(
    ("pagination", "pages"),
    [
        ({"totalItems": 241}, 3),
        ({"totalPages": 0, "totalItems": 0}, 1),
        ({"totalPages": "2"}, 1),
        (None, 1),
    ],
)
async def test_counts_the_pages(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, pagination: JsonValue, pages: int
) -> None:
    found = requests(await crawl_page(crawler, listings_page(1, {"items": [], "pagination": pagination})))

    assert [request.meta["page"] for request in found] == list(range(2, pages + 1))


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        (listing("Help", listingType="SERVICE"), "listing type 'SERVICE'"),
        (listing("Group", products=[{"productGroup": "SERVICES"}]), "service product group"),
        (listing("Partner", products=[{"productName": "Resellers"}, "x"]), "partner product"),
        (listing("Acme Managed Services"), "service"),
        (listing("Acme Implementation Service"), "service"),
    ],
)
async def test_skips_the_services(
    crawler: OracleMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    entry: Dict[str, JsonValue],
    reason: str,
) -> None:
    caplog.set_level(logging.DEBUG)

    found = requests(await crawl_page(crawler, listings_page(3, {"items": [entry, listing("Kept")]})))

    assert [request.meta["detail"] for request in found] == ["id-Kept"]
    assert f"Skipping the listing {entry['name']!r} ({reason})." in caplog.text


async def test_skips_the_listings_without_identifier(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    found = requests(await crawl_page(crawler, listings_page(3, {"items": [listing("Anonymous", id=None), "x"]})))

    assert found == []
    assert "Skipping the listing 'Anonymous', it has no identifier." in caplog.text


@pytest.mark.parametrize(
    ("content", "message", "logged"),
    [
        ("<html>Down</html>", "the page is not JSON", "is not JSON"),
        ('{"items": null}', "the `items` list is missing", "has no `items` list"),
        ("[1, 2]", "the `items` list is missing", "has no `items` list"),
    ],
)
async def test_raises_on_a_malformed_listings_page(
    crawler: OracleMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    content: str,
    message: str,
    logged: str,
) -> None:
    response = page(f"{API_URL}/listings?limit=120&page=1", content, {"page": 1})

    with pytest.raises(CatalogueFormatError, match=message):
        await crawl_page(crawler, response)

    assert any(record.levelno == logging.ERROR and logged in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("identifier", "fixture", "expected"),
    [
        (
            META_ID,
            "meta",
            {
                "name": "AI Solutions by Meta",
                "description": "Muse Models on Meta Model API and Muse Code",
                "publisher": "Meta",
                "url": f"https://marketplace.oracle.com/listings/ai-solutions-by-meta/{META_ID}",
                "delivery": "virtual-machine",
                "marketplace_categories": ["Oracle Cloud Infrastructure", "Artificial Intelligence"],
                "marketplace_category_paths": [{"path": ["Artificial Intelligence"], "id": "ARTIFICIAL_INTELLIGENCE"}],
                "added_at": "2026-10-15T23:42:44.154000Z",
                "updated_at": "2026-10-16T00:00:47.363000Z",
            },
        ),
        (
            TPAY_ID,
            "tpay",
            {
                "name": "T-PAY",
                "publisher": "安徽悦航信息技术有限公司",
                "url": f"https://marketplace.oracle.com/listings/t-pay/{TPAY_ID}",
                "delivery": "saas",
                "marketplace_categories": [
                    "Restaurants Cloud",
                    "Order Status / Digital Receipts",
                    "Catering",
                    "Digital Signage / Order Confirmation System",
                ],
                "marketplace_category_paths": [
                    {"path": ["Order Status / Digital Receipts"], "id": "ORDER_STATUS_/_DIGITAL_RECEIPTS@FOODBEV"},
                    {"path": ["Catering"], "id": "CATERING@FOODBEV"},
                    {"path": ["Digital Signage / Order Confirmation System"], "id": "DIGITAL_SIGNAGE@FOODBEV"},
                ],
            },
        ),
        (
            AGENT_ID,
            "agent",
            {
                "name": "Transfer Orders to Purchase Orders Converter",
                "description": "Convert open Transfer Order lines into consolidated Purchase Orders automatically",
                "publisher": "Infosys Limited",
                "delivery": "api",
                "added_at": "2026-10-14T16:33:00.152000Z",
                "updated_at": "2026-10-15T19:27:14.393000Z",
            },
        ),
    ],
)
async def test_extracts_the_software_of_a_detail(
    crawler: OracleMarketplaceCrawler,
    crawl_page: CrawlPage,
    identifier: str,
    fixture: str,
    expected: Dict[str, JsonValue],
) -> None:
    found = items(await crawl_page(crawler, detail_fixture(identifier, fixture)))

    assert len(found) == 1
    assert {key: found[0][key] for key in expected} == expected
    if identifier == AGENT_ID:
        assert "marketplace_category_paths" not in found[0]


@pytest.mark.parametrize(
    ("fixture", "identifier", "audiences"),
    [("meta", META_ID, ["developer-tool", "end-user-software"]), ("agent", AGENT_ID, ["end-user-software"])],
)
async def test_classifies_the_software(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, fixture: str, identifier: str, audiences: List[str]
) -> None:
    found = items(await crawl_page(crawler, detail_fixture(identifier, fixture)))

    assert found[0]["categories"] == audiences


async def test_reads_a_minimal_detail(crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    content = {
        "name": "+++",
        "tagline": "A tool.",
        "listingType": "OTHER",
        "products": [{"categories": "none"}],
        "timeCreated": "yesterday",
    }

    found = items(await crawl_page(crawler, detail("ocid1.x", json.dumps(content))))

    assert {key: found[0][key] for key in ("url", "publisher", "delivery", "marketplace_categories")} == {
        "url": "https://marketplace.oracle.com/listings/listing/ocid1.x",
        "publisher": None,
        "delivery": "other",
        "marketplace_categories": [],
    }
    assert "added_at" not in found[0]
    assert "updated_at" not in found[0]
    assert "marketplace_category_paths" not in found[0]


async def test_skips_a_missing_detail(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    found = await crawl_page(crawler, detail("ocid1.gone", '{"code": "NotAuthorizedOrNotFound"}', status=404))

    assert found == []
    assert "Skipping the oracle-marketplace listing ocid1.gone, its detail is missing (HTTP 404)." in caplog.text


async def test_skips_an_invalid_detail(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    found = await crawl_page(crawler, detail("ocid1.bad", "[]"))

    assert found == []
    assert "Skipping the invalid marketplace entry ''" in caplog.text


async def test_raises_on_a_detail_which_is_not_json(
    crawler: OracleMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(CatalogueFormatError, match="the page is not JSON"):
        await crawl_page(crawler, detail("ocid1.html", "<html></html>"))

    assert any(record.levelno == logging.ERROR and "is not JSON" in record.message for record in caplog.records)
