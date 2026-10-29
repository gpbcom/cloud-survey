from __future__ import annotations

from datetime import datetime

# Standard Library Imports.
from logging import Logger, getLogger
from types import TracebackType
from typing import Optional, Sequence, Type

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.configuration.storage.storage_settings import StorageSettings
from models.drivers.enums import MetricSource
from storage.engine.database import Database
from storage.engine.settings_reader import StorageSettingsReader
from storage.repositories.catalogue_repository import CatalogueRepository
from storage.repositories.companies.financial_repository import CompanyFinancialRepository
from storage.repositories.companies.indicator_repository import CompanyIndicatorRepository
from storage.repositories.companies.paper_repository import PaperRepository
from storage.repositories.companies.patent_profile_repository import PatentProfileRepository
from storage.repositories.companies.patent_repository import PatentRepository
from storage.repositories.correspondence.correspondence_repository import CorrespondenceRepository
from storage.repositories.curated.catalog_editor import CatalogEditor
from storage.repositories.curated.catalog_provider import CatalogProvider
from storage.repositories.curated.companies.company_identifier_repository import CompanyIdentifierRepository
from storage.repositories.curated.companies.company_profile_repository import CompanyProfileRepository
from storage.repositories.curated.curated_seeder import CuratedSeeder
from storage.repositories.curated.curated_state_repository import CuratedStateRepository
from storage.repositories.curated.figures.reported_company_repository import ReportedCompanyRepository
from storage.repositories.curated.figures.reported_event_repository import ReportedEventRepository
from storage.repositories.curated.figures.reported_year_repository import ReportedYearRepository
from storage.repositories.curated.launches.product_launch_repository import ProductLaunchRepository
from storage.repositories.curated.records.curated_record_repository import CuratedRecordRepository
from storage.repositories.dataset_repository import DatasetRepository
from storage.repositories.llm.llm_usage_repository import LlmUsageRepository
from storage.repositories.marketplace_repository import MarketplaceRepository
from storage.repositories.markets.fx_repository import FxRateRepository
from storage.repositories.markets.share_repository import MarketShareRepository
from storage.repositories.markets.stock_repository import StockPriceRepository
from storage.repositories.metrics.manual_metric_loader import ManualMetricLoader
from storage.repositories.metrics.metric_deriver import MetricDeriver
from storage.repositories.metrics.provider_metric_repository import ProviderMetricRepository
from storage.repositories.prices.free_tier_repository import FreeTierRepository
from storage.repositories.prices.profiles.price_quote_repository import PriceQuoteRepository
from storage.repositories.prices.profiles.usage_profile_repository import UsageProfileRepository
from storage.repositories.prices.service_price_repository import ServicePriceRepository
from storage.repositories.prices.sources.price_source_repository import PriceSourceRepository
from storage.repositories.statistics_repository import StatisticsRepository
from storage.repositories.taxonomy.item_categorizer import ItemCategorizer
from storage.repositories.trends.crawl_repository import CrawlRepository
from storage.repositories.trends.matrix_repository import MatrixRepository
from storage.repositories.trends.stored_items import StoredItems
from storage.repositories.trends.trend_repository import TrendRepository


class Storage:
    """The PostgreSQL storage of every crawled data: catalogues, marketplaces and market statistics.

    Attributes:
        settings (StorageSettings): The storage settings.
        database (Database): The database, open inside `async with storage`.
        categorizer (ItemCategorizer): The categorizer of the items in the unified taxonomy, shared by the catalogues
            and the marketplaces.
        taxonomy (TaxonomyRepository): The unified taxonomy.
        labels (LabelRepository): The source labels (the categories of the providers), translated and de-duplicated.
        seeder (TaxonomySeeder): The seeder of the taxonomy and of the labels.
        llm_usage (LlmUsageRepository): The language model calls and their cost.
        correspondences (CorrespondenceRepository): The equivalent services of the providers (service concepts).
        metrics (ProviderMetricRepository): The measures of the providers per quarter (the driver analysis).
        metric_deriver (MetricDeriver): Computes the measures of the providers from the crawled data.
        shares (MarketShareRepository): The market shares of the companies of the chronology.
        stocks (StockPriceRepository): The closing prices of their listings.
        fx (FxRateRepository): The exchange rates against the US dollar.
        financials (CompanyFinancialRepository): The statement lines of the chronology's companies.
        indicators (CompanyIndicatorRepository): The time series of their wealth and research indicators.
        patents (PatentRepository): Their patent publications, inventors, classes, citations and search windows.
        patent_profiles (PatentProfileRepository): The inventor and assignee profiles derived from the patents.
        papers (PaperRepository): Their researchers' papers and the researchers' profiles.
        datasets (DatasetRepository): The state of the stored datasets.
        catalogues (CatalogueRepository): The product catalogues.
        marketplaces (MarketplaceRepository): The marketplace software.
        statistics (StatisticsRepository): The market statistics.
        trends (TrendRepository): The chart trends of the catalogues and marketplaces.
        crawls (CrawlRepository): The history of the crawls.
        matrices (MatrixRepository): The matrices of the marketplace software.
        curated_state (CuratedStateRepository): The seed and the revision of each file of the curated bundle.
        curated_records (CuratedRecordRepository): The sections of the chronology and of the markets catalogue.
        company_profiles (CompanyProfileRepository): The companies crawled.
        company_identifiers (CompanyIdentifierRepository): Their identifiers at the sources.
        reported_companies (ReportedCompanyRepository): The companies whose figures were researched by hand.
        reported_years (ReportedYearRepository): The fiscal years researched by hand.
        reported_events (ReportedEventRepository): The dated figures researched by hand.
        launches (ProductLaunchRepository): The curated launches of the cloud products.
        curated_seeder (CuratedSeeder): Applies the curated bundle (`data/curated`).
        catalogs (CatalogProvider): The curated catalogues read from the database.
        catalog_editor (CatalogEditor): Changes the curated rows, each catalogue checked before it is written.
        prices (ServicePriceRepository): The prices of the cloud services, with their history.
        free_tiers (FreeTierRepository): The free offers of the cloud providers, with their history.
        price_sources (PriceSourceRepository): The price sources as last read (the incremental price crawls).
        usage_profiles (UsageProfileRepository): The workloads whose cost is compared across the providers.
        price_quotes (PriceQuoteRepository): The cached monthly costs of the workloads.
        logger (Logger): The storage logger.

    Notes:
        The storage is opened and closed in the event
        loop using it: `async with storage:`. It can be opened again
        afterwards, in another event loop (a GUI crawl runs each crawl in its own event loop).
    """

    def __init__(self, settings: Optional[StorageSettings] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the storage, without connecting yet.

        Args:
            settings (Optional[StorageSettings]): The storage settings,
                read from the environment by default.
            logger (Optional[Logger]): The storage logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.settings = settings if settings else StorageSettingsReader().read()
        self.database = Database(self.settings)
        self.categorizer = ItemCategorizer(self.database)
        self.taxonomy = self.categorizer.taxonomy
        self.labels = self.categorizer.labels
        self.seeder = self.categorizer.seeder
        self.llm_usage = LlmUsageRepository(self.database)
        self.correspondences = CorrespondenceRepository(self.database)
        self.datasets = DatasetRepository(self.database)
        self.catalogues = CatalogueRepository(self.database, categorizer=self.categorizer)
        self.marketplaces = MarketplaceRepository(self.database, categorizer=self.categorizer)
        self.statistics = StatisticsRepository(self.database)
        self.metrics = ProviderMetricRepository(self.database)
        self.metric_deriver = MetricDeriver(self.database, self.statistics)
        self.shares = MarketShareRepository(self.database)
        self.stocks = StockPriceRepository(self.database)
        self.fx = FxRateRepository(self.database)
        self.financials = CompanyFinancialRepository(self.database)
        self.indicators = CompanyIndicatorRepository(self.database)
        self.patents = PatentRepository(self.database)
        self.patent_profiles = PatentProfileRepository(self.database)
        self.papers = PaperRepository(self.database)
        items = StoredItems(self.catalogues, self.marketplaces)
        self.trends = TrendRepository(self.database, items)
        self.crawls = CrawlRepository(self.database)
        self.matrices = MatrixRepository(self.database, items)
        self.curated_state = CuratedStateRepository(self.database)
        self.curated_records = CuratedRecordRepository(self.database, self.curated_state)
        self.company_profiles = CompanyProfileRepository(self.database, self.curated_state)
        self.company_identifiers = CompanyIdentifierRepository(self.database, self.curated_state)
        self.reported_companies = ReportedCompanyRepository(self.database, self.curated_state)
        self.reported_years = ReportedYearRepository(self.database, self.curated_state)
        self.reported_events = ReportedEventRepository(self.database, self.curated_state)
        self.launches = ProductLaunchRepository(self.database, self.curated_state)
        curated = (
            self.curated_state,
            self.curated_records,
            self.company_profiles,
            self.company_identifiers,
            self.reported_companies,
            self.reported_years,
            self.reported_events,
            self.launches,
        )
        self.curated_seeder = CuratedSeeder(self.database, *curated)
        self.catalogs = CatalogProvider(*curated)
        self.catalog_editor = CatalogEditor(self.catalogs)
        self.prices = ServicePriceRepository(self.database)
        self.free_tiers = FreeTierRepository(self.database)
        self.price_sources = PriceSourceRepository(self.database)
        self.usage_profiles = UsageProfileRepository(self.database)
        self.price_quotes = PriceQuoteRepository(self.database)
        self.logger.debug(
            "Storage of %s created (pool of %d, batches of %d).",
            self.database.url,
            self.settings.pool_size,
            self.settings.batch_size,
        )

    async def __aenter__(self) -> Storage:
        """Open the storage.

        Returns:
            Storage: The open storage.

        Raises:
            StorageConnectionError: If the database cannot be reached.
            StorageSchemaError: If the database schema is not the one the code expects.
        """
        self.logger.debug("Opening the storage %s.", self.database.url)
        await self.database.open()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Close the storage.

        Args:
            exc_type (Optional[Type[BaseException]]): The type of the error leaving the block, if any.
            exc (Optional[BaseException]): The error leaving the block, if any.
            traceback (Optional[TracebackType]): Its traceback.
        """
        if exc is not None:
            self.logger.warning("Closing the storage %s after an error: %s", self.database.url, exc)
        else:
            self.logger.debug("Closing the storage %s.", self.database.url)
        await self.database.close()

    ############################
    # Publicly Exposed Methods #
    ############################

    @property
    def url(self) -> str:
        """Get the database URL, without its password.

        Returns:
            str: The URL, for the logs and messages.
        """
        return self.database.url

    async def recategorize(
        self,
        label_ids: Optional[Sequence[int]] = None,
        node_slugs: Optional[Sequence[str]] = None,
    ) -> int:
        """Categorize the stored products and software again (all, or those of some labels or taxonomy nodes).

        Args:
            label_ids (Optional[Sequence[int]]): Only the items carrying one of these labels.
            node_slugs (Optional[Sequence[str]]): Only the items filed under one of these categories or domains.

        Returns:
            int: The number of items whose categorization changed (the datasets being crawled are skipped, and
                categorized again once their crawl is over).

        Raises:
            StorageWriteError: If the items cannot be categorized again.
        """
        if (label_ids is not None and not label_ids) or (node_slugs is not None and not node_slugs):
            self.logger.debug("Nothing to categorize again.")
            return 0
        changed = 0
        for repository in (self.catalogues, self.marketplaces):
            for provider in CloudProvider:
                changed += await repository.recategorize(provider, label_ids, node_slugs) or 0
        self.logger.info("%d items categorized again.", changed)
        return changed

    async def refresh_metrics(self, now: datetime) -> int:
        """Compute the measures of the providers again, and read the manual ones again.

        Args:
            now (datetime): When the snapshot is taken
                (its quarter receives the catalogue and marketplace measures).

        Returns:
            int: The number of measures written.

        Raises:
            StorageReadError: If the crawled data cannot be read.
            StorageWriteError: If the measures cannot be written.
            StorageImportError: If the manual measures are invalid.
        """
        derived = await self.metric_deriver.derive(now)
        written = 0
        for source in (MetricSource.DERIVED, MetricSource.SYNERGY):
            written += await self.metrics.replace_source(source, derived)
        written += await self.metrics.replace_source(MetricSource.MANUAL, ManualMetricLoader().load())
        self.logger.info("%d provider metrics refreshed.", written)
        return written
