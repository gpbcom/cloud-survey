from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.ovh.marketplace import OVHcloudMarketplaceCrawler
from crawler.exception import CatalogueFormatError, EmptyCatalogueError

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
FIXTURES = Path(__file__).parents[3] / "fixtures" / "marketplace"
URL = "https://marketplace.ovhcloud.com/en/products"
TYPES: JsonValue = {
    "error": None,
    "response": [
        {"id": "a", "name": "Cybersécurité", "localizedName": "Cybersecurity", "fieldSetID": 3},
        {"id": "b", "name": "IA et data", "localizedName": "", "fieldSetID": 7},
        {"id": "c", "name": "No field set"},
    ],
}


@pytest.fixture(scope="module")
def crawler() -> OVHcloudMarketplaceCrawler:
    return OVHcloudMarketplaceCrawler(classifier=SoftwareClassifier())


@pytest.fixture
def fresh(crawler: OVHcloudMarketplaceCrawler) -> OVHcloudMarketplaceCrawler:
    crawler.software_categories.clear()
    return crawler


def encode(data: JsonValue) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")


def fixture_page() -> Response:
    content = (FIXTURES / "ovh_products.html").read_bytes()
    return Response(url=URL, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})


def html_page(products: Optional[str], types: Optional[str] = None) -> Response:
    scripts = "".join(
        f'<script type="application/json" id="{script}">{raw}</script>'
        for script, raw in (("preloadedAssetTypesData", types), ("preloadedProductsData", products))
        if raw is not None
    )
    return Response(
        url=URL,
        content=f"<html><body>{scripts}</body></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )


def data_page(assets: JsonValue, types: JsonValue = TYPES) -> Response:
    return html_page(encode({"error": None, "response": {"assets": assets}}), encode(types))


def product(name: str, **fields: JsonValue) -> JsonValue:
    data: Dict[str, JsonValue] = {
        "name": name,
        "slugName": name.casefold().replace(" ", "-"),
        "assetEncryptKey": "key1",
        "assetTypeID": 3,
        "organizationName": "Acme",
        "description": f"<p>{name} &amp; more</p>",
        "seoElements": {"description": f"{name} description"},
        "customFields": {},
        "categories": [
            {"categoryName": "Subcategories", "filters": ["data protection"]},
            {"categoryName": "Service type", "filters": ["saas"]},
        ],
    }
    data.update(fields)
    return data


def items(results: List[Union[Dict[str, JsonValue], Request]]) -> List[Dict[str, JsonValue]]:
    return [result for result in results if isinstance(result, dict)]


def names(results: List[Union[Dict[str, JsonValue], Request]]) -> List[JsonValue]:
    return [item["name"] for item in items(results)]


def test_configuration(crawler: OVHcloudMarketplaceCrawler) -> None:
    assert crawler.name == "ovhcloud-marketplace"
    assert OVHcloudMarketplaceCrawler.catalogue_url == URL
    assert OVHcloudMarketplaceCrawler.complement_urls == ()
    assert crawler.allowed_domains == {"marketplace.ovhcloud.com"}


async def test_extracts_the_software(fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(fresh, fixture_page())

    assert names(results) == [
        "Serveur Nextcloud",
        "Email Pro - SOGomail",
        "Plakar Control Plane : Plateforme de sauvegarde et de résilience des données",
        "PostgreSQL by Clever Cloud",
        "Serveur Dolibarr",
        "GuardWeaver",
        "Nucleon Detection & Response (EDR) : Protégez votre entreprise contre toutes les cybermenaces",
    ]
    assert items(results)[1]["marketplace_category_paths"] == [{"path": ["Collaboration and productivity"], "id": "4"}]
    assert items(results)[6]["marketplace_category_paths"] == [
        {"path": ["Cybersecurity", label], "id": label}
        for label in (
            "data protection",
            "endpoint & application security",
            "threat detection, response and intelligence",
        )
    ]
    assert items(results)[0] == {
        "name": "Serveur Nextcloud",
        "description": (
            "Découvrez la solution Serveur Nextcloud de notre partenaire Mise Sur Orbite, idéale pour stocker, "
            "partager et sécuriser vos données en toute confidentialité. Installation facile, performances fiables "
            "et contrôle total de vos fichiers. Optez pour une solution cloud adaptée aux particuliers et aux "
            "entreprises."
        ),
        "publisher": "Mise Sur Orbite",
        "url": "https://marketplace.ovhcloud.com/en/product/serveur-nextcloud/d562juh6omqdt",
        "delivery": "saas",
        "marketplace_categories": ["Collaboration and productivity", "document management"],
        "marketplace_category_paths": [
            {"path": ["Collaboration and productivity", "document management"], "id": "document management"}
        ],
        "categories": ["end-user-software"],
        "added_at": "2025-09-04T11:11:12Z",
        "updated_at": "2026-09-04T08:41:23Z",
    }


@pytest.mark.parametrize(
    "excluded",
    [
        "Forfait configuration DNS",
        "Infogérance 24/7 d'un serveur Linux Debian ou Ubuntu",
        "Transfert d'un site internet",
    ],
)
async def test_services_are_excluded(fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage, excluded: str) -> None:
    assert excluded not in names(await crawl_page(fresh, fixture_page()))


@pytest.mark.parametrize(
    ("name", "delivery", "audiences"),
    [
        ("Email Pro - SOGomail", "other", ["developer-tool", "end-user-software"]),
        (
            "Plakar Control Plane : Plateforme de sauvegarde et de résilience des données",
            "download",
            ["developer-tool"],
        ),
        ("PostgreSQL by Clever Cloud", "saas", ["developer-tool", "end-user-software"]),
        ("Serveur Dolibarr", "saas", ["end-user-software"]),
        ("GuardWeaver", "saas", ["developer-tool", "end-user-software"]),
    ],
)
async def test_delivery_and_audiences(
    fresh: OVHcloudMarketplaceCrawler,
    crawl_page: CrawlPage,
    name: str,
    delivery: str,
    audiences: List[str],
) -> None:
    software = next(item for item in items(await crawl_page(fresh, fixture_page())) if item["name"] == name)

    assert (software["delivery"], software["categories"]) == (delivery, audiences)


async def test_missing_fields_fall_back(fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        data_page(
            [
                product("No seo", seoElements={"description": " "}, assetTypeID=7, createdOn="soon", updatedOn=None),
                product("No slug", slugName=None, assetTypeID="3", categories="none", seoElements=None),
                product("No description", description=None, seoElements=None),
                "not a product",
            ]
        ),
    )

    assert [
        (item["name"], item["description"], item["url"], item["marketplace_categories"]) for item in items(results)
    ] == [
        (
            "No seo",
            "No seo & more",
            "https://marketplace.ovhcloud.com/en/product/no-seo/key1",
            ["IA et data", "data protection"],
        ),
        ("No slug", "No slug & more", None, []),
    ]
    assert items(results)[1]["delivery"] == "other"
    assert items(results)[0]["marketplace_category_paths"] == [
        {"path": ["IA et data", "data protection"], "id": "data protection"}
    ]
    assert "marketplace_category_paths" not in items(results)[1]
    assert not {"added_at", "updated_at"} & items(results)[0].keys()


async def test_support_subcategories_are_excluded(fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage) -> None:
    results = await crawl_page(
        fresh,
        data_page(
            [
                product("Kept"),
                product("Support", categories=[{"categoryName": "Subcategories", "filters": ["Technical support", 1]}]),
                product("Custom", customFields={"Subcategory": "Assistance technique ponctuelle / Divers"}),
                product(
                    "Managed", categories=[{"categoryName": "Service type", "filters": ["SaaS", "Managed services"]}]
                ),
            ]
        ),
    )

    assert names(results) == ["Kept"]


async def test_only_services_is_an_empty_page(
    fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(EmptyCatalogueError):
        await crawl_page(
            fresh, data_page([product("Support", customFields={"Subcategory": "Assistance technique ponctuelle"})])
        )

    assert any(record.levelname == "ERROR" and "holds no software" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        (html_page(None, encode(TYPES)), "the `preloadedProductsData` script is missing"),
        (html_page(encode({"response": {"assets": []}})), "the `preloadedAssetTypesData` script is missing"),
        (html_page("not base64!", encode(TYPES)), "the `preloadedProductsData` script is not base64 JSON"),
        (html_page(encode([1, 2]), encode(TYPES)), "the `preloadedProductsData` script is not a JSON object"),
        (html_page(encode({"response": {"assets": None}}), encode(TYPES)), "the page data has no products list"),
    ],
)
async def test_malformed_page_is_an_error(
    fresh: OVHcloudMarketplaceCrawler,
    crawl_page: CrawlPage,
    caplog: pytest.LogCaptureFixture,
    page: Response,
    reason: str,
) -> None:
    with pytest.raises(CatalogueFormatError, match=reason):
        await crawl_page(fresh, page)

    assert [record.levelname for record in caplog.records].count("ERROR") == 1


async def test_types_without_list_give_no_top_category(
    fresh: OVHcloudMarketplaceCrawler, crawl_page: CrawlPage
) -> None:
    results = await crawl_page(fresh, data_page([product("Kept")], {"response": None}))

    assert items(results)[0]["marketplace_categories"] == ["data protection"]
    assert items(results)[0]["marketplace_category_paths"] == [{"path": ["data protection"], "id": "data protection"}]
