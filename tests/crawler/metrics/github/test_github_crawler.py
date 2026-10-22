from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Union

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from crawler.metrics.github.crawler import GithubCrawler
from models.drivers.collectors.collector_catalog import CollectorCatalog

CrawlPage = Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]
MetricPage = Callable[[str, str, Dict[str, JsonValue]], Response]
AWS = "https://api.github.com/repos/hashicorp/terraform-provider-aws"


async def test_one_request_per_repository_with_the_token(
    metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(metric_catalog.github_token_env, "secret-token")

    requests = [request async for request in GithubCrawler(metric_catalog).start_requests()]

    assert len(requests) == sum(len(entry.repositories) for entry in metric_catalog.entries)
    assert requests[0].url == AWS
    assert requests[0].meta == {
        "metric_repository": "hashicorp/terraform-provider-aws",
        "metric_provider": "amazon-web-services",
    }
    assert requests[0]._session_kwargs["headers"]["Authorization"] == "Bearer secret-token"


async def test_no_token_no_authorization(metric_catalog: CollectorCatalog, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(metric_catalog.github_token_env, raising=False)

    requests = [request async for request in GithubCrawler(metric_catalog).start_requests()]

    assert "Authorization" not in requests[0]._session_kwargs["headers"]


async def test_the_stars_are_streamed(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    meta: Dict[str, JsonValue] = {
        "metric_repository": "hashicorp/terraform-provider-aws",
        "metric_provider": "amazon-web-services",
    }

    (fact,) = await crawl_page(GithubCrawler(metric_catalog), metric_page(AWS, "github-repository.json", meta))

    assert isinstance(fact, dict)
    assert (fact["provider"], fact["repository"], fact["stars"]) == (
        "amazon-web-services",
        "hashicorp/terraform-provider-aws",
        11119,
    )


async def test_a_document_without_stars_gives_nothing(
    metric_catalog: CollectorCatalog, metric_page: MetricPage, crawl_page: CrawlPage
) -> None:
    meta: Dict[str, JsonValue] = {"metric_repository": "a/b", "metric_provider": "civo"}

    assert await crawl_page(GithubCrawler(metric_catalog), metric_page(AWS, "peeringdb-net.json", meta)) == []
