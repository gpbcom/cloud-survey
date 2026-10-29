from __future__ import annotations

# Standard Library Imports.
import asyncio
from functools import partial
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.prices.price_collector import PriceCollector
from crawler.exception import CrawlerError
from crawler.runner import CatalogueRunner
from models.cloud.enums import CloudProvider
from models.cloud.prices.settings.prices_settings import PricesSettings
from storage.exception import StorageError


class PricesRun:
    """Run the price crawls of some providers, a few at a time, within the resource caps of the settings.

    Attributes:
        runner (CatalogueRunner): The runner streaming the crawls (its storage is open).
        settings (PricesSettings): The resource caps (the `prices` block of `conf/settings.yaml`).
        collector (PriceCollector): Stages and merges the prices.
        logger (Logger): The run logger.

    Notes:
        - The providers are read `max_concurrency` at a time.
          A provider whose crawl fails (a crawler, storage or
          network error) is reported and its staged rows discarded:
          its stored prices are left as they are, and the other providers go on.
        - The command line (`CRAWLER_SOURCE=prices`) and the explorer both run this.
    """

    def __init__(
        self, runner: CatalogueRunner, settings: Optional[PricesSettings] = None, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the run.

        Args:
            runner (CatalogueRunner): The runner streaming the crawls (its storage is open).
            settings (Optional[PricesSettings]): The resource caps, the defaults when `None`.
            logger (Optional[Logger]): The run logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.runner = runner
        self.settings = settings if settings else PricesSettings()
        self.collector = PriceCollector(runner.storage, self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _provider(self, provider: CloudProvider, gate: asyncio.Semaphore) -> Tuple[int, int]:
        """Crawl the prices of a provider and merge them, when the gate lets it in.

        Args:
            provider (CloudProvider): The provider.
            gate (asyncio.Semaphore): Lets `max_concurrency` providers in at a time.

        Returns:
            Tuple[int, int]: The rows closed, then the rows inserted (zero when the crawl failed).
        """
        async with gate:
            run_id = self.collector.start(provider)
            try:
                sources = await self.runner.storage.price_sources.versions(provider.value)
                pages = await self.runner.storage.catalogues.live_pages(provider)
                catalog = self.collector.coverage.read(provider)
                self.logger.debug(
                    "%d known %s price sources, %d live products.", len(sources), provider.value, len(pages)
                )
                staged, reads, failures = await self.runner.stream_prices(
                    provider,
                    partial(self.collector.write, run_id),
                    sources,
                    batch_size=self.settings.batch_rows,
                    max_memory_mb=self.settings.max_memory_mb,
                    delay_s=self.settings.request_delay_ms / 1000,
                    products={name: url for name, url in sorted(pages.values())},
                    pages=catalog.pages if catalog is not None else None,
                )
                prefixes = self.runner.factory.CRAWLER_MAP[provider].name_prefixes
                closed, inserted = await self.collector.finish(run_id, provider, reads, failures, prefixes)
            except (CrawlerError, StorageError, OSError) as e:
                self.logger.error("The %s price crawl failed: %s", provider.value, e)
                try:
                    await self.collector.abort(run_id)
                except StorageError as discard_error:
                    self.logger.error("The staged %s prices cannot be discarded: %s", provider.value, discard_error)
                return 0, 0
        self.logger.info("%s prices: %d staged, %d closed, %d inserted.", provider.value, staged, closed, inserted)
        return closed, inserted

    ############################
    # Publicly Exposed Methods #
    ############################

    async def run(self, providers: Sequence[CloudProvider]) -> Dict[CloudProvider, Tuple[int, int]]:
        """Crawl the prices of the providers and merge them.

        Args:
            providers (Sequence[CloudProvider]): The providers.

        Returns:
            Dict[CloudProvider, Tuple[int, int]]: The rows closed and inserted, by provider.
        """
        if not providers:
            self.logger.warning("No provider to crawl the prices of.")
            return {}
        gate = asyncio.Semaphore(self.settings.max_concurrency)
        self.logger.info(
            "Crawling the prices of %d providers, %d at a time.", len(providers), self.settings.max_concurrency
        )
        results: List[Tuple[int, int]] = await asyncio.gather(
            *(self._provider(provider, gate) for provider in providers)
        )
        changed = {provider: result for provider, result in zip(providers, results, strict=True)}
        unchanged = [provider.value for provider, (closed, inserted) in changed.items() if not closed and not inserted]
        if unchanged:
            self.logger.debug("Prices unchanged or not read: %s.", ", ".join(unchanged))
        return changed
