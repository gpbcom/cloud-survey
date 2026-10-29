from __future__ import annotations

# Standard Library Imports.
import asyncio
import threading
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Union

from pydantic import JsonValue

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal

# First Party Imports.
from analytics.companies.companies_run import CompaniesRun
from analytics.companies.exception import CompaniesAnalyticsError
from analytics.markets.markets_collector import MarketsCollector
from crawler.enums import CrawlSource
from crawler.exception import CrawlerError, EmptyCrawlError
from crawler.runner import CatalogueRunner
from curated.exception import CuratedError
from models.cloud.enums import CloudProvider, Country
from models.cloud.products.product import CloudProduct
from models.cloud.software.marketplace_software import MarketplaceSoftware
from models.companies.enums import CompanyFeed
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from storage.exception import StorageError


class CrawlWorker(QObject):
    """Crawl one cloud provider catalogue or marketplace, those of a country, or every one, in a background `QThread`.

    Attributes:
        STREAM_BATCH (ClassVar[int]): The facts of a companies crawl written, then shown, at once.
        product_crawled (pyqtSignal): Emitted for each crawled product, with the provider and its product count.
        company_batch (pyqtSignal): Emitted for each batch of companies facts written, with the source, the facts
            (each naming its kind) and the rows written.
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
        company_feeds (List[CompanyFeed]): The companies sources crawled (`CrawlSource.COMPANIES`), every one when
            empty.
        companies (List[str]): The companies crawled (`CrawlSource.COMPANIES`), every one of the catalogue when
            empty.
        stop_event (threading.Event): Set by `request_stop`: the companies crawl ends gracefully.
        market_history (bool): Whether the Synergy market history follows (`CrawlSource.CATALOGUE`) or ends
            (`CrawlSource.STATISTICS`) the crawl, with its derivations: the `cloud` market shares and the provider
            metrics.
        counts (Dict[CloudProvider, int]): The products (or software) crawled so far, by cloud provider.

    Notes:
        With `market_history`, the statistics crawl is followed by the shares of the stored reports
        (`MarketsCollector.write_stored_shares`, no markets crawl needed) and `Storage.refresh_metrics`, so that
        `market_shares` and `provider_metrics` are filled at once. A statistics crawl bringing no report keeps the
        stored statistics, and the derivations still run on them.
    """

    STREAM_BATCH: ClassVar[int] = 25

    product_crawled = pyqtSignal(str, int)
    company_batch = pyqtSignal(str, list, int)
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
        company_feeds: Optional[Sequence[CompanyFeed]] = None,
        market_history: bool = False,
        companies: Optional[Sequence[str]] = None,
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
            company_feeds (Optional[Sequence[CompanyFeed]]): The companies sources crawled
                (`CrawlSource.COMPANIES`), every one by default.
            market_history (bool): Whether the Synergy market history and its derivations follow the catalogue
                crawls, or the statistics crawl.
            companies (Optional[Sequence[str]]): The companies crawled (`CrawlSource.COMPANIES`), every one when
                `None` or empty.
        """
        super().__init__()
        self.runner = runner
        self.provider = provider
        self.country = country
        self.source = source
        self.providers: Optional[List[CloudProvider]] = list(providers) if providers is not None else None
        self.feeds: List[MarketFeed] = list(feeds) if feeds else []
        self.company_feeds: List[CompanyFeed] = list(company_feeds) if company_feeds else []
        self.market_history = market_history
        self.companies: List[str] = list(companies) if companies else []
        self.stop_event = threading.Event()
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
            self.logger.debug("Crawling %d marketplaces.", len(targets))
            written = await self.runner.run_all_marketplaces(self._on_product, targets)
            failed = len(targets) - len(written)
            if failed:
                self.logger.warning("%d of %d marketplace crawls failed.", failed, len(targets))
            self.logger.info("%d marketplaces updated.", len(written))
            return f"{len(written)} marketplaces updated" + (f", {failed} failed (see the logs)" if failed else "")
        summary = await self.runner.run_marketplace(self.provider, self._on_product)
        self.logger.info("%d %s software written.", summary.found, self.provider.value)
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
            available = list(CloudProvider) if self.providers is None else self.providers
            targets = [provider for provider in available if self.country in (None, provider.country)]
            self.logger.debug("Crawling %d catalogues.", len(targets))
            chosen = self.country is not None or self.providers is not None
            written = await self.runner.run_all(self._on_product, targets if chosen else None)
            failed = len(targets) - len(written)
            if failed:
                self.logger.warning("%d of %d catalogue crawls failed.", failed, len(targets))
            self.logger.info("%d catalogues updated.", len(written))
            return f"{len(written)} catalogues updated" + (f", {failed} failed (see the logs)" if failed else "")
        summary = await self.runner.run(self.provider, self._on_product)
        self.logger.info("%d %s products written.", summary.found, self.provider.value)
        return (
            f"{summary.found} {self.provider.value} products written "
            f"({summary.added} added, {summary.updated} updated, {summary.deleted} deleted)"
        )

    async def _derive_market_history(self) -> str:
        """Write the cloud market shares of the stored Synergy reports, then compute the provider metrics again.

        Returns:
            str: The derivation summary.

        Raises:
            StorageError: If the storage cannot be read or written, or the curated catalogues were never seeded.
        """
        self.logger.debug("Deriving the cloud market shares and the provider metrics.")
        catalogs = self.runner.storage.catalogs
        collector = MarketsCollector(
            await catalogs.markets(), await catalogs.chronology(), self.runner.storage, self.logger
        )
        shares = await collector.write_stored_shares()
        metrics = await self.runner.storage.refresh_metrics(datetime.now(UTC))
        self.logger.info("%d market shares and %d provider metrics derived.", shares, metrics)
        return f"{shares} market shares and {metrics} provider metrics derived"

    async def _crawl_statistics(self) -> str:
        """Run the statistics crawl, followed by its derivations with `market_history`.

        Returns:
            str: The crawl summary.

        Raises:
            CrawlerError: If the crawl fails, or brings no report without `market_history`.
            StorageError: If the storage cannot be read or written.
        """
        self.logger.debug("Running a statistics crawl%s.", " with its derivations" if self.market_history else "")
        try:
            summary = await self.runner.run_statistics()
        except EmptyCrawlError:
            if not self.market_history:
                self.logger.error("The statistics crawl brought no report.")
                raise
            self.logger.warning("The statistics crawl brought no report: deriving from the stored statistics.")
            reports = "no new market report"
        else:
            self.logger.info("%d market reports written.", summary.found)
            reports = f"{summary.found} market reports written"
        if not self.market_history:
            return reports
        return f"{reports}, {await self._derive_market_history()}"

    async def _crawl_markets(self) -> str:
        """Run a markets crawl: each source picked, then the measures derived from several of them.

        Returns:
            str: The crawl summary.

        Raises:
            StorageError: If the curated catalogues cannot be read (a database never seeded).

        Notes:
            As `CRAWLER_SOURCE=markets`: the World Bank weights join StatCounter (the EU-27 estimate needs them), the
            facts are written by batches as they come, then the EU-27 is estimated, the dossier's manual shares and
            the Synergy cloud shares are written, and the providers' stock measures computed.
        """
        feeds = [feed for feed in self.runner.factory.MARKETS_MAP if not self.feeds or feed in self.feeds]
        if MarketFeed.STATCOUNTER in feeds and MarketFeed.WORLD_BANK not in feeds:
            self.logger.debug("Adding the World Bank weights, which the StatCounter estimate needs.")
            feeds.insert(0, MarketFeed.WORLD_BANK)
        self.logger.debug("Running a markets crawl of %s.", ", ".join(feed.value for feed in feeds))
        catalog = await self.runner.storage.catalogs.markets()
        collector = MarketsCollector(
            catalog, await self.runner.storage.catalogs.chronology(), self.runner.storage, self.logger
        )
        written = 0
        for feed in feeds:
            written += await self.runner.stream_markets(feed, collector.write, catalog, CrawlScope())
        written += await collector.finish(feeds)
        if not written:
            self.logger.warning("The markets crawl wrote no row.")
        self.logger.info("%d markets rows written.", written)
        return f"{written} markets rows written from {', '.join(feed.value for feed in feeds)}"

    def _on_company_batch(self, feed: CompanyFeed, items: List[Dict[str, JsonValue]], rows: int) -> None:
        """Hand a batch of companies facts written to the GUI.

        Args:
            feed (CompanyFeed): The source of the batch.
            items (List[Dict[str, JsonValue]]): The facts, each naming its kind.
            rows (int): The rows written.
        """
        self.company_batch.emit(feed.value, list(items), rows)

    async def _crawl_companies(self) -> str:
        """Run a companies crawl: each source picked, then the indicator series derived.

        Returns:
            str: The crawl summary.

        Raises:
            CrawlerError: If a catalogue cannot be loaded.
            StorageError: If the storage cannot be read or written.

        Notes:
            As `CRAWLER_SOURCE=companies`, for every company of the catalogue.
        """
        chosen = self.company_feeds
        every = [*self.runner.factory.COMPANIES_MAP, *CompaniesRun.LOCAL_FEEDS]
        feeds = [feed for feed in every if feed in chosen or (not chosen and feed not in CompaniesRun.ON_DEMAND_FEEDS)]
        self.logger.debug(
            "Running a companies crawl of %s for %s.",
            ", ".join(feed.value for feed in feeds),
            ", ".join(self.companies) or "every company",
        )
        run = CompaniesRun(self.runner, self.logger)
        written = await run.run(
            feeds,
            CrawlScope(companies=self.companies),
            observer=self._on_company_batch,
            batch_size=self.STREAM_BATCH,
            stop=self.stop_event,
        )
        self.logger.info("%d companies rows written.", written)
        summary = f"{written} companies rows written from {', '.join(feed.value for feed in feeds)}"
        if self.stop_event.is_set():
            return f"{summary} (stopped)"
        if run.refusals:
            self.logger.warning("Companies sources refused: %s.", ", ".join(feed.value for feed in run.refusals))
            return f"{summary}. {'. '.join(run.refusals.values())} (refused)"
        return summary

    async def _crawl(self) -> str:
        """Run the crawl, with the storage of the runner opened in the event loop of the crawl.

        Returns:
            str: The crawl summary.

        Notes:
            With `market_history`, a catalogue crawl is followed by the Synergy history and its derivations.
        """
        self.logger.debug("Opening the storage of the crawl %s.", self.runner.storage.url)
        async with self.runner.storage:
            match self.source:
                case CrawlSource.MARKETPLACE:
                    return await self._crawl_marketplaces()
                case CrawlSource.STATISTICS:
                    return await self._crawl_statistics()
                case CrawlSource.MARKETS:
                    return await self._crawl_markets()
                case CrawlSource.COMPANIES:
                    return await self._crawl_companies()
                case _ if self.market_history:
                    catalogues = await self._crawl_catalogues()
                    return f"{catalogues}, {await self._crawl_statistics()}"
                case _:
                    return await self._crawl_catalogues()

    ############################
    # Publicly Exposed Methods #
    ############################

    def request_stop(self) -> None:
        """Ask a companies crawl to end gracefully (the facts read are kept, the next run resumes)."""
        self.logger.info("Stop of the crawl requested.")
        self.stop_event.set()

    def run(self) -> None:
        """Run the crawl in its own event loop, then emit its outcome."""
        if self.source is CrawlSource.MARKETS:
            scope = ", ".join(feed.value for feed in self.feeds) or "every markets source"
        elif self.source is CrawlSource.COMPANIES:
            scope = ", ".join(feed.value for feed in self.company_feeds) or "every companies source"
        elif self.provider:
            scope = self.provider.value
        elif self.providers is not None:
            scope = ", ".join(provider.value for provider in self.providers)
        else:
            scope = self.country.value if self.country else "all"
        target = f"{scope} ({self.source.value}{', market history' if self.market_history else ''})"
        self.logger.info("Background crawl of %s started.", target)
        try:
            summary = asyncio.run(self._crawl())
        except (CrawlerError, CuratedError, CompaniesAnalyticsError, StorageError) as e:
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
