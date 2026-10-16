from __future__ import annotations

# Standard Library Imports.
import asyncio
import os
import time
from datetime import UTC, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import Awaitable, Callable, ClassVar, Dict, List, Optional, Tuple, Type, Union

# First Party Imports.
from catalogue.exception import CatalogueFileError, CatalogueStoreError
from catalogue.item_history import ItemHistory
from catalogue.marketplace_store import MarketplaceStore
from catalogue.statistics_store import StatisticsStore
from catalogue.store import CatalogueStore
from classifier.exception import ClassifierError
from classifier.software_classifier import SoftwareClassifier
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.factory import CrawlerFactory
from models.cloud.catalogue import CloudCatalogue
from models.cloud.enums import CloudProvider
from models.cloud.marketplace import CloudMarketplace
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics

ProductCallback = Callable[[CloudProvider, CloudProduct], None]
SoftwareCallback = Callable[[CloudProvider, MarketplaceSoftware], None]
ReportCallback = Callable[[MarketReport], None]


class CatalogueRunner:
    """Crawl the cloud providers catalogues and marketplaces and write them to their stores.

    Attributes:
        DEFAULT_CONCURRENCY (ClassVar[int]): The number of providers crawled at the same time by default.
        CONCURRENCY_VARIABLE (ClassVar[str]): The environment variable overriding the default concurrency.
        SAVE_INTERVAL (ClassVar[float]): How often, in seconds, a running crawl writes the items crawled so far by
            default.
        store (CatalogueStore): The store the catalogues are written to.
        marketplace_store (MarketplaceStore): The store the marketplaces are written to.
        statistics_store (StatisticsStore): The store the market statistics are written to.
        factory (CrawlerFactory): The factory building the crawlers.
        logger (Logger): The runner logger.
        classifier (Optional[SoftwareClassifier]): The classifier of the marketplace software, loaded once (at the
            first marketplace crawl) so that the rules cannot change during a run.
        concurrency (int): The number of providers crawled at the same time, at least 1.
        save_interval (float): How often, in seconds, a running crawl writes the items crawled so far.

    Notes:
        Several providers are crawled at the same time, at most `concurrency` of them: each website is still crawled
        one request at a time, with its own delay. Each crawl is dated from the previous file before being written
        (see `ItemHistory`). The files are written progressively: every `save_interval` seconds with the items crawled
        so far (`in_progress`, nothing deleted yet), then with every item once the crawl is over.
    """

    DEFAULT_CONCURRENCY: ClassVar[int] = 4
    CONCURRENCY_VARIABLE: ClassVar[str] = "CRAWLER_CONCURRENCY"
    SAVE_INTERVAL: ClassVar[float] = 10.0

    def __init__(
        self,
        store: Optional[CatalogueStore] = None,
        factory: Optional[CrawlerFactory] = None,
        logger: Optional[Logger] = None,
        marketplace_store: Optional[MarketplaceStore] = None,
        statistics_store: Optional[StatisticsStore] = None,
        concurrency: Optional[int] = None,
        save_interval: Optional[float] = None,
    ) -> None:
        """Initialize the runner.

        Args:
            store (Optional[CatalogueStore]): The store the catalogues are written to, `output/` by default.
            factory (Optional[CrawlerFactory]): The factory building the crawlers.
            logger (Optional[Logger]): The runner logger.
            marketplace_store (Optional[MarketplaceStore]): The store the marketplaces are written to,
                `<catalogue store folder>/marketplaces/` by default.
            statistics_store (Optional[StatisticsStore]): The store the market statistics are written to,
                `<catalogue store folder>/stats/` by default.
            concurrency (Optional[int]): The number of providers crawled at the same time, `CRAWLER_CONCURRENCY` (or
                4) by default.
            save_interval (Optional[float]): How often, in seconds, a running crawl writes the items crawled so far,
                every 10 s by default.
        """
        self.store = store if store else CatalogueStore()
        self.marketplace_store = (
            marketplace_store if marketplace_store else MarketplaceStore(self.store.output_dir / "marketplaces")
        )
        self.statistics_store = (
            statistics_store if statistics_store else StatisticsStore(self.store.output_dir / "stats")
        )
        self.factory = factory if factory else CrawlerFactory()
        self.logger = logger if logger else getLogger(__name__)
        self.classifier: Optional[SoftwareClassifier] = None
        if concurrency is None:
            raw = os.getenv(self.CONCURRENCY_VARIABLE, "").strip()
            valid = raw.isdigit() and int(raw) > 0
            if raw and not valid:
                self.logger.warning(
                    "%s=%r is not a positive number: %d providers are crawled at the same time.",
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
        try:
            return CloudProvider(target)
        except ValueError:
            return None

    def _previous_products(self, target: Union[CloudProvider, str]) -> Optional[List[CloudProduct]]:
        """Read the products of the previous catalogue file, the history of a new crawl.

        Args:
            target (Union[CloudProvider, str]): The crawled cloud provider.

        Returns:
            Optional[List[CloudProduct]]: The previous products, `None` without a usable previous file (logged).
        """
        provider = self._provider_of(target)
        if provider is None:
            return None
        try:
            previous = self.store.load(provider)
        except CatalogueFileError as e:
            self.logger.warning("The previous %s catalogue is unusable, its history is lost: %s", provider.value, e)
            return None
        return previous.products if previous else None

    def _previous_software(self, target: Union[CloudProvider, str]) -> Optional[List[MarketplaceSoftware]]:
        """Read the software of the previous marketplace file, the history of a new crawl.

        Args:
            target (Union[CloudProvider, str]): The crawled cloud provider.

        Returns:
            Optional[List[MarketplaceSoftware]]: The previous software, `None` without a usable previous file (logged).
        """
        provider = self._provider_of(target)
        if provider is None:
            return None
        try:
            previous = self.marketplace_store.load(provider)
        except CatalogueFileError as e:
            self.logger.warning("The previous %s marketplace is unusable, its history is lost: %s", provider.value, e)
            return None
        return previous.software if previous else None

    def _save_catalogue(
        self, catalogue: CloudCatalogue, previous: Optional[List[CloudProduct]], final: bool = True
    ) -> Path:
        """Date the products of a crawled catalogue from the previous ones, and write the catalogue file.

        Args:
            catalogue (CloudCatalogue): The crawled catalogue, complete or crawled so far.
            previous (Optional[List[CloudProduct]]): The products of the previous catalogue file, if any.
            final (bool): Whether the crawl is over (else the missing products are not deleted yet).

        Returns:
            Path: The written catalogue file.

        Raises:
            CatalogueWriteError: If the catalogue file cannot be written.
        """
        history = ItemHistory[CloudProduct](f"{catalogue.provider.value} catalogue")
        products = history.merge(previous, catalogue.products, catalogue.crawled_at, final)
        return self.store.save(catalogue.model_copy(update={"products": products, "in_progress": not final}))

    def _save_marketplace(
        self, marketplace: CloudMarketplace, previous: Optional[List[MarketplaceSoftware]], final: bool = True
    ) -> Path:
        """Date the software of a crawled marketplace from the previous ones, and write the marketplace file.

        Args:
            marketplace (CloudMarketplace): The crawled marketplace, complete or crawled so far.
            previous (Optional[List[MarketplaceSoftware]]): The software of the previous marketplace file, if any.
            final (bool): Whether the crawl is over (else the missing software is not deleted yet).

        Returns:
            Path: The written marketplace file.

        Raises:
            CatalogueWriteError: If the marketplace file cannot be written.
        """
        history = ItemHistory[MarketplaceSoftware](f"{marketplace.provider.value} marketplace")
        software = history.merge(previous, marketplace.software, marketplace.crawled_at, final)
        return self.marketplace_store.save(
            marketplace.model_copy(update={"software": software, "in_progress": not final})
        )

    def _checkpoint(self, save: Callable[[], Path], label: str) -> None:
        """Write the items crawled so far. A failing write is logged, the crawl goes on.

        Args:
            save (Callable[[], Path]): Writes the file.
            label (str): What is written, for the logs (e.g. `aws catalogue`).
        """
        try:
            path = save()
        except CatalogueStoreError as e:
            self.logger.warning("The %s crawled so far could not be written: %s", label, e)
            return
        self.logger.debug("The %s crawled so far was written to %s.", label, path)

    async def _run_parallel(
        self,
        targets: List[CloudProvider],
        job: Callable[[CloudProvider], Awaitable[Path]],
        errors: Tuple[Type[Exception], ...],
        noun: str,
    ) -> Dict[CloudProvider, Path]:
        """Run a crawl job for several providers, at most `concurrency` at the same time.

        Args:
            targets (List[CloudProvider]): The crawled providers.
            job (Callable[[CloudProvider], Awaitable[Path]]): The crawl of one provider, returning the written file.
            errors (Tuple[Type[Exception], ...]): The errors failing one provider only.
            noun (str): What is crawled, for the logs (e.g. `catalogue`).

        Returns:
            Dict[CloudProvider, Path]: The written files, by cloud provider, in the targets order.
        """
        semaphore = asyncio.Semaphore(self.concurrency)

        async def guarded(provider: CloudProvider) -> Optional[Path]:
            async with semaphore:
                try:
                    return await job(provider)
                except errors as e:
                    self.logger.error("The %s %s was not updated: %s", provider.value, noun, e)
                    return None

        self.logger.info("Crawling %d %ss, %d at the same time.", len(targets), noun, self.concurrency)
        paths = await asyncio.gather(*(guarded(provider) for provider in targets))
        written = {provider: path for provider, path in zip(targets, paths, strict=True) if path is not None}
        failed = len(targets) - len(written)
        log = self.logger.warning if failed else self.logger.info
        log("%d %ss written, %d failed.", len(written), noun, failed)
        return written

    ############################
    # Publicly Exposed Methods #
    ############################

    async def crawl(
        self,
        target: Union[CloudProvider, str],
        on_product: Optional[ProductCallback] = None,
        checkpoint: Optional[Callable[[CloudCatalogue], None]] = None,
    ) -> CloudCatalogue:
        """Crawl the catalogue of a cloud provider.

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.
            checkpoint (Optional[Callable[[CloudCatalogue], None]]): Called with the products crawled so far, at most
                every `save_interval` seconds.

        Returns:
            CloudCatalogue: The crawled catalogue, possibly empty.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
        """
        crawler = self.factory.get(target)
        provider = CloudProvider(target)
        self.logger.info("Crawling the %s catalogue.", provider.value)
        crawled_at, saved = datetime.now(UTC), time.monotonic()
        products: List[CloudProduct] = []
        async for item in crawler.stream():
            product = CloudProduct.model_validate(item)
            products.append(product)
            self.logger.debug("%s product %d received: %s", provider.value, len(products), product.name)
            if on_product:
                on_product(provider, product)
            if checkpoint and time.monotonic() - saved >= self.save_interval:
                checkpoint(CloudCatalogue(provider=provider, crawled_at=crawled_at, products=list(products)))
                saved = time.monotonic()
        self.logger.info("%s catalogue crawled: %d products.", provider.value, len(products))
        return CloudCatalogue(provider=provider, crawled_at=crawled_at, products=products)

    async def run(self, target: Union[CloudProvider, str], on_product: Optional[ProductCallback] = None) -> Path:
        """Crawl the catalogue of a cloud provider and write it to the store, progressively (see the class notes).

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.

        Returns:
            Path: The written catalogue file.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            EmptyCrawlError: If the crawl produced no product (the previous catalogue file is kept).
            CatalogueWriteError: If the catalogue file cannot be written.
        """
        previous = self._previous_products(target)
        catalogue = await self.crawl(
            target,
            on_product,
            lambda partial: self._checkpoint(
                lambda: self._save_catalogue(partial, previous, final=False), f"{partial.provider.value} catalogue"
            ),
        )
        if not catalogue.products:
            self.logger.error("The %s crawl produced no product: its file is kept.", catalogue.provider.value)
            raise EmptyCrawlError(catalogue.provider.value)
        return self._save_catalogue(catalogue, previous)

    async def run_all(
        self, on_product: Optional[ProductCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        """Crawl every cloud provider catalogue (or some of them), several at a time, and write them to the store.

        Args:
            on_product (Optional[ProductCallback]): Called with each product as soon as it is crawled.
            providers (Optional[List[CloudProvider]]): The crawled providers, every provider by default.

        Returns:
            Dict[CloudProvider, Path]: The written catalogue files, by cloud provider.
        """
        targets = list(CloudProvider) if providers is None else providers
        return await self._run_parallel(
            targets, lambda provider: self.run(provider, on_product), (CrawlerError, CatalogueStoreError), "catalogue"
        )

    async def crawl_marketplace(
        self,
        target: Union[CloudProvider, str],
        on_software: Optional[SoftwareCallback] = None,
        checkpoint: Optional[Callable[[CloudMarketplace], None]] = None,
    ) -> CloudMarketplace:
        """Crawl the marketplace of a cloud provider.

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.
            checkpoint (Optional[Callable[[CloudMarketplace], None]]): Called with the software crawled so far, at
                most every `save_interval` seconds.

        Returns:
            CloudMarketplace: The crawled marketplace, possibly empty.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            NoMarketplaceError: If the cloud provider has no marketplace.
        """
        crawler = self.factory.get_marketplace(target, self._classifier())
        provider = CloudProvider(target)
        self.logger.info("Crawling the %s marketplace.", provider.value)
        crawled_at, saved = datetime.now(UTC), time.monotonic()
        software: Dict[str, MarketplaceSoftware] = {}
        async for item in crawler.stream():
            listing = MarketplaceSoftware.model_validate(item)
            identity = listing.identity()
            is_new = identity not in software
            software[identity] = listing
            self.logger.debug("%s software %d received: %s", provider.value, len(software), listing.name)
            if is_new and on_software:
                on_software(provider, listing)
            if checkpoint and time.monotonic() - saved >= self.save_interval:
                checkpoint(CloudMarketplace(provider=provider, crawled_at=crawled_at, software=list(software.values())))
                saved = time.monotonic()
        self.logger.info("%s marketplace crawled: %d software.", provider.value, len(software))
        return CloudMarketplace(provider=provider, crawled_at=crawled_at, software=list(software.values()))

    async def run_marketplace(
        self, target: Union[CloudProvider, str], on_software: Optional[SoftwareCallback] = None
    ) -> Path:
        """Crawl the marketplace of a cloud provider and write it to the store, progressively (see the class notes).

        Args:
            target (Union[CloudProvider, str]): The cloud provider.
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.

        Returns:
            Path: The written marketplace file.

        Raises:
            UnknownCrawlerTargetError: If the target is not a supported cloud provider.
            NoMarketplaceError: If the cloud provider has no marketplace.
            EmptyCrawlError: If the crawl produced no software (the previous marketplace file is kept).
            CatalogueWriteError: If the marketplace file cannot be written.
        """
        previous = self._previous_software(target)
        marketplace = await self.crawl_marketplace(
            target,
            on_software,
            lambda partial: self._checkpoint(
                lambda: self._save_marketplace(partial, previous, final=False), f"{partial.provider.value} marketplace"
            ),
        )
        if not marketplace.software:
            self.logger.error(
                "The %s marketplace crawl produced no software: its file is kept.", marketplace.provider.value
            )
            raise EmptyCrawlError(marketplace.provider.value)
        return self._save_marketplace(marketplace, previous)

    async def run_all_marketplaces(
        self, on_software: Optional[SoftwareCallback] = None, providers: Optional[List[CloudProvider]] = None
    ) -> Dict[CloudProvider, Path]:
        """Crawl the marketplaces of every cloud provider having one (or of some of them), several at the same time.

        Args:
            on_software (Optional[SoftwareCallback]): Called with each new software as soon as it is crawled.
            providers (Optional[List[CloudProvider]]): The crawled providers, every provider having a marketplace by
                default.

        Returns:
            Dict[CloudProvider, Path]: The written marketplace files, by cloud provider.
        """
        targets = self.factory.marketplace_providers() if providers is None else providers
        return await self._run_parallel(
            targets,
            lambda provider: self.run_marketplace(provider, on_software),
            (CrawlerError, CatalogueStoreError, ClassifierError),
            "marketplace",
        )

    def reclassify_marketplaces(self) -> Dict[CloudProvider, Path]:
        """Classify the stored marketplace software again with the current rules, without crawling.

        Returns:
            Dict[CloudProvider, Path]: The rewritten marketplace files, by cloud provider.

        Raises:
            ClassificationRulesFileError: If the classification rules cannot be loaded.
        """
        rules = self._classifier()
        written: Dict[CloudProvider, Path] = {}
        for provider in CloudProvider:
            try:
                marketplace = self.marketplace_store.load(provider)
                if marketplace is None:
                    continue
                software = []
                for listing in marketplace.software:
                    categories, types = rules.classify(
                        listing.name, listing.description, listing.marketplace_categories, listing.delivery
                    )
                    software.append(listing.model_copy(update={"categories": categories, "types": types}))
                written[provider] = self.marketplace_store.save(marketplace.model_copy(update={"software": software}))
            except CatalogueStoreError as e:
                self.logger.error("The %s marketplace was not classified again: %s", provider.value, e)
        self.logger.info("%d marketplaces classified again.", len(written))
        return written

    async def run_statistics(self, name: str = "synergy", on_report: Optional[ReportCallback] = None) -> Path:
        """Crawl the market statistics of a source and write them to the statistics store.

        Args:
            name (str): The source name, e.g. `synergy`.
            on_report (Optional[ReportCallback]): Called with each new report as soon as it is crawled.

        Returns:
            Path: The written statistics file.

        Raises:
            UnknownCrawlerTargetError: If there is no crawler for the source.
            EmptyCrawlError: If the crawl produced no report (the previous statistics file is kept).
            CatalogueWriteError: If the statistics file cannot be written.
        """
        crawler = self.factory.get_statistics(name)
        self.logger.info("Crawling the %s market statistics.", name)
        reports: Dict[Tuple[str, str, str], MarketReport] = {}
        async for item in crawler.stream():
            report = MarketReport.model_validate(item)
            key = (report.period, report.region.value, report.segment.value)
            is_new = key not in reports
            reports[key] = report
            if is_new and on_report:
                on_report(report)
        if not reports:
            self.logger.error("The %s statistics crawl produced no report: its file is kept.", name)
            raise EmptyCrawlError(name)
        ordered = sorted(
            reports.values(), key=lambda report: (report.region.value, report.segment.value, report.sort_key())
        )
        statistics = MarketStatistics(source=crawler.source, crawled_at=datetime.now(UTC), reports=ordered)
        return self.statistics_store.save(name, statistics)
