from __future__ import annotations

import logging
from typing import Type
from unittest.mock import MagicMock, patch

import pytest

from crawler.cloud.alibaba.crawler import AlibabaCloudCrawler
from crawler.cloud.arsys.crawler import ArsysCrawler
from crawler.cloud.aruba.crawler import ArubaCloudCrawler
from crawler.cloud.aws.crawler import AWSCrawler
from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.civo.crawler import CivoCrawler
from crawler.cloud.combell.crawler import CombellCrawler
from crawler.cloud.ctyun.crawler import ChinaTelecomCloudCrawler
from crawler.cloud.deep.crawler import DEEPCrawler
from crawler.cloud.ecloud.crawler import ChinaMobileCloudCrawler
from crawler.cloud.exoscale.crawler import ExoscaleCrawler
from crawler.cloud.gcore.crawler import GcoreCrawler
from crawler.cloud.gcp.crawler import GoogleCloudPlatformCrawler
from crawler.cloud.gigas.crawler import GigasCrawler
from crawler.cloud.huawei.crawler import HuaweiCloudCrawler
from crawler.cloud.ibm.crawler import IBMCloudCrawler
from crawler.cloud.infomaniak.crawler import InfomaniakCrawler
from crawler.cloud.krystal.crawler import KrystalCrawler
from crawler.cloud.oracle.crawler import OracleCloudCrawler
from crawler.cloud.ovh.crawler import OVHcloudCrawler
from crawler.cloud.proximus.crawler import ProximusNXTCrawler
from crawler.cloud.scaleway.crawler import ScalewayCrawler
from crawler.cloud.seeweb.crawler import SeewebCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler
from crawler.cloud.tencent.crawler import TencentCloudCrawler
from crawler.cloud.volcengine.crawler import VolcanoEngineCrawler
from crawler.exception import NoMarketplaceError, UnknownCrawlerTargetError
from crawler.factory import CrawlerFactory
from crawler.marketplace.base import BaseMarketplaceCrawler
from crawler.stats.base import BaseStatsCrawler
from crawler.stats.synergy import SynergyResearchCrawler
from models.cloud.enums import CloudProvider

EXPECTED_CRAWLERS = [
    (CloudProvider.AWS, AWSCrawler),
    (CloudProvider.AZURE, AzureCrawler),
    (CloudProvider.GCP, GoogleCloudPlatformCrawler),
    (CloudProvider.IBM, IBMCloudCrawler),
    (CloudProvider.ORACLE, OracleCloudCrawler),
    (CloudProvider.OVH, OVHcloudCrawler),
    (CloudProvider.SCALEWAY, ScalewayCrawler),
    (CloudProvider.COMBELL, CombellCrawler),
    (CloudProvider.PROXIMUS, ProximusNXTCrawler),
    (CloudProvider.STACKIT, STACKITCrawler),
    (CloudProvider.TCLOUD, TCloudPublicCrawler),
    (CloudProvider.ARUBA, ArubaCloudCrawler),
    (CloudProvider.SEEWEB, SeewebCrawler),
    (CloudProvider.GCORE, GcoreCrawler),
    (CloudProvider.DEEP, DEEPCrawler),
    (CloudProvider.ARSYS, ArsysCrawler),
    (CloudProvider.GIGAS, GigasCrawler),
    (CloudProvider.EXOSCALE, ExoscaleCrawler),
    (CloudProvider.INFOMANIAK, InfomaniakCrawler),
    (CloudProvider.CIVO, CivoCrawler),
    (CloudProvider.KRYSTAL, KrystalCrawler),
    (CloudProvider.ALIBABA, AlibabaCloudCrawler),
    (CloudProvider.HUAWEI, HuaweiCloudCrawler),
    (CloudProvider.TENCENT, TencentCloudCrawler),
    (CloudProvider.BAIDU, BaiduAICloudCrawler),
    (CloudProvider.VOLCENGINE, VolcanoEngineCrawler),
    (CloudProvider.CTYUN, ChinaTelecomCloudCrawler),
    (CloudProvider.ECLOUD, ChinaMobileCloudCrawler),
]


def test_every_provider_has_a_crawler() -> None:
    assert set(CrawlerFactory.CRAWLER_MAP) == set(CloudProvider)


def test_default_logger() -> None:
    assert CrawlerFactory().logger.name == "crawler.factory"


def test_custom_logger() -> None:
    logger = logging.getLogger("custom")

    assert CrawlerFactory(logger=logger).logger is logger


@pytest.mark.parametrize(("provider", "crawler_cls"), EXPECTED_CRAWLERS)
def test_get_with_enum(provider: CloudProvider, crawler_cls: Type[BaseCloudCrawler]) -> None:
    crawler = CrawlerFactory().get(provider)

    assert type(crawler) is crawler_cls


@pytest.mark.parametrize(("provider", "crawler_cls"), EXPECTED_CRAWLERS)
def test_get_with_string(provider: CloudProvider, crawler_cls: Type[BaseCloudCrawler]) -> None:
    crawler = CrawlerFactory().get(provider.value)

    assert type(crawler) is crawler_cls


def test_get_returns_a_new_instance_each_time() -> None:
    factory = CrawlerFactory()

    assert factory.get(CloudProvider.AWS) is not factory.get(CloudProvider.AWS)


def test_get_logs_instantiation() -> None:
    logger = MagicMock(spec=logging.Logger)

    CrawlerFactory(logger=logger).get(CloudProvider.SCALEWAY)

    logger.info.assert_called_once_with("A crawler for this target: %s will be instantiated.", CloudProvider.SCALEWAY)
    logger.error.assert_not_called()


@pytest.mark.parametrize("target", ["", "aws", "AWS", "Scaleway", "unknown-cloud"])
def test_get_unknown_target_raises(target: str) -> None:
    logger = MagicMock(spec=logging.Logger)

    with pytest.raises(ValueError, match="Failed to identify suitable crawler") as exc_info:
        CrawlerFactory(logger=logger).get(target)

    assert isinstance(exc_info.value.__cause__, ValueError)
    logger.error.assert_called_once_with("There is no crawler available for this target: %s", target)
    logger.info.assert_not_called()


def test_get_unknown_target_does_not_instantiate_any_crawler(stealth_session_cls: MagicMock) -> None:
    with pytest.raises(ValueError, match="Failed to identify suitable crawler"):
        CrawlerFactory().get("unknown-cloud")

    stealth_session_cls.assert_not_called()


class FakeMarketplaceCrawler(BaseMarketplaceCrawler):
    """Marketplace crawler registered for the tests."""

    name = "fake-marketplace"


def test_marketplace_providers_follow_the_map() -> None:
    with patch.dict(CrawlerFactory.MARKETPLACE_MAP, {CloudProvider.CIVO: FakeMarketplaceCrawler}, clear=True):
        assert CrawlerFactory().marketplace_providers() == [CloudProvider.CIVO]

        assert type(CrawlerFactory().get_marketplace("civo")) is FakeMarketplaceCrawler


def test_marketplace_crawlers_are_marketplace_crawlers() -> None:
    for crawler_cls in CrawlerFactory.MARKETPLACE_MAP.values():
        assert issubclass(crawler_cls, BaseMarketplaceCrawler)


def test_provider_without_marketplace(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.dict(CrawlerFactory.MARKETPLACE_MAP, {}, clear=True),
        pytest.raises(NoMarketplaceError, match="has no marketplace") as exc_info,
    ):
        CrawlerFactory().get_marketplace(CloudProvider.SEEWEB)

    assert exc_info.value.provider == "seeweb"
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_unknown_marketplace_target() -> None:
    with pytest.raises(UnknownCrawlerTargetError):
        CrawlerFactory().get_marketplace("unknown-cloud")


def test_providers_with_a_marketplace() -> None:
    providers = CrawlerFactory().marketplace_providers()

    assert len(providers) == 22
    assert {CloudProvider.DEEP, CloudProvider.SEEWEB, CloudProvider.ARSYS, CloudProvider.GIGAS} & set(
        providers
    ) == set()
    assert CloudProvider.PROXIMUS not in providers
    assert CloudProvider.ECLOUD not in providers


@pytest.mark.parametrize("provider", list(CrawlerFactory.MARKETPLACE_MAP))
def test_marketplace_crawler_names_are_unique(provider: CloudProvider) -> None:
    names = [crawler_cls.name for crawler_cls in CrawlerFactory.MARKETPLACE_MAP.values()]
    catalogue_names = {crawler_cls.name for crawler_cls in CrawlerFactory.CRAWLER_MAP.values()}

    name = CrawlerFactory.MARKETPLACE_MAP[provider].name
    assert names.count(name) == 1
    assert name not in catalogue_names
    assert type(CrawlerFactory().get_marketplace(provider)) is CrawlerFactory.MARKETPLACE_MAP[provider]


class FakeStatsCrawler(BaseStatsCrawler):
    """Statistics crawler registered for the tests."""

    name = "fake-stats"


def test_statistics_crawler() -> None:
    with patch.dict(CrawlerFactory.STATISTICS_MAP, {"fake": FakeStatsCrawler}):
        assert type(CrawlerFactory().get_statistics("fake")) is FakeStatsCrawler


def test_unknown_statistics_source(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(UnknownCrawlerTargetError):
        CrawlerFactory().get_statistics("unknown-firm")

    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_synergy_is_the_statistics_source() -> None:
    assert type(CrawlerFactory().get_statistics("synergy")) is SynergyResearchCrawler
