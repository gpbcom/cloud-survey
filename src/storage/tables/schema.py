from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Tuple, Type

# Third Party Imports.
from sqlalchemy import MetaData

# First Party Imports.
from storage.tables.base import Base
from storage.tables.companies.financials.company_financial_row import CompanyFinancialRow
from storage.tables.companies.financials.company_indicator_row import CompanyIndicatorRow
from storage.tables.companies.graph.assignee_profile_row import AssigneeProfileRow
from storage.tables.companies.graph.inventor_profile_row import InventorProfileRow
from storage.tables.companies.graph.patent_citation_row import PatentCitationRow
from storage.tables.companies.graph.patent_window_row import PatentWindowRow
from storage.tables.companies.papers.paper_author_row import PaperAuthorRow
from storage.tables.companies.papers.paper_company_row import PaperCompanyRow
from storage.tables.companies.papers.research_paper_row import ResearchPaperRow
from storage.tables.companies.papers.researcher_profile_row import ResearcherProfileRow
from storage.tables.companies.patents.patent_assignee_row import PatentAssigneeRow
from storage.tables.companies.patents.patent_classification_row import PatentClassificationRow
from storage.tables.companies.patents.patent_company_row import PatentCompanyRow
from storage.tables.companies.patents.patent_inventor_row import PatentInventorRow
from storage.tables.companies.patents.patent_row import PatentRow
from storage.tables.correspondence.concept_member_row import ConceptMemberRow
from storage.tables.correspondence.correspondence_check_row import CorrespondenceCheckRow
from storage.tables.correspondence.service_concept_row import ServiceConceptRow
from storage.tables.curated.companies.company_identifier_row import CompanyIdentifierRow
from storage.tables.curated.companies.company_profile_row import CompanyProfileRow
from storage.tables.curated.figures.reported_company_row import ReportedCompanyRow
from storage.tables.curated.figures.reported_event_row import ReportedEventRow
from storage.tables.curated.figures.reported_year_row import ReportedYearRow
from storage.tables.curated.launches.product_launch_row import ProductLaunchRow
from storage.tables.curated.records.curated_record_row import CuratedRecordRow
from storage.tables.curated.records.curated_state_row import CuratedStateRow
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.datasets.dataset_row import DatasetRow
from storage.tables.datasets.market_report_row import MarketReportRow
from storage.tables.items.product_row import ProductRow
from storage.tables.items.product_version_row import ProductVersionRow
from storage.tables.items.software_row import SoftwareRow
from storage.tables.items.software_version_row import SoftwareVersionRow
from storage.tables.llm.llm_usage_row import LlmUsageRow
from storage.tables.markets.fx_rate_row import FxRateRow
from storage.tables.markets.market_share_row import MarketShareRow
from storage.tables.markets.stock_price_row import StockPriceRow
from storage.tables.metrics.provider_metric_row import ProviderMetricRow
from storage.tables.prices.free_tier_row import FreeTierRow
from storage.tables.prices.price_quote_row import PriceQuoteRow
from storage.tables.prices.price_source_row import PriceSourceRow
from storage.tables.prices.service_price_row import ServicePriceRow
from storage.tables.prices.staging.free_tier_stage_row import FreeTierStageRow
from storage.tables.prices.staging.service_price_stage_row import ServicePriceStageRow
from storage.tables.prices.usage_profile_row import UsageProfileRow
from storage.tables.taxonomy.label_link_row import LabelLinkRow
from storage.tables.taxonomy.label_sighting_row import LabelSightingRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from storage.tables.taxonomy.taxonomy_node_row import TaxonomyNodeRow
from storage.tables.taxonomy.taxonomy_state_row import TaxonomyStateRow


class StorageSchema:
    """The complete schema of the storage: every table loaded in the metadata, for the migrations.

    Attributes:
        REVISION (ClassVar[str]): The migration revision the code expects (the head of `scripts/migrations`).
        TABLES (ClassVar[Tuple[Type[Base], ...]]): The tables of the storage.
        metadata (MetaData): The metadata of every table, index and sequence.
    """

    REVISION: ClassVar[str] = "0022"
    TABLES: ClassVar[Tuple[Type[Base], ...]] = (
        CrawlRow,
        DatasetRow,
        ProductRow,
        ProductVersionRow,
        SoftwareRow,
        SoftwareVersionRow,
        MarketReportRow,
        TaxonomyNodeRow,
        SourceLabelRow,
        LabelLinkRow,
        LabelSightingRow,
        TaxonomyStateRow,
        LlmUsageRow,
        ServiceConceptRow,
        ConceptMemberRow,
        CorrespondenceCheckRow,
        ProviderMetricRow,
        MarketShareRow,
        StockPriceRow,
        FxRateRow,
        CompanyFinancialRow,
        CompanyIndicatorRow,
        PatentRow,
        PatentCompanyRow,
        PatentInventorRow,
        PatentAssigneeRow,
        PatentClassificationRow,
        PatentCitationRow,
        PatentWindowRow,
        InventorProfileRow,
        AssigneeProfileRow,
        ResearchPaperRow,
        PaperCompanyRow,
        PaperAuthorRow,
        ResearcherProfileRow,
        CuratedRecordRow,
        CuratedStateRow,
        CompanyProfileRow,
        CompanyIdentifierRow,
        ReportedCompanyRow,
        ReportedYearRow,
        ReportedEventRow,
        ProductLaunchRow,
        ServicePriceRow,
        ServicePriceStageRow,
        FreeTierRow,
        FreeTierStageRow,
        PriceSourceRow,
        UsageProfileRow,
        PriceQuoteRow,
    )

    def __init__(self) -> None:
        """Initialize the schema with the metadata of every table."""
        self.metadata: MetaData = Base.metadata
