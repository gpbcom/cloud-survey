from __future__ import annotations

from typing import Type

import pytest

from crawler.cloud.alibaba.crawler import AlibabaCloudCrawler
from crawler.cloud.arsys.crawler import ArsysCrawler
from crawler.cloud.aruba.crawler import ArubaCloudCrawler
from crawler.cloud.aws.crawler import AWSCrawler
from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.civo.crawler import CivoCrawler
from crawler.cloud.cloudru.crawler import CloudRuCrawler
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
from crawler.cloud.selectel.crawler import SelectelCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler
from crawler.cloud.tencent.crawler import TencentCloudCrawler
from crawler.cloud.vkcloud.crawler import VKCloudCrawler
from crawler.cloud.volcengine.crawler import VolcanoEngineCrawler
from crawler.cloud.yandex.crawler import YandexCloudCrawler
from models.cloud.products.product import CloudProduct

# Smoke tests against the real websites, through the real (visible) stealth browser: `pytest --live`.
# They detect catalogue changes the offline fixtures cannot see.
pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    ("crawler_cls", "minimum"),
    [
        (AWSCrawler, 300),
        (AzureCrawler, 210),
        (GoogleCloudPlatformCrawler, 185),
        (IBMCloudCrawler, 90),
        (OracleCloudCrawler, 125),
        (OVHcloudCrawler, 100),
        (ScalewayCrawler, 75),
        (CombellCrawler, 48),
        (ProximusNXTCrawler, 37),
        (STACKITCrawler, 38),
        (TCloudPublicCrawler, 53),
        (ArubaCloudCrawler, 35),
        (SeewebCrawler, 22),
        (GcoreCrawler, 40),
        (DEEPCrawler, 48),
        (ArsysCrawler, 41),
        (GigasCrawler, 15),
        (ExoscaleCrawler, 24),
        (InfomaniakCrawler, 36),
        (CivoCrawler, 23),
        (KrystalCrawler, 21),
        (AlibabaCloudCrawler, 210),
        (HuaweiCloudCrawler, 140),
        (TencentCloudCrawler, 185),
        (BaiduAICloudCrawler, 215),
        (VolcanoEngineCrawler, 110),
        (ChinaTelecomCloudCrawler, 145),
        (ChinaMobileCloudCrawler, 175),
        (YandexCloudCrawler, 65),
        (VKCloudCrawler, 42),
        (CloudRuCrawler, 115),
        (SelectelCrawler, 88),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
)
async def test_crawls_the_catalogue(crawler_cls: Type[BaseCloudCrawler], minimum: int) -> None:
    crawler = crawler_cls()

    products = [CloudProduct.model_validate(item) async for item in crawler.stream()]

    assert len(products) >= minimum
    assert len({product.name.casefold() for product in products}) == len(products)
