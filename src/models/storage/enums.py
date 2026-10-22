from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class DatasetKind(StrEnum):
    """Enums representing the kinds of stored datasets: what a crawl writes.

    Attributes:
        CATALOGUE (str): The product catalogue of a cloud provider.
        MARKETPLACE (str): The software of the marketplace of a cloud provider.
        STATISTICS (str): The cloud market statistics of a source (e.g. Synergy Research Group).
    """

    CATALOGUE = "catalogue"
    MARKETPLACE = "marketplace"
    STATISTICS = "statistics"


@unique
class CrawlStatus(StrEnum):
    """Enums representing the outcome of a stored crawl.

    Attributes:
        RUNNING (str): The crawl is writing its items.
        SUCCEEDED (str): The crawl is over, the items missing from it are deleted.
        PARTIAL (str): The crawl is over but found too few items: nothing is deleted.
        EMPTY (str): The crawl found nothing: the stored items are unchanged.
        FAILED (str): The crawl stopped on an error: the items written so far are kept, nothing is deleted.
        ABANDONED (str): The crawl process disappeared while running (found when the next crawl starts).
        IMPORTED (str): The dataset was imported from a JSON file of the former file storage.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    EMPTY = "empty"
    FAILED = "failed"
    ABANDONED = "abandoned"
    IMPORTED = "imported"


@unique
class ItemSort(StrEnum):
    """Enums representing the orders of a page of stored items.

    Attributes:
        ID (str): The order the items were stored in.
        NAME (str): The item name, case-insensitive.
        PROVIDER (str): The cloud provider, then the name.
        PUBLISHER (str): The software publisher (the products have none), then the name.
        ADDED_AT (str): When the item was added, unknown dates last.
        UPDATED_AT (str): When the item was last updated, unknown dates last.
        DELETED_AT (str): When the item was deleted, the listed items last.
    """

    ID = "id"
    NAME = "name"
    PROVIDER = "provider"
    PUBLISHER = "publisher"
    ADDED_AT = "added_at"
    UPDATED_AT = "updated_at"
    DELETED_AT = "deleted_at"


@unique
class StorageTable(StrEnum):
    """Enums representing the tables of the storage.

    Attributes:
        CRAWLS (str): The crawls of the datasets.
        DATASETS (str): The state of the stored datasets.
        PRODUCTS (str): The products of the catalogues.
        PRODUCT_VERSIONS (str): The versions of the products.
        SOFTWARE (str): The software of the marketplaces.
        SOFTWARE_VERSIONS (str): The versions of the software.
        MARKET_REPORTS (str): The cloud market reports.
        TAXONOMY_NODES (str): The domains and categories of the unified taxonomy.
        SOURCE_LABELS (str): The categories of the providers (source labels), translated and de-duplicated.
        LABEL_LINKS (str): The taxonomy nodes each source label tells.
        LABEL_SIGHTINGS (str): Where each source label was seen (kind of dataset and provider).
        TAXONOMY_STATE (str): The revision of the taxonomy and the hash of its last seed.
        LLM_USAGE (str): The calls to the language model, with their tokens and cost.
        SERVICE_CONCEPTS (str): The service concepts shared by the providers (their equivalent services).
        CONCEPT_MEMBERS (str): The catalogue services filed under each service concept.
        CORRESPONDENCE_CHECKS (str): When the language model last matched each catalogue service, by category.
        PROVIDER_METRICS (str): The measures of the providers per quarter (the criteria of the driver analysis).
    """

    CRAWLS = "crawls"
    DATASETS = "datasets"
    PRODUCTS = "products"
    PRODUCT_VERSIONS = "product_versions"
    SOFTWARE = "software"
    SOFTWARE_VERSIONS = "software_versions"
    MARKET_REPORTS = "market_reports"
    TAXONOMY_NODES = "taxonomy_nodes"
    SOURCE_LABELS = "source_labels"
    LABEL_LINKS = "label_links"
    LABEL_SIGHTINGS = "label_sightings"
    TAXONOMY_STATE = "taxonomy_state"
    LLM_USAGE = "llm_usage"
    SERVICE_CONCEPTS = "service_concepts"
    CONCEPT_MEMBERS = "concept_members"
    CORRESPONDENCE_CHECKS = "correspondence_checks"
    PROVIDER_METRICS = "provider_metrics"


@unique
class ItemFilter(StrEnum):
    """Enums representing the filters of a page of stored items (see `ItemQuery`).

    Attributes:
        PROVIDERS (str): The items of some cloud providers only.
        LISTED (str): The items still listed by the websites only.
        SEARCH (str): The items containing a text.
        CATEGORIES (str): The software meant for some audiences only.
        DELIVERIES (str): The software delivered some ways only.
        NAME (str): The items whose name contains a text.
        DESCRIPTION (str): The items whose description contains a text.
        URL (str): The items whose page address contains a text.
        PUBLISHERS (str): The software of some publishers only.
        ADDED (str): The items added in a range, by a source, or with an unknown date.
        UPDATED (str): The items updated in a range, by a source, or with an unknown date.
        DELETED (str): The items deleted in a range.
        APPROXIMATE (str): The items with an approximate date, or only exact ones.
        CAVEATS (str): The items whose dates have some caveats.
        AUDIENCES (str): The items meant for some audiences only (developer tool only, end-user software only, both).
        SERVICE_CATEGORIES (str): The items filed under some categories or domains of the unified taxonomy only.
        SOURCE_LABELS (str): The items carrying some source labels (or their aliases) only.
    """

    PROVIDERS = "providers"
    LISTED = "listed"
    SEARCH = "search"
    CATEGORIES = "categories"
    DELIVERIES = "deliveries"
    NAME = "name"
    DESCRIPTION = "description"
    URL = "url"
    PUBLISHERS = "publishers"
    ADDED = "added"
    UPDATED = "updated"
    DELETED = "deleted"
    APPROXIMATE = "approximate"
    CAVEATS = "caveats"
    AUDIENCES = "audiences"
    SERVICE_CATEGORIES = "service-categories"
    SOURCE_LABELS = "source-labels"


@unique
class ItemField(StrEnum):
    """Enums representing the fields of the stored items which can be changed by hand (see `ItemRepository`).

    Attributes:
        NAME (str): The item name.
        DESCRIPTION (str): The item description.
        URL (str): The item page.
        PUBLISHER (str): The software publisher (software only).
        DELIVERY (str): How the software is delivered (software only).
        MARKETPLACE_CATEGORIES (str): The categories given by the marketplace (software only).
        CATEGORIES (str): Who the item is meant for (developer tool, end-user software or both).
        SERVICE_CATEGORIES (str): The categories of the unified taxonomy: changing them pins them.
    """

    NAME = "name"
    DESCRIPTION = "description"
    URL = "url"
    PUBLISHER = "publisher"
    DELIVERY = "delivery"
    MARKETPLACE_CATEGORIES = "marketplace_categories"
    CATEGORIES = "categories"
    SERVICE_CATEGORIES = "service_categories"


@unique
class ExportFormat(StrEnum):
    """Enums representing the file formats the stored items are exported to (the file extension).

    Attributes:
        CSV (str): Comma-separated values, one row per item (lists and objects as JSON texts).
        JSON (str): One JSON array of the items.
        JSON_LINES (str): One JSON object per line.
    """

    CSV = "csv"
    JSON = "json"
    JSON_LINES = "jsonl"


@unique
class SelectionAction(StrEnum):
    """Enums representing what is done with the items chosen by criteria (a bulk selection).

    Attributes:
        FILTER (str): The table shows the chosen items only.
        EXPORT (str): The chosen items are exported to a file.
        DELETE (str): The chosen items are deleted, once confirmed.
    """

    FILTER = "filter"
    EXPORT = "export"
    DELETE = "delete"


@unique
class DeletedState(StrEnum):
    """Enums representing which items are chosen according to their deletion from their website.

    Attributes:
        LISTED (str): The items still listed by their website only.
        ALL (str): The listed and the deleted items.
        DELETED (str): The deleted items only.
    """

    LISTED = "listed"
    ALL = "all"
    DELETED = "deleted"


@unique
class ExportColumn(StrEnum):
    """Enums representing the storage columns written before the item fields in the exported files.

    Attributes:
        ID (str): The storage identifier of the item.
        PROVIDER (str): The cloud provider of the item.
    """

    ID = "id"
    PROVIDER = "provider"
