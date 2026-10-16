from __future__ import annotations

from typing import Type
from unittest.mock import MagicMock

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

PROVIDER_CRAWLERS = [
    AWSCrawler,
    AzureCrawler,
    GoogleCloudPlatformCrawler,
    IBMCloudCrawler,
    OracleCloudCrawler,
    OVHcloudCrawler,
    ScalewayCrawler,
    CombellCrawler,
    ProximusNXTCrawler,
    STACKITCrawler,
    TCloudPublicCrawler,
    ArubaCloudCrawler,
    SeewebCrawler,
    GcoreCrawler,
    DEEPCrawler,
    ArsysCrawler,
    GigasCrawler,
    ExoscaleCrawler,
    InfomaniakCrawler,
    CivoCrawler,
    KrystalCrawler,
    AlibabaCloudCrawler,
    HuaweiCloudCrawler,
    TencentCloudCrawler,
    BaiduAICloudCrawler,
    VolcanoEngineCrawler,
    ChinaTelecomCloudCrawler,
    ChinaMobileCloudCrawler,
]

pytestmark = pytest.mark.parametrize("crawler_cls", PROVIDER_CRAWLERS, ids=lambda cls: cls.__name__)


def test_inherits_from_base_crawler(crawler_cls: Type[BaseCloudCrawler]) -> None:
    assert issubclass(crawler_cls, BaseCloudCrawler)


def test_has_docstring(crawler_cls: Type[BaseCloudCrawler]) -> None:
    assert crawler_cls.__doc__


def test_can_be_instantiated(crawler_cls: Type[BaseCloudCrawler], stealth_session_cls: MagicMock) -> None:
    crawler = crawler_cls()

    assert isinstance(crawler, crawler_cls)
    assert crawler._session_manager.session_ids == [f"{crawler.name}-session"]
    stealth_session_cls.assert_called_once()


def test_implements_the_extraction(crawler_cls: Type[BaseCloudCrawler]) -> None:
    # A listing which only links to product pages yields their requests from `parse`.
    assert (
        crawler_cls.extract_products is not BaseCloudCrawler.extract_products
        or crawler_cls.parse is not BaseCloudCrawler.parse
    )


def test_has_a_catalogue_url(crawler_cls: Type[BaseCloudCrawler]) -> None:
    assert crawler_cls.catalogue_url.startswith("https://")


def test_names_are_unique(crawler_cls: Type[BaseCloudCrawler]) -> None:
    assert [cls.name for cls in PROVIDER_CRAWLERS].count(crawler_cls.name) == 1
