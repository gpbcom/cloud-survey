from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Tuple, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import JsonValue
from scrapling.spiders import Request, Response

from crawler.cloud.base import BaseCloudCrawler
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import (
    CloudProvider,
    DeliveryMethod,
    MarketPlayer,
    MarketRegion,
    MarketSegment,
    PricingPolicy,
    SoftwareCategory,
    SoftwareType,
)
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct
from models.stats.market_report import MarketReport

# The GUI tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CRAWLED_AT = datetime(2026, 10, 16, 7, 24, tzinfo=UTC)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="Run the live tests, which crawl the real websites.")


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="Live test: run it with `pytest --live`.")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def stealth_session_cls(request: pytest.FixtureRequest) -> Iterator[MagicMock]:
    """Replace the stealth browser session so no test ever touches a real browser, except the live tests."""
    if request.node.get_closest_marker("live"):
        yield MagicMock()
        return
    with patch("crawler.cloud.base.AsyncStealthySession", autospec=True) as mock_cls:
        yield mock_cls


@pytest.fixture
def make_response() -> Callable[[str, str], Response]:
    """Build an offline scrapling response from a fixture file of `tests/fixtures/crawler`."""

    def build(url: str, fixture: str) -> Response:
        content = (FIXTURES_DIR / "crawler" / fixture).read_bytes()
        return Response(url=url, content=content, status=200, reason="OK", cookies={}, headers={}, request_headers={})

    return build


@pytest.fixture
def crawl_page() -> Callable[[BaseCloudCrawler, Response], Awaitable[List[Union[Dict[str, JsonValue], Request]]]]:
    """Collect everything a crawler yields for a page: the products and the follow-up requests."""

    async def crawl(crawler: BaseCloudCrawler, response: Response) -> List[Union[Dict[str, JsonValue], Request]]:
        return [result async for result in crawler.parse(response)]

    return crawl


@pytest.fixture
def pricing_payload() -> Dict[str, JsonValue]:
    """A valid raw pricing policy, as it would come out of a scraper."""
    return {
        "pricing_policy": PricingPolicy.BY_RESOURCE.value,
        "free_limit": 10.0,
        "amount": 0.25,
        "currency": "EUR",
    }


@pytest.fixture
def product_payload(pricing_payload: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
    """A valid raw cloud product, as it would come out of a scraper."""
    return {
        "name": "Object Storage",
        "description": "S3 compatible object storage.",
        "pricing_policy": [pricing_payload],
    }


@pytest.fixture
def plain_formatter_payload() -> Dict[str, JsonValue]:
    """The `plain` formatter of `logging_config_payload`."""
    return {"format": "%(levelname)s - %(message)s"}


@pytest.fixture
def console_handler_payload() -> Dict[str, JsonValue]:
    """The `console` handler of `logging_config_payload`."""
    return {"class": "logging.StreamHandler", "formatter": "plain", "stream": "ext://sys.stdout"}


@pytest.fixture
def file_handler_payload(tmp_path: Path) -> Dict[str, JsonValue]:
    """The `file` handler of `logging_config_payload`."""
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "plain",
        "filename": str(tmp_path / "app.log"),
        "maxBytes": 1024,
        "backupCount": 2,
    }


@pytest.fixture
def app_logger_payload() -> Dict[str, JsonValue]:
    """The `app` logger of `logging_config_payload`."""
    return {"level": "info", "handlers": ["file"], "propagate": False}


@pytest.fixture
def root_logger_payload() -> Dict[str, JsonValue]:
    """The root logger of `logging_config_payload`."""
    return {"level": "DEBUG", "handlers": ["console"]}


@pytest.fixture
def logging_config_payload(
    plain_formatter_payload: Dict[str, JsonValue],
    console_handler_payload: Dict[str, JsonValue],
    file_handler_payload: Dict[str, JsonValue],
    app_logger_payload: Dict[str, JsonValue],
    root_logger_payload: Dict[str, JsonValue],
) -> Dict[str, JsonValue]:
    """A minimal valid logging configuration, written with `dictConfig` key names.

    It references the section fixtures: mutating a section fixture mutates this configuration.
    """
    return {
        "version": 1,
        "formatters": {"plain": plain_formatter_payload},
        "handlers": {"console": console_handler_payload, "file": file_handler_payload},
        "loggers": {"app": app_logger_payload},
        "root": root_logger_payload,
    }


@pytest.fixture
def isolated_logging() -> Iterator[None]:
    """Snapshot the global logging state and restore it once the test reconfigured logging."""
    root = logging.getLogger()
    root_state = (root.level, root.handlers[:])
    loggers = {
        name: (logger.level, logger.handlers[:], logger.propagate, logger.disabled)
        for name, logger in logging.Logger.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }

    yield

    for handler in root.handlers:
        if handler not in root_state[1]:
            handler.close()
    root.setLevel(root_state[0])
    root.handlers[:] = root_state[1]
    for name, (level, handlers, propagate, disabled) in loggers.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.disabled = disabled


@pytest.fixture
def make_marketplace() -> Callable[[CloudProvider, List[MarketplaceSoftware]], CloudMarketplace]:
    """Build a marketplace of the given software."""

    def build(provider: CloudProvider, software: List[MarketplaceSoftware]) -> CloudMarketplace:
        return CloudMarketplace(provider=provider, crawled_at=CRAWLED_AT, software=software)

    return build


def build_software(
    name: str,
    types: List[SoftwareType],
    categories: List[SoftwareCategory],
    delivery: DeliveryMethod = DeliveryMethod.SAAS,
    publisher: str = "ACME",
) -> MarketplaceSoftware:
    """Build a marketplace software."""
    return MarketplaceSoftware(
        name=name,
        description=f"{name} description",
        publisher=publisher,
        url=f"https://marketplace.example.com/{name.casefold().replace(' ', '-')}",
        delivery=delivery,
        marketplace_categories=[kind.value for kind in types],
        categories=categories,
        types=types,
    )


@pytest.fixture
def make_software() -> Callable[..., MarketplaceSoftware]:
    """Build a marketplace software: name, types, categories, then optionally the delivery and publisher."""
    return build_software


def build_report(
    label: str,
    top_shares: List[Tuple[MarketPlayer, float]],
    region: MarketRegion = MarketRegion.WORLDWIDE,
    segment: MarketSegment = MarketSegment.CLOUD_INFRASTRUCTURE,
    **fields: JsonValue,
) -> MarketReport:
    """Build a market report with top-level shares, the other fields given as JSON values."""
    values: Dict[str, JsonValue] = {
        "period": label,
        "region": region.value,
        "segment": segment.value,
        "shares": [{"player": player.value, "share_pct": pct} for player, pct in top_shares],
        "source_url": f"https://www.srgresearch.com/articles/{label.casefold()}",
        "title": f"Cloud market {label}",
        "published": "2026-07-30",
    }
    values.update(fields)
    return MarketReport.model_validate(values)


@pytest.fixture
def make_report() -> Callable[..., MarketReport]:
    """Build a market report: period, (player, share) pairs, then optionally the region, segment and other fields."""
    return build_report


@pytest.fixture
def make_catalogue() -> Callable[[CloudProvider, List[str]], CloudCatalogue]:
    """Build a catalogue of products named after the given names."""

    def build(provider: CloudProvider, names: List[str]) -> CloudCatalogue:
        products = [CloudProduct(name=name, description=f"{name} description") for name in names]
        return CloudCatalogue(provider=provider, crawled_at=CRAWLED_AT, products=products)

    return build
