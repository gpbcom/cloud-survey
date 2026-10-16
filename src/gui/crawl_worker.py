from __future__ import annotations

# Standard Library Imports.
import asyncio
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Union

# Third Party Imports.
from PyQt6.QtCore import QObject, pyqtSignal

# First Party Imports.
from catalogue.exception import CatalogueStoreError
from crawler.exception import CrawlerError
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider, Country
from models.cloud.marketplace_software import MarketplaceSoftware
from models.cloud.product import CloudProduct


class CrawlWorker(QObject):
    """Crawl one cloud provider catalogue or marketplace, those of a country, or every one, in a background `QThread`.

    Attributes:
        CATALOGUE (ClassVar[str]): The catalogue source, the cloud products.
        MARKETPLACE (ClassVar[str]): The marketplace source, the marketplace software.
        STATISTICS (ClassVar[str]): The market statistics source (Synergy Research Group).
        product_crawled (pyqtSignal): Emitted for each crawled product, with the provider and its product count.
        succeeded (pyqtSignal): Emitted at the end of a successful crawl, with a summary.
        failed (pyqtSignal): Emitted when the crawl failed, with the reason.
        stopped (pyqtSignal): Emitted once the crawl is over, whatever its outcome.
        runner (CatalogueRunner): The runner crawling the catalogues into the store.
        provider (Optional[CloudProvider]): The crawled cloud provider, `None` for several of them.
        country (Optional[Country]): The country whose providers are crawled when no provider is given, `None` for
            every provider.
        source (str): What is crawled, `CATALOGUE` or `MARKETPLACE`.
        providers (Optional[List[CloudProvider]]): The crawled cloud providers when no provider is given, before the
            country filter, `None` for every one.
        counts (Dict[CloudProvider, int]): The products (or software) crawled so far, by cloud provider.
    """

    CATALOGUE: ClassVar[str] = "catalogue"
    MARKETPLACE: ClassVar[str] = "marketplace"
    STATISTICS: ClassVar[str] = "statistics"

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
        source: str = CATALOGUE,
        providers: Optional[Sequence[CloudProvider]] = None,
    ) -> None:
        """Initialize the worker.

        Args:
            runner (CatalogueRunner): The runner crawling the catalogues into the store.
            provider (Optional[CloudProvider]): The crawled cloud provider, `None` for several of them.
            logger (Optional[Logger]): The worker logger.
            country (Optional[Country]): The country whose providers are crawled when no provider is given.
            source (str): What is crawled, `CATALOGUE` (default) or `MARKETPLACE`.
            providers (Optional[Sequence[CloudProvider]]): The crawled cloud providers when no provider is given,
                e.g. the marketplaces chosen in the marketplace menu, `None` for every one.
        """
        super().__init__()
        self.runner = runner
        self.provider = provider
        self.country = country
        self.source = source
        self.providers: Optional[List[CloudProvider]] = list(providers) if providers is not None else None
        self.counts: Dict[CloudProvider, int] = {}
        self.logger = logger if logger else getLogger(__name__)

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
        if self.provider is None:
            available = self.runner.factory.marketplace_providers() if self.providers is None else self.providers
            targets = [provider for provider in available if self.country in (None, provider.country)]
            written = await self.runner.run_all_marketplaces(self._on_product, targets)
            failed = len(targets) - len(written)
            return f"{len(written)} marketplaces updated" + (f", {failed} failed (see the logs)" if failed else "")
        path = await self.runner.run_marketplace(self.provider, self._on_product)
        return f"{self.counts.get(self.provider, 0)} {self.provider.value} software written to {path}"

    async def _crawl(self) -> str:
        """Run the crawl.

        Returns:
            str: The crawl summary.
        """
        if self.source == self.MARKETPLACE:
            return await self._crawl_marketplaces()
        if self.source == self.STATISTICS:
            path = await self.runner.run_statistics()
            return f"market statistics written to {path}"
        if self.provider is None:
            targets = [provider for provider in CloudProvider if self.country in (None, provider.country)]
            written = await self.runner.run_all(self._on_product, None if self.country is None else targets)
            failed = len(targets) - len(written)
            return f"{len(written)} catalogues updated" + (f", {failed} failed (see the logs)" if failed else "")
        path = await self.runner.run(self.provider, self._on_product)
        return f"{self.counts.get(self.provider, 0)} {self.provider.value} products written to {path}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def run(self) -> None:
        """Run the crawl in its own event loop, then emit its outcome."""
        if self.provider:
            scope = self.provider.value
        elif self.providers is not None:
            scope = ", ".join(provider.value for provider in self.providers)
        else:
            scope = self.country.value if self.country else "all"
        target = f"{scope} ({self.source})"
        self.logger.info("Background crawl of %s started.", target)
        try:
            summary = asyncio.run(self._crawl())
        except (CrawlerError, CatalogueStoreError) as e:
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
