from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, Final, List, Optional, Type, Union

from classifier.software_classifier import SoftwareClassifier

# First Party Imports.
from crawler.cloud.alibaba.crawler import AlibabaCloudCrawler
from crawler.cloud.alibaba.marketplace import AlibabaMarketplaceCrawler
from crawler.cloud.arsys.crawler import ArsysCrawler
from crawler.cloud.aruba.crawler import ArubaCloudCrawler
from crawler.cloud.aruba.marketplace import ArubaCloudMarketplaceCrawler
from crawler.cloud.aws.crawler import AWSCrawler
from crawler.cloud.aws.marketplace import AWSMarketplaceCrawler
from crawler.cloud.azure.crawler import AzureCrawler
from crawler.cloud.azure.marketplace import AzureMarketplaceCrawler
from crawler.cloud.baidu.crawler import BaiduAICloudCrawler
from crawler.cloud.baidu.marketplace import BaiduMarketplaceCrawler
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.civo.crawler import CivoCrawler
from crawler.cloud.civo.marketplace import CivoMarketplaceCrawler
from crawler.cloud.cloudru.crawler import CloudRuCrawler
from crawler.cloud.cloudru.marketplace import CloudRuMarketplaceCrawler
from crawler.cloud.combell.crawler import CombellCrawler
from crawler.cloud.combell.marketplace import CombellMarketplaceCrawler
from crawler.cloud.ctyun.crawler import ChinaTelecomCloudCrawler
from crawler.cloud.ctyun.marketplace import ChinaTelecomMarketplaceCrawler
from crawler.cloud.deep.crawler import DEEPCrawler
from crawler.cloud.ecloud.crawler import ChinaMobileCloudCrawler
from crawler.cloud.exoscale.crawler import ExoscaleCrawler
from crawler.cloud.exoscale.marketplace import ExoscaleMarketplaceCrawler
from crawler.cloud.gcore.crawler import GcoreCrawler
from crawler.cloud.gcore.marketplace import GcoreMarketplaceCrawler
from crawler.cloud.gcp.crawler import GoogleCloudPlatformCrawler
from crawler.cloud.gcp.marketplace import GoogleCloudMarketplaceCrawler
from crawler.cloud.gigas.crawler import GigasCrawler
from crawler.cloud.huawei.crawler import HuaweiCloudCrawler
from crawler.cloud.huawei.marketplace import HuaweiMarketplaceCrawler
from crawler.cloud.ibm.crawler import IBMCloudCrawler
from crawler.cloud.ibm.marketplace import IBMMarketplaceCrawler
from crawler.cloud.infomaniak.crawler import InfomaniakCrawler
from crawler.cloud.infomaniak.marketplace import InfomaniakMarketplaceCrawler
from crawler.cloud.krystal.crawler import KrystalCrawler
from crawler.cloud.krystal.marketplace import KrystalMarketplaceCrawler
from crawler.cloud.oracle.crawler import OracleCloudCrawler
from crawler.cloud.oracle.marketplace import OracleMarketplaceCrawler
from crawler.cloud.ovh.crawler import OVHcloudCrawler
from crawler.cloud.ovh.marketplace import OVHcloudMarketplaceCrawler
from crawler.cloud.proximus.crawler import ProximusNXTCrawler
from crawler.cloud.scaleway.crawler import ScalewayCrawler
from crawler.cloud.scaleway.marketplace import ScalewayMarketplaceCrawler
from crawler.cloud.seeweb.crawler import SeewebCrawler
from crawler.cloud.selectel.crawler import SelectelCrawler
from crawler.cloud.selectel.marketplace import SelectelMarketplaceCrawler
from crawler.cloud.stackit.crawler import STACKITCrawler
from crawler.cloud.stackit.marketplace import STACKITMarketplaceCrawler
from crawler.cloud.tcloud.crawler import TCloudPublicCrawler
from crawler.cloud.tcloud.marketplace import TCloudPublicMarketplaceCrawler
from crawler.cloud.tencent.crawler import TencentCloudCrawler
from crawler.cloud.tencent.marketplace import TencentMarketplaceCrawler
from crawler.cloud.vkcloud.crawler import VKCloudCrawler
from crawler.cloud.vkcloud.marketplace import VKCloudMarketplaceCrawler
from crawler.cloud.volcengine.crawler import VolcanoEngineCrawler
from crawler.cloud.volcengine.marketplace import VolcanoEngineMarketplaceCrawler
from crawler.cloud.yandex.crawler import YandexCloudCrawler
from crawler.cloud.yandex.marketplace import YandexMarketplaceCrawler
from crawler.exception import NoMarketplaceError, UnknownCrawlerTargetError
from crawler.marketplace.base import BaseMarketplaceCrawler
from crawler.markets.base import BaseMarketsCrawler
from crawler.markets.fred.crawler import FredCrawler
from crawler.markets.google_finance.crawler import GoogleFinanceCrawler
from crawler.markets.idc.crawler import IdcCrawler
from crawler.markets.statcounter.crawler import StatCounterCrawler
from crawler.markets.trendforce.crawler import TrendForceCrawler
from crawler.markets.worldbank.crawler import WorldBankCrawler
from crawler.metrics.base import BaseMetricsCrawler
from crawler.metrics.edgar.crawler import EdgarCrawler
from crawler.metrics.github.crawler import GithubCrawler
from crawler.metrics.peeringdb.crawler import PeeringdbCrawler
from crawler.metrics.wikidata.crawler import WikidataCrawler
from crawler.stats.base import BaseStatsCrawler
from crawler.stats.synergy import SynergyResearchCrawler
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.enums import MetricSource
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.markets_catalog import MarketsCatalog


class CrawlerFactory:
    """Class instantiating user required crawler.

    Attributes:
        CRAWLER_MAP (Final[Dict[CloudProvider, Type[BaseCloudCrawler]]]): Mapping between the
            targeted types & corresponding crawler.
        MARKETPLACE_MAP (Final[Dict[CloudProvider, Type[BaseMarketplaceCrawler]]]): The marketplace crawler of each
            cloud provider having a marketplace (or a list of one-click applications).
        STATISTICS_MAP (Final[Dict[str, Type[BaseStatsCrawler]]]): The crawler of each market statistics source, by
            name (e.g. `synergy`).
        METRICS_MAP (Final[Dict[MetricSource, Type[BaseMetricsCrawler]]]): The crawler of each metric source.
        MARKETS_MAP (Final[Dict[MarketFeed, Type[BaseMarketsCrawler]]]): The crawler of each source of the market
            shares, the stock prices and the exchange rates, in the order a full markets crawl runs them.
    """

    CRAWLER_MAP: Final[Dict[CloudProvider, Type[BaseCloudCrawler]]] = {
        CloudProvider.AWS: AWSCrawler,
        CloudProvider.AZURE: AzureCrawler,
        CloudProvider.GCP: GoogleCloudPlatformCrawler,
        CloudProvider.IBM: IBMCloudCrawler,
        CloudProvider.ORACLE: OracleCloudCrawler,
        CloudProvider.OVH: OVHcloudCrawler,
        CloudProvider.SCALEWAY: ScalewayCrawler,
        CloudProvider.COMBELL: CombellCrawler,
        CloudProvider.PROXIMUS: ProximusNXTCrawler,
        CloudProvider.STACKIT: STACKITCrawler,
        CloudProvider.TCLOUD: TCloudPublicCrawler,
        CloudProvider.ARUBA: ArubaCloudCrawler,
        CloudProvider.SEEWEB: SeewebCrawler,
        CloudProvider.GCORE: GcoreCrawler,
        CloudProvider.DEEP: DEEPCrawler,
        CloudProvider.ARSYS: ArsysCrawler,
        CloudProvider.GIGAS: GigasCrawler,
        CloudProvider.EXOSCALE: ExoscaleCrawler,
        CloudProvider.INFOMANIAK: InfomaniakCrawler,
        CloudProvider.CIVO: CivoCrawler,
        CloudProvider.KRYSTAL: KrystalCrawler,
        CloudProvider.ALIBABA: AlibabaCloudCrawler,
        CloudProvider.HUAWEI: HuaweiCloudCrawler,
        CloudProvider.TENCENT: TencentCloudCrawler,
        CloudProvider.BAIDU: BaiduAICloudCrawler,
        CloudProvider.VOLCENGINE: VolcanoEngineCrawler,
        CloudProvider.CTYUN: ChinaTelecomCloudCrawler,
        CloudProvider.ECLOUD: ChinaMobileCloudCrawler,
        CloudProvider.YANDEX_CLOUD: YandexCloudCrawler,
        CloudProvider.VK_CLOUD: VKCloudCrawler,
        CloudProvider.CLOUD_RU: CloudRuCrawler,
        CloudProvider.SELECTEL: SelectelCrawler,
    }

    MARKETPLACE_MAP: Final[Dict[CloudProvider, Type[BaseMarketplaceCrawler]]] = {
        CloudProvider.AWS: AWSMarketplaceCrawler,
        CloudProvider.AZURE: AzureMarketplaceCrawler,
        CloudProvider.GCP: GoogleCloudMarketplaceCrawler,
        CloudProvider.IBM: IBMMarketplaceCrawler,
        CloudProvider.ORACLE: OracleMarketplaceCrawler,
        CloudProvider.OVH: OVHcloudMarketplaceCrawler,
        CloudProvider.SCALEWAY: ScalewayMarketplaceCrawler,
        CloudProvider.COMBELL: CombellMarketplaceCrawler,
        CloudProvider.STACKIT: STACKITMarketplaceCrawler,
        CloudProvider.TCLOUD: TCloudPublicMarketplaceCrawler,
        CloudProvider.ARUBA: ArubaCloudMarketplaceCrawler,
        CloudProvider.GCORE: GcoreMarketplaceCrawler,
        CloudProvider.EXOSCALE: ExoscaleMarketplaceCrawler,
        CloudProvider.INFOMANIAK: InfomaniakMarketplaceCrawler,
        CloudProvider.CIVO: CivoMarketplaceCrawler,
        CloudProvider.KRYSTAL: KrystalMarketplaceCrawler,
        CloudProvider.ALIBABA: AlibabaMarketplaceCrawler,
        CloudProvider.HUAWEI: HuaweiMarketplaceCrawler,
        CloudProvider.TENCENT: TencentMarketplaceCrawler,
        CloudProvider.BAIDU: BaiduMarketplaceCrawler,
        CloudProvider.VOLCENGINE: VolcanoEngineMarketplaceCrawler,
        CloudProvider.CTYUN: ChinaTelecomMarketplaceCrawler,
        CloudProvider.YANDEX_CLOUD: YandexMarketplaceCrawler,
        CloudProvider.VK_CLOUD: VKCloudMarketplaceCrawler,
        CloudProvider.CLOUD_RU: CloudRuMarketplaceCrawler,
        CloudProvider.SELECTEL: SelectelMarketplaceCrawler,
    }

    STATISTICS_MAP: Final[Dict[str, Type[BaseStatsCrawler]]] = {"synergy": SynergyResearchCrawler}
    METRICS_MAP: Final[Dict[MetricSource, Type[BaseMetricsCrawler]]] = {
        MetricSource.EDGAR: EdgarCrawler,
        MetricSource.WIKIDATA: WikidataCrawler,
        MetricSource.PEERINGDB: PeeringdbCrawler,
        MetricSource.GITHUB: GithubCrawler,
    }
    MARKETS_MAP: Final[Dict[MarketFeed, Type[BaseMarketsCrawler]]] = {
        MarketFeed.FRED: FredCrawler,
        MarketFeed.WORLD_BANK: WorldBankCrawler,
        MarketFeed.GOOGLE_FINANCE: GoogleFinanceCrawler,
        MarketFeed.STATCOUNTER: StatCounterCrawler,
        MarketFeed.TRENDFORCE: TrendForceCrawler,
        MarketFeed.IDC: IdcCrawler,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Crawler abstract factory.

        Args:
            logger (Optional[Logger]): The class logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _provider(self, target: Union[CloudProvider, str]) -> CloudProvider:
        """Get the cloud provider of a target.

        Args:
            target (Union[CloudProvider, str]): The user targeted crawler.

        Returns:
            CloudProvider: The cloud provider.

        Raises:
            UnknownCrawlerTargetError: If the target is not a cloud provider.
        """
        try:
            return CloudProvider(target)
        except ValueError as e:
            self.logger.error("There is no crawler available for this target: %s", target)
            raise UnknownCrawlerTargetError(str(target)) from e

    ############################
    # Publicly Exposed Methods #
    ############################

    def get(self, target: Union[CloudProvider, str]) -> BaseCloudCrawler:
        """Get the cloud provider crawler instance.

        Args:
            target (Union[CloudProvider, str]): The user targeted crawler.

        Returns:
            BaseCloudCrawler: The crawler ready to run (session configured in the base class).

        Raises:
            UnknownCrawlerTargetError: If no crawler is available for the given target.
        """
        self.logger.debug("Looking up the crawler of the target %r.", target)
        crawler_type = self._provider(target)
        crawler = self.CRAWLER_MAP[crawler_type]
        self.logger.info("A crawler for this target: %s will be instantiated.", target)
        self.logger.debug("Instantiating %s for the target %s.", crawler.__name__, crawler_type.value)
        return crawler()

    def marketplace_providers(self) -> List[CloudProvider]:
        """Get the cloud providers having a marketplace crawler.

        Returns:
            List[CloudProvider]: The cloud providers, in enum order.
        """
        return [provider for provider in CloudProvider if provider in self.MARKETPLACE_MAP]

    def get_marketplace(
        self, target: Union[CloudProvider, str], classifier: Optional[SoftwareClassifier] = None
    ) -> BaseMarketplaceCrawler:
        """Get the marketplace crawler instance of a cloud provider.

        Args:
            target (Union[CloudProvider, str]): The user targeted cloud provider.
            classifier (Optional[SoftwareClassifier]): The software classifier of the crawler, the project rules
                (loaded by the crawler) by default.

        Returns:
            BaseMarketplaceCrawler: The marketplace crawler ready to run.

        Raises:
            UnknownCrawlerTargetError: If the target is not a cloud provider.
            NoMarketplaceError: If the cloud provider has no marketplace.
        """
        self.logger.debug("Looking up the marketplace crawler of the target %r.", target)
        provider = self._provider(target)
        crawler = self.MARKETPLACE_MAP.get(provider)
        if crawler is None:
            self.logger.error("The %s cloud provider has no marketplace to crawl.", provider.value)
            raise NoMarketplaceError(provider.value)
        self.logger.info("Instantiating %s for the %s marketplace.", crawler.__name__, provider.value)
        return crawler(classifier=classifier)

    def get_statistics(self, name: str) -> BaseStatsCrawler:
        """Get the crawler instance of a market statistics source.

        Args:
            name (str): The source name, e.g. `synergy`.

        Returns:
            BaseStatsCrawler: The statistics crawler ready to run.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
        """
        crawler = self.STATISTICS_MAP.get(name)
        if crawler is None:
            self.logger.error("There is no statistics crawler for the source: %s", name)
            raise UnknownCrawlerTargetError(name)
        self.logger.info("Instantiating %s for the %s statistics.", crawler.__name__, name)
        return crawler()

    def get_metrics(self, source: MetricSource, catalog: Optional[CollectorCatalog] = None) -> BaseMetricsCrawler:
        """Get the crawler instance of a metric source.

        Args:
            source (MetricSource): The source, e.g. SEC EDGAR.
            catalog (Optional[CollectorCatalog]): Where each provider is found, `conf/metrics/collectors.yaml` by
                default.

        Returns:
            BaseMetricsCrawler: The metrics crawler ready to run.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            CollectorCatalogError: If the default catalogue cannot be loaded.
        """
        crawler = self.METRICS_MAP.get(source)
        if crawler is None:
            self.logger.error("There is no metrics crawler for the source: %s", source.value)
            raise UnknownCrawlerTargetError(source.value)
        self.logger.info("Instantiating %s for the %s metrics.", crawler.__name__, source.value)
        return crawler(catalog=catalog)

    def get_markets(
        self, feed: MarketFeed, catalog: Optional[MarketsCatalog] = None, scope: Optional[CrawlScope] = None
    ) -> BaseMarketsCrawler:
        """Get the crawler instance of a markets source.

        Args:
            feed (MarketFeed): The source, e.g. StatCounter.
            catalog (Optional[MarketsCatalog]): What is read, `conf/history/markets.yaml` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.

        Returns:
            BaseMarketsCrawler: The markets crawler ready to run.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        crawler = self.MARKETS_MAP.get(feed)
        if crawler is None:
            self.logger.error("There is no markets crawler for the source: %s", feed.value)
            raise UnknownCrawlerTargetError(feed.value)
        self.logger.info("Instantiating %s for the %s markets data.", crawler.__name__, feed.value)
        return crawler(catalog=catalog, scope=scope)
