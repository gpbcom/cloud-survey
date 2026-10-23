from __future__ import annotations

# Standard Library Imports.
import asyncio
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Union

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal

# First Party Imports.
from analytics.markets.markets_collector import MarketsCollector
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError
from crawler.markets.catalog_loader import MarketsCatalogLoader
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider, Country
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from storage.exception import StorageError


class CrawlWorker(QObject):
    """Crawl one cloud provider catalogue or marketplace, those of a country, or every one, in a background `QThread`.

    Attributes:
        product_crawled (pyqtSignal): Emitted for each crawled product, with the provider and its product count.
        succeeded (pyqtSignal): Emitted at the end of a successful crawl, with a summary.
        failed (pyqtSignal): Emitted when the crawl failed, with the reason.
        stopped (pyqtSignal): Emitted once the crawl is over, whatever its outcome.
        runner (CatalogueRunner): The runner crawling the catalogues into the store.
        provider (Optional[CloudProvider]): The crawled cloud provider, `None` for several of them.
        country (Optional[Country]): The country whose providers are crawled when no provider is given, `None` for
            every provider.
        source (CrawlSource): What is crawled: the catalogues, the marketplaces, the statistics or the markets.
        providers (Optional[List[CloudProvider]]): The crawled cloud providers when no provider is given, before the
            country filter, `None` for every one.
        feeds (List[MarketFeed]): The markets sources crawled (`CrawlSource.MARKETS`), every one when empty.
        counts (Dict[CloudProvider, int]): The products (or software) crawled so far, by cloud provider.
    """

    product_crawled = pyqtSignal(str, int)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(
        self,
        runner: CatalogueRunner,
        provider: Optional[CloudProvider],
        logger: Optional[Logger] = None,
        country: Optional[Country] = None,
        source: CrawlSource = CrawlSource.CATALOGUE,
        providers: Optional[Sequence[CloudProvider]] = None,
        feeds: Optional[Sequence[MarketFeed]] = None,
    ) -> None:
        """Initialize the worker.

        Args:
            runner (CatalogueRunner): The runner crawling the catalogues into the store.
            provider (Optional[CloudProvider]): The crawled cloud provider, `None` for several of them.
            logger (Optional[Logger]): The worker logger.
            country (Optional[Country]): The country whose providers are crawled when no provider is given.
            source (CrawlSource): What is crawled: the catalogues (default), the marketplaces or the statistics.
            providers (Optional[Sequence[CloudProvider]]): The crawled cloud providers when no provider is given,
                e.g. the marketplaces chosen in the marketplace menu, `None` for every one.
            feeds (Optional[Sequence[MarketFeed]]): The markets sources crawled (`CrawlSource.MARKETS`), every one
                by default.
        """
        super().__init__()
        self.runner = runner
        self.provider = provider
        self.country = country
        self.source = source
        self.providers: Optional[List[CloudProvider]] = list(providers) if providers is not None else None
        self.feeds: List[MarketFeed] = list(feeds) if feeds else []
        self.counts: Dict[CloudProvider, int] = {}
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "Crawl worker prepared: %s of %s.", source.value, provider.value if provider else "several providers"
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _on_product(self, provider: CloudProvider, product: Union[CloudProduct, MarketplaceSoftware]) -> None:
        """Count a crawled product (or software) and notify the GUI.

        Args:
            provider (CloudProvider): The cloud provider of the product.
            product (Union[CloudProduct, MarketplaceSoftware]): The crawled product or software.
        """
        self.counts[provider] = self.counts.get(provider, 0) + 1
        self.product_crawled.emit(provider.value, self.counts[provider])

    async def _crawl_marketplaces(self) -> str:
        """Run a marketplace crawl.

        Returns:
            str: The crawl summary.
        """
        self.logger.debug("Running a marketplace crawl.")
        if self.provider is None:
            available = self.runner.factory.marketplace_providers() if self.providers is None else self.providers
            targets = [provider for provider in available if self.country in (None, provider.country)]
            written = await self.runner.run_all_marketplaces(self._on_product, targets)
            failed = len(targets) - len(written)
            return f"{len(written)} marketplaces updated" + (f", {failed} failed (see the logs)" if failed else "")
        summary = await self.runner.run_marketplace(self.provider, self._on_product)
        return (
            f"{summary.found} {self.provider.value} software written "
            f"({summary.added} added, {summary.updated} updated, {summary.deleted} deleted)"
        )

    async def _crawl_catalogues(self) -> str:
        """Run a catalogue crawl.

        Returns:
            str: The crawl summary.
        """
        self.logger.debug("Running a catalogue crawl.")
        if self.provider is None:
            targets = [provider for provider in CloudProvider if self.country in (None, provider.country)]
            written = await self.runner.run_all(self._on_product, None if self.country is None else targets)
            failed = len(targets) - len(written)
            return f"{len(written)} catalogues updated" + (f", {failed} failed (see the logs)" if failed else "")
        summary = await self.runner.run(self.provider, self._on_product)
        return (
            f"{summary.found} {self.provider.value} products written "
            f"({summary.added} added, {summary.updated} updated, {summary.deleted} deleted)"
        )

    async def _crawl_markets(self) -> str:
        """Run a markets crawl: each source picked, then the measures derived from several of them.

        Returns:
            str: The crawl summary.

        Raises:
            CrawlerError: If the markets catalogue cannot be loaded.

        Notes:
            As `CRAWLER_SOURCE=markets`: the World Bank weights join StatCounter (the EU-27 estimate needs them), the
            facts are written by batches as they come, then the EU-27 is estimated, the dossier's manual shares and
            the Synergy cloud shares are written, and the providers' stock measures computed.
        """
        feeds = [feed for feed in self.runner.factory.MARKETS_MAP if not self.feeds or feed in self.feeds]
        if MarketFeed.STATCOUNTER in feeds and MarketFeed.WORLD_BANK not in feeds:
            feeds.insert(0, MarketFeed.WORLD_BANK)
        self.logger.debug("Running a markets crawl of %s.", ", ".join(feed.value for feed in feeds))
        loader = MarketsCatalogLoader(self.logger)
        catalog = loader.load()
        collector = MarketsCollector(catalog, loader.chronology(), self.runner.storage, self.logger)
        written = 0
        for feed in feeds:
            written += await self.runner.stream_markets(feed, collector.write, catalog, CrawlScope())
        written += await collector.finish(feeds)
        return f"{written} markets rows written from {', '.join(feed.value for feed in feeds)}"

    async def _crawl(self) -> str:
        """Run the crawl, with the storage of the runner opened in the event loop of the crawl.

        Returns:
            str: The crawl summary.
        """
        self.logger.debug("Opening the storage of the crawl %s.", self.runner.storage.url)
        async with self.runner.storage:
            match self.source:
                case CrawlSource.MARKETPLACE:
                    return await self._crawl_marketplaces()
                case CrawlSource.STATISTICS:
                    summary = await self.runner.run_statistics()
                    return f"{summary.found} market reports written"
                case CrawlSource.MARKETS:
                    return await self._crawl_markets()
                case _:
                    return await self._crawl_catalogues()

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self) -> None:
        """Run the crawl in its own event loop, then emit its outcome."""
        if self.source is CrawlSource.MARKETS:
            scope = ", ".join(feed.value for feed in self.feeds) or "every markets source"
        elif self.provider:
            scope = self.provider.value
        elif self.providers is not None:
            scope = ", ".join(provider.value for provider in self.providers)
        else:
            scope = self.country.value if self.country else "all"
        target = f"{scope} ({self.source.value})"
        self.logger.info("Background crawl of %s started.", target)
        try:
            summary = asyncio.run(self._crawl())
        except (CrawlerError, StorageError) as e:
            self.logger.error("Background crawl of %s failed: %s", target, e)
            self.failed.emit(str(e))
        except Exception as e:
            self.logger.exception("Background crawl of %s failed unexpectedly.", target)
            self.failed.emit(f"Unexpected error: {e!r}")
        else:
            self.logger.info("Background crawl of %s over: %s.", target, summary)
            self.succeeded.emit(summary)
        finally:
            self.stopped.emit()
