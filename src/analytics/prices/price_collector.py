from __future__ import annotations

# Standard Library Imports.
import uuid
from decimal import Decimal
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from analytics.prices.coverage_catalog_reader import CoverageCatalogReader
from analytics.prices.price_linker import PriceLinker
from crawler.cloud.base import PriceItem
from models.cloud.enums import CloudProvider, PriceFactKind, PriceModel, PriceSourceKind, PriceSourceStatus, PriceUnit
from models.cloud.prices.coverage.coverage_catalog import CoverageCatalog
from models.cloud.prices.facts.free_tier import FreeTier
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.stored.price_source import PriceSource
from storage.storage import Storage


class PriceCollector:
    """Write the prices a crawl streams: stage them by batches, then merge them at its end.

    Attributes:
        KIND_KEY (ClassVar[str]): The item key naming the kind of a fact (`fact`: a free offer has its own `kind`).
        MODEL_KEY (ClassVar[str]): The item key holding the validated model (the fields are validated otherwise).
        STATEMENT_FRAGMENT (ClassVar[str]): The fragment marking the source of a curated statement (its evidence
            page may be a crawled source too, whose prices a curation must not close).
        storage (Storage): The open storage.
        invalid (int): The facts left out as invalid in the crawls of this collector.
        linker (PriceLinker): Matches the priced services to the catalogue products.
        coverage (CoverageCatalogReader): Reads the curated price coverage of the providers.
        logger (Logger): The collector logger.

    Notes:
        - A crawl gets a run identifier (`start`): its batches are validated and copied into the staging tables
          (`write`), then merged at its end (`finish`), or discarded when it failed (`abort`).
        - At the end, only the rows of the sources the crawl read whole are closed when it no longer found them:
          the sources unchanged since their last read, or which failed, keep their prices. The prices are then
          linked to their catalogue products, the sources recorded for the next crawl, and the cached quotes
          cleared when a price changed.
    """

    KIND_KEY: ClassVar[str] = "fact"
    MODEL_KEY: ClassVar[str] = "model"
    STATEMENT_FRAGMENT: ClassVar[str] = "#price-coverage"

    def __init__(self, storage: Storage, logger: Optional[Logger] = None) -> None:
        """Initialize the collector.

        Args:
            storage (Storage): The open storage.
            logger (Optional[Logger]): The collector logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage
        self.invalid = 0
        self.linker = PriceLinker(self.logger)
        self.coverage = CoverageCatalogReader(logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _facts(self, items: Sequence[PriceItem]) -> Tuple[List[ServicePrice], List[FreeTier]]:
        """Sort the items of a batch by kind: their validated model, else their fields validated.

        Args:
            items (Sequence[PriceItem]): The items, each naming its kind.

        Returns:
            Tuple[List[ServicePrice], List[FreeTier]]: The prices, then the free offers (an invalid item is logged
                and left out).
        """
        prices: List[ServicePrice] = []
        tiers: List[FreeTier] = []
        for item in items:
            kind = item.get(self.KIND_KEY)
            model = item.get(self.MODEL_KEY)
            if isinstance(model, ServicePrice):
                prices.append(model)
                continue
            if isinstance(model, FreeTier):
                tiers.append(model)
                continue
            fields = {key: value for key, value in item.items() if key not in (self.KIND_KEY, self.MODEL_KEY)}
            try:
                if kind == PriceFactKind.PRICE:
                    prices.append(ServicePrice.model_validate(fields))
                elif kind == PriceFactKind.FREE_TIER:
                    tiers.append(FreeTier.model_validate(fields))
                else:
                    self.invalid += 1
                    self.logger.warning("A price item without a known kind is left out (%r).", kind)
            except ValidationError as e:
                self.invalid += 1
                self.logger.warning("Invalid %s left out: %s", kind, e.errors()[0]["msg"])
        self.logger.debug("Batch of %d items: %d prices, %d free offers.", len(items), len(prices), len(tiers))
        return prices, tiers

    def _statements(self, catalog: CoverageCatalog) -> List[ServicePrice]:
        """Turn the curated statements of a provider into prices: free at zero, the others unpriced with a reason.

        Args:
            catalog (CoverageCatalog): The curated coverage of the provider.

        Returns:
            List[ServicePrice]: One price per valid statement, its source being the page stating it.
        """
        prices: List[ServicePrice] = []
        for statement in catalog.statements:
            free = statement.model is PriceModel.FREE
            try:
                prices.append(
                    ServicePrice(
                        provider=catalog.provider,
                        sku_key=f"curated/{statement.product}",
                        service=statement.product,
                        region="global",
                        unit=PriceUnit.OTHER,
                        unit_raw=statement.model.value,
                        price=Decimal(0) if free else None,
                        currency=catalog.currency if free else None,
                        model=statement.model,
                        reason=None if free else statement.reason,
                        attributes={"statement": statement.reason},
                        source_url=f"{statement.source}{self.STATEMENT_FRAGMENT}",
                        source_kind=PriceSourceKind.DOCS,
                    )
                )
            except ValidationError as e:
                self.invalid += 1
                self.logger.warning("The coverage statement of %r is left out: %s", statement.product, e)
        self.logger.debug("%d coverage statements of %s.", len(prices), catalog.provider.value)
        return prices

    async def _drop_superseded(
        self, run_id: str, provider: CloudProvider, statements: Sequence[ServicePrice], crawled: Set[str]
    ) -> int:
        """Close the statements whose product got a crawled price since they were written (by the new links).

        Args:
            run_id (str): The run staging the statements kept, when some are dropped.
            provider (CloudProvider): The provider.
            statements (Sequence[ServicePrice]): Its curated statements.
            crawled (Set[str]): The products that had a crawled price when the statements were written (theirs
                were left out then).

        Returns:
            int: The statement rows closed.

        Raises:
            StorageError: If the storage cannot be read or written.
        """
        priced = await self.storage.prices.crawled_products(provider.value, self.STATEMENT_FRAGMENT)
        superseded = [statement for statement in statements if statement.service in priced - crawled]
        if not superseded:
            self.logger.debug("No %s statement is superseded by a crawled price.", provider.value)
            return 0
        await self.storage.prices.stage(
            run_id, [statement for statement in statements if statement.service not in priced]
        )
        closed, _ = await self.storage.prices.merge(
            run_id, provider.value, sorted({statement.source_url for statement in statements})
        )
        self.logger.info(
            "%d %s statements dropped: their product has a crawled price.", len(superseded), provider.value
        )
        return closed

    def _sources(self, provider: CloudProvider, reads: Dict[str, PriceSource], failures: Set[str]) -> List[PriceSource]:
        """List the sources to record: those read, and those which failed.

        Args:
            provider (CloudProvider): The provider.
            reads (Dict[str, PriceSource]): The sources read (whole or unchanged), by source.
            failures (Set[str]): The sources which failed.

        Returns:
            List[PriceSource]: The sources, a failed one with no version (it is read whole next time).
        """
        recorded = [source for url, source in reads.items() if url not in failures]
        recorded += [
            PriceSource(provider=provider, source_key=url, status=PriceSourceStatus.FAILED) for url in sorted(failures)
        ]
        if failures:
            self.logger.warning("%d %s price sources failed: read whole next time.", len(failures), provider.value)
        return recorded

    ############################
    # Publicly Exposed Methods #
    ############################

    def start(self, provider: CloudProvider) -> str:
        """Open a price crawl.

        Args:
            provider (CloudProvider): The provider.

        Returns:
            str: The run identifier of its staged rows.
        """
        run_id = f"{provider.value[:20]}-{uuid.uuid4().hex[:12]}"
        self.logger.info("Price crawl %s of %s opened.", run_id, provider.value)
        return run_id

    async def write(self, run_id: str, items: List[PriceItem]) -> int:
        """Validate and stage a batch of a crawl.

        Args:
            run_id (str): The crawl.
            items (List[PriceItem]): The prices and free offers, each naming its kind.

        Returns:
            int: The facts staged.

        Raises:
            StorageWriteError: If they cannot be staged.
        """
        prices, tiers = self._facts(items)
        staged = await self.storage.prices.stage(run_id, prices) if prices else 0
        staged += await self.storage.free_tiers.stage(run_id, tiers) if tiers else 0
        if len(items) and not staged:
            self.logger.warning("No valid fact in a batch of %d items of %s.", len(items), run_id)
        self.logger.debug("%d facts of %s staged.", staged, run_id)
        return staged

    async def finish(
        self,
        run_id: str,
        provider: CloudProvider,
        reads: Dict[str, PriceSource],
        failures: Set[str],
        prefixes: Sequence[str] = (),
    ) -> Tuple[int, int]:
        """Merge a crawl into the stored prices, link them, record the sources, clear the stale quotes.

        Args:
            run_id (str): The crawl.
            provider (CloudProvider): Its provider.
            reads (Dict[str, PriceSource]): The sources read (whole or unchanged), by source.
            failures (Set[str]): The sources which failed.
            prefixes (Sequence[str]): The brand prefixes of the provider, ignored when matching names.

        Returns:
            Tuple[int, int]: The rows closed, then the rows inserted (prices and free offers).

        Raises:
            StorageError: If the storage cannot be read or written.
        """
        whole = [
            url for url, source in reads.items() if source.status is PriceSourceStatus.FETCHED and url not in failures
        ]
        catalog = self.coverage.read(provider)
        statements = self._statements(catalog) if catalog is not None else []
        crawled = await self.storage.prices.crawled_products(provider.value, self.STATEMENT_FRAGMENT)
        if statements:
            await self.storage.prices.stage(
                run_id, [statement for statement in statements if statement.service not in crawled]
            )
            whole = sorted({*whole, *(statement.source_url for statement in statements)})
        closed, inserted = await self.storage.prices.merge(run_id, provider.value, whole)
        tier_closed, tier_inserted = await self.storage.free_tiers.merge(run_id, provider.value, whole)
        closed, inserted = closed + tier_closed, inserted + tier_inserted
        services = await self.storage.prices.unlinked_services(provider.value)
        if services:
            products = await self.storage.catalogues.live_pages(provider)
            if catalog is not None and catalog.row_links:
                await self.storage.prices.link_rows(provider.value, self.linker.row_links(products, catalog.row_links))
                services = await self.storage.prices.unlinked_services(provider.value)
            await self.storage.prices.link_products(
                provider.value, self.linker.exact_links(products, services, self.STATEMENT_FRAGMENT)
            )
            services = await self.storage.prices.unlinked_services(provider.value)
            links = self.linker.links(products, services, prefixes, catalog.links if catalog is not None else None)
            await self.storage.prices.link_products(provider.value, links)
        closed += await self._drop_superseded(f"{run_id}-drop", provider, statements, crawled)
        await self.storage.price_sources.upsert(self._sources(provider, reads, failures))
        if closed or inserted:
            await self.storage.price_quotes.clear()
        else:
            self.logger.debug("The prices of %s are unchanged: the quotes are kept.", provider.value)
        self.logger.info(
            "Price crawl %s of %s finished: %d rows closed, %d inserted, %d sources read whole, %d invalid.",
            run_id,
            provider.value,
            closed,
            inserted,
            len(whole),
            self.invalid,
        )
        return closed, inserted

    async def curate(self, provider: CloudProvider, prefixes: Sequence[str] = ()) -> Tuple[int, int, int]:
        """Apply the curated coverage of a provider without crawling: its statements, then all its links again.

        Args:
            provider (CloudProvider): The provider.
            prefixes (Sequence[str]): The brand prefixes of the provider, ignored when matching names.

        Returns:
            Tuple[int, int, int]: The statement rows closed, inserted, and the prices linked.

        Raises:
            StorageError: If the storage cannot be read or written.

        Notes:
            Only the statement sources are merged, so the crawled prices stay as they are. Every current price of
            the provider is then unlinked and linked again: the curated row links first (the most specific), then
            the services named exactly as a product, the curated links and the automatic matching, so that a
            corrected link replaces a former automatic one. A statement whose product has a crawled price is
            left out (or dropped once the new links give it one, its row closed): a crawled price wins over a
            statement.
        """
        catalog = self.coverage.read(provider)
        statements = self._statements(catalog) if catalog is not None else []
        sources = sorted({statement.source_url for statement in statements})
        closed = inserted = 0
        crawled = await self.storage.prices.crawled_products(provider.value, self.STATEMENT_FRAGMENT)
        if statements:
            run_id = self.start(provider)
            await self.storage.prices.stage(
                run_id, [statement for statement in statements if statement.service not in crawled]
            )
            closed, inserted = await self.storage.prices.merge(run_id, provider.value, sources)
        await self.storage.prices.unlink_products(provider.value)
        products = await self.storage.catalogues.live_pages(provider)
        linked = 0
        if catalog is not None and catalog.row_links:
            linked = await self.storage.prices.link_rows(
                provider.value, self.linker.row_links(products, catalog.row_links)
            )
        services = await self.storage.prices.unlinked_services(provider.value)
        linked += await self.storage.prices.link_products(
            provider.value, self.linker.exact_links(products, services, self.STATEMENT_FRAGMENT)
        )
        services = await self.storage.prices.unlinked_services(provider.value)
        links = self.linker.links(products, services, prefixes, catalog.links if catalog is not None else None)
        linked += await self.storage.prices.link_products(provider.value, links)
        if statements:
            closed += await self._drop_superseded(self.start(provider), provider, statements, crawled)
        if closed or inserted:
            await self.storage.price_quotes.clear()
        self.logger.info(
            "Coverage of %s curated: %d statement rows closed, %d inserted, %d prices linked.",
            provider.value,
            closed,
            inserted,
            linked,
        )
        return closed, inserted, linked

    async def abort(self, run_id: str) -> int:
        """Discard a failed crawl: its staged rows are removed, the stored prices left as they are.

        Args:
            run_id (str): The crawl.

        Returns:
            int: The staged rows removed.

        Raises:
            StorageWriteError: If they cannot be removed.
        """
        self.logger.error("Price crawl %s failed: its staged rows are discarded.", run_id)
        return await self.storage.prices.discard(run_id) + await self.storage.free_tiers.discard(run_id)
