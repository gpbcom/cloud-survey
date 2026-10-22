from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Tuple, Type

# Third Party Imports.
from sqlalchemy import MetaData

# First Party Imports.
from storage.tables.base import Base
from storage.tables.correspondence.concept_member_row import ConceptMemberRow
from storage.tables.correspondence.correspondence_check_row import CorrespondenceCheckRow
from storage.tables.correspondence.service_concept_row import ServiceConceptRow
from storage.tables.datasets.crawl_row import CrawlRow
from storage.tables.datasets.dataset_row import DatasetRow
from storage.tables.datasets.market_report_row import MarketReportRow
from storage.tables.items.product_row import ProductRow
from storage.tables.items.product_version_row import ProductVersionRow
from storage.tables.items.software_row import SoftwareRow
from storage.tables.items.software_version_row import SoftwareVersionRow
from storage.tables.llm.llm_usage_row import LlmUsageRow
from storage.tables.metrics.provider_metric_row import ProviderMetricRow
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

    REVISION: ClassVar[str] = "0008"
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
    )

    def __init__(self) -> None:
        """Initialize the schema with the metadata of every table."""
        self.metadata: MetaData = Base.metadata
