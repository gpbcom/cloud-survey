from __future__ import annotations

# Standard Library Imports.
import asyncio
import gc
import os
import threading
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Type, Union

# Third Party Imports.
from pydantic import JsonValue

from classifier.exception import ClassifierError
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler, PriceItem
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from crawler.item_collector import ItemCollector
from crawler.metrics.catalog_loader import CollectorCatalogLoader

# First Party Imports.
from llm.exception import LLMConfigurationFileError, LLMError
from llm.settings_loader import LLMSettingsLoader
from llm.tasks.correspondence.service_matcher import ServiceMatcher
from llm.tasks.item_classifier import ItemClassifier
from llm.tasks.label_translator import LabelTranslator
from models.cloud.enums import CloudProvider, PriceSourceStatus
from models.cloud.prices.stored.price_source import PriceSource
from models.cloud.products.catalogue import CloudCatalogue
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace import CloudMarketplace
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.companies.companies_catalog import CompaniesCatalog
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.enums import CompanyFeed
from models.companies.figures.reported_figures import ReportedFigures
from models.companies.patents.patent_window import PatentWindow
from models.configuration.llm.llm_settings import LLMSettings
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.enums import MetricSource
from models.history.chronology import Chronology
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.markets_catalog import MarketsCatalog
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics
from models.storage.crawl_summary import CrawlSummary
from models.storage.enums import CrawlStatus
from storage.exception import StorageError
from storage.storage import Storage

ProductCallback = Callable[[CloudProvider, CloudProduct], None]
SoftwareCallback = Callable[[CloudProvider, MarketplaceSoftware], None]
ReportCallback = Callable[[MarketReport], None]
ProductSink = Callable[[CloudProduct], Awaitable[None]]
SoftwareSink = Callable[[MarketplaceSoftware], Awaitable[None]]
FactSink = Callable[[MarketFeed, List[Dict[str, JsonValue]]], Awaitable[int]]
CompanySink = Callable[[CompanyFeed, List[Dict[str, JsonValue]]], Awaitable[int]]
CompanyObserver = Callable[[CompanyFeed, List[Dict[str, JsonValue]], int], None]
PriceSink = Callable[[List[PriceItem]], Awaitable[int]]


class CatalogueRunner:
    """Crawl the cloud providers catalogues, marketplaces and market statistics, and write them to the storage.

    Attributes:
        DEFAULT_CONCURRENCY (ClassVar[int]): The number of providers crawled at the same time by default.
        MARKETS_BATCH (ClassVar[int]): The facts of a markets crawl handed to its sink at once.
        PRICE_MIN_BATCH (ClassVar[int]): The smallest batch of a price crawl, however tight its memory.
        STATM_PATH (ClassVar[str]): Where the memory the process uses is read (Linux).
        CONCURRENCY_VARIABLE (ClassVar[str]): The environment variable overriding the default concurrency.
        SAVE_INTERVAL (ClassVar[float]): How often, in seconds, a running crawl writes the items crawled so far by
            default.
        storage (Storage): The storage the crawls are written to, opened by the caller (`async with storage`).
        factory (CrawlerFactory): The factory building the crawlers.
        logger (Logger): The runner logger.
        classifier (Optional[SoftwareClassifier]): The classifier of the marketplace software and of the catalogue
            products, loaded once (at the first crawl) so that the rules cannot change during a run.
        concurrency (int): The number of providers crawled at the same time, at least 1.
        llm_settings (Optional[LLMSettings]): The language model settings, read at the first crawl.
        save_interval (float): How often, in seconds, a running crawl writes the items crawled so far.

    Notes:
        Several providers are crawled at the same time, at most `concurrency` of them: each website is still crawled
        one request at a time, with its own delay. Each crawl is dated from the stored items (see `ItemWriter`). The
        items are written progressively: every `save_interval` seconds (or every batch) the items crawled so far, the
        missing items being marked deleted once the crawl is over. Once a crawl is over (its lock released), the
        pending source labels are translated and the unclassified items of its provider categorized by the language
        model, when one is configured (`conf/llm.yaml`): a failure there is logged, never a failed crawl.
    """

    DEFAULT_CONCURRENCY: ClassVar[int] = 4
    MARKETS_BATCH: ClassVar[int] = 5000
    PRICE_MIN_BATCH: ClassVar[int] = 500
    STATM_PATH: ClassVar[str] = "/proc/self/statm"
    CONCURRENCY_VARIABLE: ClassVar[str] = "CRAWLER_CONCURRENCY"
    SAVE_INTERVAL: ClassVar[float] = 10.0

    def __init__(
        self,
        storage: Optional[Storage] = None,
        factory: Optional[CrawlerFactory] = None,
        logger: Optional[Logger] = None,
        concurrency: Optional[int] = None,
        save_interval: Optional[float] = None,
        llm_settings: Optional[LLMSettings] = None,
    ) -> None:
        """Initialize the runner.

        Args:
            storage (Optional[Storage]): The storage the crawls are written to, configured from the environment by
                default. It is opened by the caller.
            factory (Optional[CrawlerFactory]): The factory building the crawlers.
            logger (Optional[Logger]): The runner logger.
            concurrency (Optional[int]): The number of providers crawled at the same time, `CRAWLER_CONCURRENCY` (or
                4) by default.
            save_interval (Optional[float]): How often, in seconds, a running crawl writes the items crawled so far,
                every 10 s by default.
            llm_settings (Optional[LLMSettings]): The language model settings, read from `conf/llm.yaml` (or
                `CRAWLER_LLM_CONFIG`) by default.
        """
        self.storage = storage if storage else Storage()
        self.factory = factory if factory else CrawlerFactory()
        self.logger = logger if logger else getLogger(__name__)
        self.classifier: Optional[SoftwareClassifier] = None
        self.llm_settings = llm_settings
        if concurrency is None:
            raw = os.getenv(self.CONCURRENCY_VARIABLE, "").strip()
            valid = raw.isdigit() and int(raw) > 0
            if raw and not valid:
                self.logger.warning(
                    "%s=%r is not a positive number: %d providers "  # noqa: E501
                    "are crawled at the same time.",
                    self.CONCURRENCY_VARIABLE,
                    raw,
                    self.DEFAULT_CONCURRENCY,
                )
            concurrency = int(raw) if valid else self.DEFAULT_CONCURRENCY
        self.concurrency = max(1, concurrency)
        self.save_interval = self.SAVE_INTERVAL if save_interval is None else save_interval

    ############################
    # Internal Helpers Methods #
    ############################

    def _classifier(self) -> SoftwareClassifier:
        """Get the classifier of the marketplace software, loading the rules the first time.

        Returns:
            SoftwareClassifier: The classifier shared by the marketplace crawls of the runner.

        Raises:
            ClassificationRulesFileError: If the classification rules cannot be loaded.
        """
        self.logger.debug("Getting the software classifier (loaded: %s).", self.classifier is not None)
        if self.classifier is None:
            self.classifier = SoftwareClassifier()
        return self.classifier

    def _provider_of(self, target: Union[CloudProvider, str]) -> Optional[CloudProvider]:
        """Get the cloud provider of a target, leaving the unknown targets to the crawler factory.

        Args:
            target (Union[CloudProvider, str]): The crawl target.

        Returns:
            Optional[CloudProvider]: The cloud provider, `None` when the target is not one.
        """
        self.logger.debug("Resolving the cloud provider of the target %r.", target)
        try:
            return CloudProvider(target)
        except ValueError:
            return None

    async def _guarded(
        self,
        semaphore: asyncio.Semaphore,
        provider: CloudProvider,
        job: Callable[[CloudProvider], Awaitable[CrawlSummary]],
        errors: Tuple[Type[Exception], ...],
        noun: str,
    ) -> Optional[CrawlSummary]:
        """Run the crawl of one provider when the concurrency allows it, logging its failure.

        Args:
            semaphore (asyncio.Semaphore): The semaphore limiting the crawls running at the same time.
            provider (CloudProvider): The crawled provider.
            job (Callable[[CloudProvider], Awaitable[CrawlSummary]]): The crawl of one provider.
            errors (Tuple[Type[Exception], ...]): The errors failing this provider only.
            noun (str): What is crawled, for the logs (e.g. `catalogue`).

        Returns:
            Optional[CrawlSummary]: What the crawl wrote, `None` when it failed (logged).
        """
        async with semaphore:
            try:
                return await job(provider)
            except errors as e:
                self.logger.error("The %s %s was not updated: %s", provider.value, noun, e)
                return None

    async def _run_parallel(
        self,
        targets: List[CloudProvider],
        job: Callable[[CloudProvider], Awaitable[CrawlSummary]],
        errors: Tuple[Type[Exception], ...],
        noun: str,
    ) -> Dict[CloudProvider, CrawlSummary]:
        """Run a crawl job for several providers, at most `concurrency` at the same time.

        Args:
            targets (List[CloudProvider]): The crawled providers.
            job (Callable[[CloudProvider], Awaitable[CrawlSummary]]): The crawl of one provider, returning what it
                wrote.
            errors (Tuple[Type[Exception], ...]): The errors failing one provider only.
            noun (str): What is crawled, for the logs (e.g. `catalogue`).

        Returns:
            Dict[CloudProvider, CrawlSummary]: What each successful crawl wrote, by cloud provider, in the targets
                order.
        """
        semaphore = asyncio.Semaphore(self.concurrency)
        self.logger.info("Crawling %d %ss, %d at the same time.", len(targets), noun, self.concurrency)
        connections = self.storage.settings.pool_size + self.storage.settings.max_overflow
        if min(self.concurrency, len(targets)) + 1 > connections:
            self.logger.warning(
                "%d crawls at the same time need more connections "  # noqa: E501
                "than the %d of the storage pool: they will wait.",
                self.concurrency,
                connections,
            )
        summaries = await asyncio.gather(
            *(self._guarded(semaphore, provider, job, errors, noun) for provider in targets)
        )
        written = {
            provider: summary for provider, summary in zip(targets, summaries, strict=True) if summary is not None
        }
        failed = len(targets) - len(written)
        log = self.logger.warning if failed else self.logger.info
        log("%d %ss written, %d failed.", len(written), noun, failed)
        return written

    async def _stream_products(
        self,
        crawler: BaseCloudCrawler,
        provider: CloudProvider,
        on_product: Optional[ProductCallback],
        sink: ProductSink,
    ) -> int:
        """Crawl the catalogue of a cloud provider, handing each product (classified: who it is for) to a sink.

        Args:
            crawler (BaseCloudCrawler): The crawler of the catalogue.
            provider (CloudProvider): The cloud provider.
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.
            sink (ProductSink): Receives each product (the storage writer, or a collector).

        Returns:
            int: The number of products crawled.
        """
        self.logger.info("Crawling the %s catalogue.", provider.value)
        count = 0
        classifier = self._classifier()
        async for item in crawler.stream():
            product = CloudProduct.model_validate(item)
            classification = classifier.classify_product(
                product.name, product.description, product.catalogue_categories
            )
            audience = classification.audiences
            product = product.model_copy(update={"categories": audience})
            count += 1
            self.logger.debug("%s product %d received: %s", provider.value, count, product.name)
            if on_product:
                on_product(provider, product)
            await sink(product)
        self.logger.info("%s catalogue crawled: %d products.", provider.value, count)
        return count

    async def _stream_software(
        self,
        crawler: BaseCloudCrawler,
        provider: CloudProvider,
        on_software: Optional[SoftwareCallback],
        sink: SoftwareSink,
    ) -> int:
        """Crawl the marketplace of a cloud provider, handing each listing to a sink.

        Args:
            crawler (BaseCloudCrawler): The crawler of the marketplace.
            provider (CloudProvider): The cloud provider.
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.
            sink (SoftwareSink): Receives each listing, a software listed again replacing its previous listing.

        Returns:
            int: The number of distinct software crawled.
        """
        self.logger.info("Crawling the %s marketplace.", provider.value)
        seen: Set[str] = set()
        async for item in crawler.stream():
            listing = MarketplaceSoftware.model_validate(item)
            identity = listing.identity()
            is_new = identity not in seen
            seen.add(identity)
            self.logger.debug("%s software %d received: %s", provider.value, len(seen), listing.name)
            if is_new and on_software:
                on_software(provider, listing)
            await sink(listing)
        self.logger.info("%s marketplace crawled: %d software.", provider.value, len(seen))
        return len(seen)

    def _language_model(self) -> LLMSettings:
        """Get the language model settings, reading them the first time.

        Returns:
            LLMSettings: The settings, empty (no model) when they cannot be read (logged).
        """
        if self.llm_settings is None:
            try:
                self.llm_settings = LLMSettingsLoader(self.logger).load()
            except LLMConfigurationFileError as e:
                self.logger.warning("The language model settings cannot be read, no model is used: %s", e)
                self.llm_settings = LLMSettings()
        return self.llm_settings

    async def _after_crawl(self, provider: CloudProvider, catalogue: bool) -> None:
        """Run the language model tasks after the crawl of a provider.

        Args:
            provider (CloudProvider): The crawled provider.
            catalogue (bool): Whether its catalogue was crawled (its services are then matched).

        Notes:
            The pending labels are translated, the unclassified items
            of the provider are categorized, then (after a
            catalogue crawl) its new or changed services are matched
            with the equivalent services of the others.
        """
        settings = self._language_model()
        if not settings.after_crawl:
            return
        translator, classifier = LabelTranslator(self.storage, settings), ItemClassifier(self.storage, settings)
        matcher = ServiceMatcher(self.storage, settings) if catalogue else None
        configured = [task.is_configured() for task in (translator, classifier)]
        if not any(configured) and (matcher is None or not matcher.is_configured()):
            self.logger.debug("No language model after the %s crawl.", provider.value)
            return
        try:
            translated = await translator.run()
            classified = await classifier.run(provider)
            matched = await matcher.run(provider) if matcher is not None else 0
        except (LLMError, StorageError) as e:
            self.logger.warning("The language model tasks after the %s crawl stopped: %s", provider.value, e)
            return
        self.logger.info(
            "After the %s crawl, the language model translated %d labels, "  # noqa: E501
            "categorized %d items, matched %d services.",
            provider.value,
            translated,
            classified,
            matched,
        )

    def _rss_mb(self) -> float:
        """Read the memory the process uses now (its resident set), in MB.

        Returns:
            float: The resident memory, 0 when it cannot be read (not Linux).
        """
        try:
            with open(self.STATM_PATH, encoding="utf-8") as file:
                pages = int(file.read().split()[1])
        except (OSError, ValueError, IndexError) as e:
            self.logger.warning("The memory of the process cannot be read: %s", e)
            return 0.0
        rss = pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
        self.logger.debug("The process uses %.0f MB.", rss)
        return rss

    ############################
    # Publicly Exposed Methods #
    ############################

    async def crawl(
        self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None
    ) -> CloudCatalogue:
        """Crawl the catalogue of a cloud provider, without writing it.

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.

        Returns:
            CloudCatalogue: The crawled catalogue, possibly empty.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
        """
        self.logger.debug("Crawling the %s catalogue without writing it.", target)
        crawler = self.factory.get(target)
        provider = CloudProvider(target)
        crawled_at = datetime.now(UTC)
        collector = ItemCollector[CloudProduct]()
        await self._stream_products(crawler, provider, on_product, collector.add)
        return CloudCatalogue(provider=provider, crawled_at=crawled_at, products=collector.items())

    async def run(
        self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None
    ) -> CrawlSummary:
        """Crawl the catalogue of a cloud provider and write it to the storage, progressively (see the class notes).

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.

        Returns:
            CrawlSummary: What the crawl wrote.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            EmptyCrawlError: If the crawl produced no product (the stored catalogue is unchanged).
            StorageError: If the catalogue cannot be written.
        """
        crawler = self.factory.get(target)
        crawler.use_launches(await self.storage.catalogs.launches())
        provider = CloudProvider(target)
        async with self.storage.catalogues.writer(provider, datetime.now(UTC), self.save_interval) as writer:
            count = await self._stream_products(crawler, provider, on_product, writer.add)
            if not count:
                await writer.abort(CrawlStatus.EMPTY, "no product crawled")
                self.logger.error("The %s crawl produced no product: its catalogue is unchanged.", provider.value)
                raise EmptyCrawlError(provider.value)
            summary = await writer.finish()
        await self._after_crawl(provider, True)
        return summary

    async def run_all(
        self, on_product: Optional[ProductCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, CrawlSummary]:
        """Crawl every cloud provider catalogue (or some of them), several at a time, and write them to the storage.

        Args:
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.
            providers (Optional[List[CloudProvider]]): The crawled providers, every provider by default.

        Returns:
            Dict[CloudProvider, CrawlSummary]: What each successful crawl wrote, by cloud provider.
        """
        self.logger.info("Crawling %s catalogues.", "every" if providers is None else len(providers))
        targets = list(CloudProvider) if providers is None else providers
        return await self._run_parallel(
            targets, lambda provider: self.run(provider, on_product), (CrawlerError, StorageError), "catalogue"
        )

    async def crawl_marketplace(
        self, target: Union[CloudProvider, str], on_software: Optional[SoftwareCallback] = None
    ) -> CloudMarketplace:
        """Crawl the marketplace of a cloud provider, without writing it.

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.

        Returns:
            CloudMarketplace: The crawled marketplace, possibly empty, a software listed again keeping its last
                listing.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            NoMarketplaceError: If the cloud provider has no marketplace.
        """
        self.logger.debug("Crawling the %s marketplace without writing it.", target)
        crawler = self.factory.get_marketplace(target, self._classifier())
        provider = CloudProvider(target)
        crawled_at = datetime.now(UTC)
        collector = ItemCollector[MarketplaceSoftware]()
        await self._stream_software(crawler, provider, on_software, collector.add)
        return CloudMarketplace(provider=provider, crawled_at=crawled_at, software=collector.items())

    async def run_marketplace(
        self, target: Union[CloudProvider, str], on_software: Optional[SoftwareCallback] = None
    ) -> CrawlSummary:
        """Crawl the marketplace of a cloud provider and write it to the storage, progressively (see the class notes).

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.

        Returns:
            CrawlSummary: What the crawl wrote.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            NoMarketplaceError: If the cloud provider has no marketplace.
            EmptyCrawlError: If the crawl produced no software (the stored marketplace is unchanged).
            StorageError: If the marketplace cannot be written.
        """
        crawler = self.factory.get_marketplace(target, self._classifier())
        crawler.use_launches(await self.storage.catalogs.launches())
        provider = CloudProvider(target)
        async with self.storage.marketplaces.writer(provider, datetime.now(UTC), self.save_interval) as writer:
            count = await self._stream_software(crawler, provider, on_software, writer.add)
            if not count:
                await writer.abort(CrawlStatus.EMPTY, "no software crawled")
                self.logger.error(
                    "The %s marketplace crawl produced no software: its marketplace is unchanged.", provider.value
                )
                raise EmptyCrawlError(provider.value)
            summary = await writer.finish()
        await self._after_crawl(provider, False)
        return summary

    async def run_all_marketplaces(
        self, on_software: Optional[SoftwareCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, CrawlSummary]:
        """Crawl the marketplaces of every cloud provider having one (or of some of them), several at the same time.

        Args:
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.
            providers (Optional[List[CloudProvider]]): The crawled providers, every provider having a marketplace by
                default.

        Returns:
            Dict[CloudProvider, CrawlSummary]: What each successful crawl wrote, by cloud provider.
        """
        self.logger.info("Crawling %s marketplaces.", "every" if providers is None else len(providers))
        targets = self.factory.marketplace_providers() if providers is None else providers
        return await self._run_parallel(
            targets,
            lambda provider: self.run_marketplace(provider, on_software),
            (CrawlerError, StorageError, ClassifierError),
            "marketplace",
        )

    async def refresh_taxonomy(self) -> int:
        """Apply the taxonomy seed files when they changed, then link every source label again with the current rules.

        Returns:
            int: The number of source labels whose rule links or status changed.

        Raises:
            ClassificationRulesFileError: If the classification rules cannot be loaded.
            StorageWriteError: If the seed or the links cannot be written.
        """
        classifier = self._classifier()
        await self.storage.seeder.seed()
        changed = await self.storage.labels.recompute_rule_links(classifier)
        self.logger.info("Taxonomy refreshed: %d source labels linked again.", changed)
        return changed

    async def reclassify_marketplaces(self) -> Dict[CloudProvider, int]:
        """Classify the stored marketplace software again with the current taxonomy and links, without crawling.

        Returns:
            Dict[CloudProvider, int]: The number of software whose classification changed, by cloud provider (the
                marketplaces not stored, being crawled or failing are left out, logged).
        """
        changed: Dict[CloudProvider, int] = {}
        for provider in CloudProvider:
            try:
                count = await self.storage.marketplaces.reclassify(provider)
            except StorageError as e:
                self.logger.error("The %s marketplace was not classified again: %s", provider.value, e)
                continue
            if count is not None:
                changed[provider] = count
        self.logger.info("%d marketplaces classified again.", len(changed))
        return changed

    async def reclassify_catalogues(self) -> Dict[CloudProvider, int]:
        """Classify the stored catalogue products again with the current taxonomy and links, without crawling.

        Returns:
            Dict[CloudProvider, int]: The number of products whose categories changed, by cloud provider (the
                catalogues not stored, being crawled or failing are left out, logged).
        """
        changed: Dict[CloudProvider, int] = {}
        for provider in CloudProvider:
            try:
                count = await self.storage.catalogues.reclassify(provider)
            except StorageError as e:
                self.logger.error("The %s catalogue was not classified again: %s", provider.value, e)
                continue
            if count is not None:
                changed[provider] = count
        self.logger.info("%d catalogues classified again.", len(changed))
        return changed

    async def date_launches(self) -> Dict[CloudProvider, int]:
        """Date the stored catalogue products by their curated launch (the launch dates catalogue), without crawling.

        Returns:
            Dict[CloudProvider, int]: The number of products whose added date changed, by cloud provider (the
                catalogues being crawled or failing are left out, logged).

        Raises:
            StorageReadError: If the curated launches cannot be read (a database never seeded).

        Notes:
            Each provider's crawler matches the stored product names to the catalogue as a crawl does (brand
            prefixes ignored). The dated sources the crawlers read (feeds, release notes) need a crawl: only the
            curated launches are written.
        """
        changed: Dict[CloudProvider, int] = {}
        catalog = await self.storage.catalogs.launches()
        for provider in self.factory.CRAWLER_MAP:
            try:
                crawler = self.factory.get(provider)
                crawler.use_launches(catalog)
                names = await self.storage.catalogues.live_names(provider)
                launches = {
                    item_id: launch for item_id, name in names.items() if (launch := crawler.curated_launch(name))
                }
                changed[provider] = await self.storage.catalogues.set_launches(provider, launches)
            except (CrawlerError, StorageError) as e:
                self.logger.error("The %s products were not dated by their launch: %s", provider.value, e)
        self.logger.info("%d catalogues dated by their curated launches.", len(changed))
        return changed

    async def run_statistics(self, name: str = "synergy", on_report: Optional[ReportCallback] = None) -> CrawlSummary:
        """Crawl the market statistics of a source and write them to the storage.

        Args:
            name (str): The source name, e.g. `synergy`.
            on_report (Optional[ReportCallback]): Called with each new report as soon as it is crawled.

        Returns:
            CrawlSummary: What the crawl wrote.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            EmptyCrawlError: If the crawl produced no report (the stored statistics are unchanged).
            StorageError: If the statistics cannot be written.
        """
        crawler = self.factory.get_statistics(name)
        self.logger.info("Crawling the %s market statistics.", name)
        crawled_at = datetime.now(UTC)
        reports: Dict[Tuple[str, str, str], MarketReport] = {}
        async for item in crawler.stream():
            report = MarketReport.model_validate(item)
            key = (report.period, report.region.value, report.segment.value)
            is_new = key not in reports
            reports[key] = report
            if is_new and on_report:
                on_report(report)
        if not reports:
            self.logger.error("The %s statistics crawl produced no report: the stored statistics are kept.", name)
            raise EmptyCrawlError(name)
        ordered = sorted(
            reports.values(), key=lambda report: (report.region.value, report.segment.value, report.sort_key())
        )
        statistics = MarketStatistics(source=crawler.source, crawled_at=crawled_at, reports=ordered)
        return await self.storage.statistics.replace(name, statistics)

    async def crawl_metrics(
        self, catalog: Optional[CollectorCatalog] = None
    ) -> Dict[MetricSource, List[Dict[str, JsonValue]]]:
        """Crawl every metric source (SEC EDGAR, Wikidata, PeeringDB, GitHub), one after the other.

        Args:
            catalog (Optional[CollectorCatalog]): Where each provider is found, `conf/metrics/collectors.yaml` by
                default.

        Returns:
            Dict[MetricSource, List[Dict[str, JsonValue]]]: The facts crawled at each source, as the source states
                them. A source yielding nothing (unreachable, refused) is left out, so that its stored measures are
                kept.

        Raises:
            CollectorCatalogError: If the default catalogue cannot be loaded.
        """
        catalog = catalog if catalog else CollectorCatalogLoader(self.logger).load()
        crawled: Dict[MetricSource, List[Dict[str, JsonValue]]] = {}
        for source in self.factory.METRICS_MAP:
            crawler = self.factory.get_metrics(source, catalog)
            facts = [item async for item in crawler.stream()]
            if not facts:
                self.logger.warning(
                    "The %s metrics crawl produced no fact: its stored measures are kept.", source.value
                )
                continue
            crawled[source] = facts
        self.logger.info("Metrics crawled from %d of %d sources.", len(crawled), len(self.factory.METRICS_MAP))
        return crawled

    async def stream_markets(
        self,
        feed: MarketFeed,
        sink: FactSink,
        catalog: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
    ) -> int:
        """Crawl a markets source, handing its facts to a sink by batches as they come.

        Args:
            feed (MarketFeed): The source.
            sink (FactSink): Called with each batch of facts, as the source states them: it measures and writes
                them, and returns how many rows it wrote.
            catalog (Optional[MarketsCatalog]): What is read, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.

        Returns:
            int: The rows the sink wrote. Zero when the source yielded nothing: its stored data are kept.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            MarketsCatalogError: If the default catalogue cannot be loaded.

        Notes:
            The facts are never all held in memory: a full StatCounter crawl yields millions of them.
        """
        crawler = self.factory.get_markets(feed, catalog, scope)
        written = crawled = 0
        batch: List[Dict[str, JsonValue]] = []
        async for item in crawler.stream():
            batch.append(item)
            if len(batch) >= self.MARKETS_BATCH:
                crawled += len(batch)
                written += await sink(feed, batch)
                batch = []
        if batch:
            crawled += len(batch)
            written += await sink(feed, batch)
        if not crawled:
            self.logger.warning("The %s markets crawl produced no fact: its stored data are kept.", feed.value)
        self.logger.info("%s markets crawl: %d facts, %d rows written.", feed.value, crawled, written)
        return written

    async def stream_prices(
        self,
        provider: CloudProvider,
        sink: PriceSink,
        sources: Dict[str, PriceSource],
        batch_size: int = 10000,
        max_memory_mb: int = 1024,
        delay_s: float = 2.0,
        products: Optional[Mapping[str, Optional[str]]] = None,
        pages: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> Tuple[int, Dict[str, PriceSource], Set[str]]:
        """Crawl the price sources of a provider, handing its prices to a sink by batches as they come.

        Args:
            provider (CloudProvider): The provider.
            sink (PriceSink): Called with each batch of prices and free offers (each naming its kind): it stages
                them, and returns how many it staged.
            sources (Dict[str, PriceSource]): The price sources as last read (an unchanged one is not read again).
            batch_size (int): The prices handed to the sink at once.
            max_memory_mb (int): The memory the process may use: above it, the batches shrink.
            delay_s (float): The wait between two price requests, in seconds.
            products (Optional[Mapping[str, Optional[str]]]): The page of each live catalogue product of the
                provider, by name (stated unpriced by a provider publishing no price, read by one reading its
                product pages).
            pages (Optional[Mapping[str, Sequence[str]]]): The curated extra price pages of each product, by name.

        Returns:
            Tuple[int, Dict[str, PriceSource], Set[str]]: The prices staged, the sources read (whole or unchanged),
                and the sources which failed.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the provider.

        Notes:
            The prices are never all held in memory: after each batch, the memory of the process is read, and above
            `max_memory_mb` the garbage is collected, then the batches are halved (down to `PRICE_MIN_BATCH`).
        """
        crawler = self.factory.get(provider)
        crawler.use_prices(provider, sources, delay_s, products, pages)
        size = max(batch_size, self.PRICE_MIN_BATCH)
        staged = 0
        batch: List[PriceItem] = []
        async for item in crawler.stream():
            batch.append(item)
            if len(batch) < size:
                continue
            staged += await sink(batch)
            batch = []
            if self._rss_mb() > max_memory_mb:
                gc.collect()
                rss = self._rss_mb()
                if rss > max_memory_mb and size > self.PRICE_MIN_BATCH:
                    size = max(size // 2, self.PRICE_MIN_BATCH)
                    self.logger.warning(
                        "The %s price crawl uses %.0f MB (cap %d MB): its batches shrink to %d.",
                        provider.value,
                        rss,
                        max_memory_mb,
                        size,
                    )
        if batch:
            staged += await sink(batch)
        if crawler.price_failures:
            self.logger.error(
                "%d %s price sources failed: their prices are kept.", len(crawler.price_failures), provider.value
            )
        unchanged = all(read.status is PriceSourceStatus.UNCHANGED for read in crawler.price_reads.values())
        if not staged and crawler.price_reads and unchanged:
            self.logger.info("The %s price sources are unchanged: nothing to stage.", provider.value)
        elif not staged:
            self.logger.warning("The %s price crawl staged no price: its stored prices are kept.", provider.value)
        self.logger.info(
            "%s price crawl: %d prices staged from %d sources.", provider.value, staged, len(crawler.price_reads)
        )
        return staged, dict(crawler.price_reads), set(crawler.price_failures)

    async def stream_companies(
        self,
        feed: CompanyFeed,
        sink: CompanySink,
        companies: Optional[CompaniesCatalog] = None,
        concepts: Optional[FinancialConcepts] = None,
        markets: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        known: Optional[Sequence[PatentWindow]] = None,
        queue: Optional[Sequence[str]] = None,
        batch_size: Optional[int] = None,
        observer: Optional[CompanyObserver] = None,
        stop: Optional[threading.Event] = None,
        refusals: Optional[Dict[CompanyFeed, str]] = None,
        rejected: Optional[Dict[str, Set[str]]] = None,
        chronology: Optional[Chronology] = None,
        figures: Optional[ReportedFigures] = None,
    ) -> int:
        """Crawl a companies source, handing its facts to a sink by batches as they come.

        Args:
            feed (CompanyFeed): The source.
            sink (CompanySink): Called with each batch of facts (each naming its kind): it measures and writes
                them, and returns how many rows it wrote.
            companies (Optional[CompaniesCatalog]): Where each company is found, by default
                `data/curated/companies.json`.
            concepts (Optional[FinancialConcepts]): How the statement lines are read, by default
                the `concepts` block of `conf/settings.yaml`.
            markets (Optional[MarketsCatalog]): The listings, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The companies read, every one by default.
            known (Optional[Sequence[PatentWindow]]): The patents windows already searched (the patents search).
            queue (Optional[Sequence[str]]): The publications whose page to read (the patent pages).
            batch_size (Optional[int]): The facts handed to the sink at once, `MARKETS_BATCH` by default (the
                explorer asks for small batches, to show them as they come).
            observer (Optional[CompanyObserver]): Called after each batch is written, with its facts and the rows
                written (the explorer's progress).
            stop (Optional[threading.Event]): Once set, the crawler is asked to stop gracefully: the requests in
                flight end, the facts already read are written, and the next run resumes.
            refusals (Optional[Dict[CompanyFeed, str]]): Filled with why the source refused the crawl before its
                end, when it did.
            rejected (Optional[Dict[str, Set[str]]]): Filled with the records the crawl rejected as not the
                company's, by company.
            chronology (Optional[Chronology]): The names of the companies (the identity resolvers),
                `data/curated/chronology.json` by default.
            figures (Optional[ReportedFigures]): The researched figures (the figures check),
                `data/curated/figures.json` by default.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            CompaniesCatalogError: If a default catalogue cannot be loaded.

        Notes:
            The facts are never all held in memory: the patents of a company number hundreds of thousands.
        """
        crawler = self.factory.get_companies(
            feed, companies, concepts, markets, scope, known=known, queue=queue, chronology=chronology, figures=figures
        )
        size = batch_size if batch_size and batch_size > 0 else self.MARKETS_BATCH
        written = crawled = 0
        paused = False
        batch: List[Dict[str, JsonValue]] = []
        async for item in crawler.stream():
            batch.append(item)
            if len(batch) >= size:
                crawled += len(batch)
                rows = await sink(feed, batch)
                written += rows
                if observer is not None:
                    observer(feed, batch, rows)
                batch = []
            if stop is not None and stop.is_set() and not paused:
                self.logger.warning(
                    "Stop requested: the %s companies crawl ends after its requests in flight.", feed.value
                )
                crawler.pause()
                paused = True
        if batch:
            crawled += len(batch)
            rows = await sink(feed, batch)
            written += rows
            if observer is not None:
                observer(feed, batch, rows)
        if not crawled:
            self.logger.warning("The %s companies crawl produced no fact: its stored data are kept.", feed.value)
        if crawler.refusal is not None and refusals is not None:
            refusals[feed] = crawler.refusal
        if rejected is not None:
            for company, records in crawler.rejected.items():
                rejected.setdefault(company, set()).update(records)
        self.logger.info("%s companies crawl: %d facts, %d rows written.", feed.value, crawled, written)
        return written

    async def translate(self) -> Tuple[int, int]:
        """Translate every pending label, then categorize every unclassified item, with the language model.

        Returns:
            Tuple[int, int]: The number of labels translated, then of items categorized (0 and 0 without a model).

        Raises:
            LLMError: If the settings cannot be read or the budget is spent.
            StorageError: If the labels or the items cannot be read or written.
        """
        settings = LLMSettingsLoader(self.logger).load()
        self.llm_settings = settings
        translated = await LabelTranslator(self.storage, settings).run()
        classified = await ItemClassifier(self.storage, settings).run()
        self.logger.info("%d labels translated, %d items categorized by the language model.", translated, classified)
        return translated, classified

    async def correspond(self) -> int:
        """Match the catalogue services waiting in every category with the language model (equivalent services).

        Returns:
            int: The number of services filed under service concepts (0 without a model).

        Raises:
            LLMError: If the settings cannot be read or the budget is spent.
            StorageError: If the services cannot be read or written.
        """
        settings = self.llm_settings if self.llm_settings is not None else LLMSettingsLoader(self.logger).load()
        self.llm_settings = settings
        matched = await ServiceMatcher(self.storage, settings).run()
        self.logger.info("%d services filed under service concepts by the language model.", matched)
        return matched
