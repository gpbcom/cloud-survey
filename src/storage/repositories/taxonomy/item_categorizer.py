from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import BigInteger, String, bindparam, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from models.classification.classification import Classification
from models.classification.classification_rules import ClassificationRules
from models.cloud.categorized_item import CategorizedItem
from models.storage.enums import DatasetKind
from models.taxonomy.enums import CategorySource
from models.taxonomy.labels.resolved_label import ResolvedLabel
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.mappers.item_mapper import ItemMapper, RowValue
from storage.repositories.taxonomy.label_registry import LabelRegistry
from storage.repositories.taxonomy.label_repository import LabelRepository
from storage.repositories.taxonomy.taxonomy_repository import TaxonomyRepository  # noqa: E501
from storage.repositories.taxonomy.taxonomy_seeder import TaxonomySeeder
from storage.tables.base import ITEM_REVISION
from taxonomy.exception import TaxonomyError
from taxonomy.label_normalizer import LabelNormalizer


class ItemCategorizer:
    """File the items (products and software) in the unified taxonomy when they are written.

    Attributes:
        RECOMPUTE_PAGE (ClassVar[int]): The number of items categorized again at a time.
        taxonomy (TaxonomyRepository): The stored taxonomy.
        labels (LabelRepository): The stored source labels.
        seeder (TaxonomySeeder): The seeder, applied before the first categorization when the seed changed.
        registry (LabelRegistry): The cache of the source labels.
        normalizer (LabelNormalizer): The normalizer of the label texts.
        rules (Optional[ClassificationRules]): The classification rules, read once.
        classifier (Optional[SoftwareClassifier]): The classifier over the stored taxonomy, rebuilt when it changes.
        revision (Optional[int]): The taxonomy revision of the classifier.
        seeded (bool): Whether the seed was checked by this process.
        logger (Logger): The categorizer logger.

    Notes:
        - The categories of an item come, in this order, from: a person (`categories_source` = `user`, kept as they
          are), the stored links of its source labels, the classification rules, its delivery method, the language
          model (kept while the content of the item does not change), else `other` (see
          `SoftwareClassifier.classify`).
        - The writes (crawls, imports, changes by hand) only fill the categorization columns: the audiences
          (`categories`) stay those of the crawlers. `recompute` sets them too, from the stored links of the labels.
        - One categorizer serves the repositories of a `Storage`: they share its caches.
    """

    RECOMPUTE_PAGE: ClassVar[int] = 2000

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the categorizer, without reading the database yet.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The categorizer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.taxonomy = TaxonomyRepository(database, self.logger)
        self.labels = LabelRepository(database, self.taxonomy, self.logger)
        self.seeder = TaxonomySeeder(database, self.taxonomy, self.labels)
        self.registry = LabelRegistry(self.labels, self.logger)
        self.normalizer = LabelNormalizer()
        self.rules: Optional[ClassificationRules] = None
        self.classifier: Optional[SoftwareClassifier] = None
        self.revision: Optional[int] = None
        self.seeded = False
        self.logger.debug("Item categorizer ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _resolved(self, item: CategorizedItem, labels: Dict[str, ResolvedLabel]) -> List[ResolvedLabel]:    # noqa: E501
        """Get the resolved source labels of an item.

        Args:
            item (CategorizedItem): The item.
            labels (Dict[str, ResolvedLabel]): The resolved labels, by key.

        Returns:
            List[ResolvedLabel]: Its labels, in its order, each once.
        """
        keys = dict.fromkeys(self.normalizer.key(text) for text in item.raw_labels())    # noqa: E501
        return [labels[key] for key in keys if key in labels]

    def _values(
        self,
        label_ids: List[int],
        categories: List[str],
        domains: List[str],
        source: CategorySource,
        fingerprint: Optional[bytes] = None,
    ) -> Dict[str, RowValue]:
        """Build the categorization columns of an item.

        Args:
            label_ids (List[int]): The identifiers of its source labels.
            categories (List[str]): Its categories.
            domains (List[str]): Its domains.
            source (CategorySource): What gave it its categories.
            fingerprint (Optional[bytes]): The content fingerprint the language model categorized, if it did.

        Returns:
            Dict[str, RowValue]: The `source_label_ids`, `service_categories`, `service_domains`, `categories_source`
                and `categories_fingerprint` columns.
        """
        ids: List[JsonValue] = [*label_ids]
        slugs: List[JsonValue] = [*categories]
        parents: List[JsonValue] = [*domains]
        return {
            "source_label_ids": ids,
            "service_categories": slugs,
            "service_domains": parents,
            "categories_source": source.value,
            "categories_fingerprint": fingerprint,
        }

    async def _update[T: CategorizedItem](
        self, connection: AsyncConnection, mapper: ItemMapper[T], rows: List[Dict[str, RowValue]]    # noqa: E501
    ) -> None:
        """Write the new categorization of stored items.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            mapper (ItemMapper[T]): The converter of the items to rows.
            rows (List[Dict[str, RowValue]]): The new values (`new_<column>`) of each item (`row_id`).
        """
        self.logger.debug("Writing the categorization of %d %s items.", len(rows), mapper.table.name)
        if not rows:
            return
        names = [name.removeprefix("new_") for name in rows[0] if name != "row_id"]    # noqa: E501
        await connection.execute(
            update(mapper.table)
            .where(mapper.table.c.id == bindparam("row_id")) 
            .values({**{name: bindparam(f"new_{name}") for name in names}, "revision": ITEM_REVISION.next_value()}),    # noqa: E501
            rows,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def current(self) -> SoftwareClassifier:
        """Get the classifier over the stored taxonomy.

        Returns:
            SoftwareClassifier: The classifier of the last `prepare`.

        Raises:
            StorageWriteError: If no categorization was prepared yet.
        """
        if self.classifier is None:
            self.logger.error("The items are categorized before the taxonomy is read.")
            raise StorageWriteError("categories of the items", "the taxonomy is not read yet")
        return self.classifier

    async def prepare(
        self,
        connection: AsyncConnection,
        items: Sequence[CategorizedItem],
        kind: DatasetKind,
        provider: Optional[str],
        seen: Optional[Set[int]] = None,
    ) -> Dict[str, ResolvedLabel]:
        """Prepare the categorization of items: seed when needed, refresh the caches, resolve and sight their labels.

        Args:
            connection (AsyncConnection): The connection, in a transaction (whose failure must `invalidate`).
            items (Sequence[CategorizedItem]): The items about to be written.
            kind (DatasetKind): Their kind of dataset.
            provider (Optional[str]): Their cloud provider, `None` not to sight their labels (changes by hand).
            seen (Optional[Set[int]]): The labels already sighted by the caller, updated (all are sighted without).

        Returns:
            Dict[str, ResolvedLabel]: Their resolved labels, by key.

        Raises:
            StorageWriteError: If the taxonomy cannot be seeded or read.
        """
        try:
            if not self.seeded:
                await self.seeder.apply(connection, self.rules)
                self.seeded = True
            revision, largest = await self.taxonomy.revision(connection)
            if revision is None:
                await self.seeder.apply(connection, self.rules, force=True)
                revision, largest = await self.taxonomy.revision(connection)
            classifier = self.classifier
            if classifier is None or revision != self.revision:
                classifier = SoftwareClassifier(rules=self.rules, taxonomy=await self.taxonomy.load(connection))
                self.classifier, self.rules, self.revision = classifier, classifier.rules, revision     # noqa: E501
        except TaxonomyError as e:
            self.logger.error("The taxonomy cannot be prepared: %s", e)
            raise StorageWriteError("taxonomy", str(e)) from e
        await self.registry.refresh(connection, revision or 0, largest)
        labels = await self.registry.resolve(
            connection,
            (text for item in items for text in item.raw_labels()),
            classifier,
        )
        ids = {label.id for label in labels.values()}
        fresh = sorted(ids - seen) if seen is not None else sorted(ids)
        if provider is not None:
            await self.labels.sight(connection, fresh, kind, provider)
            if seen is not None:
                seen.update(fresh)
        self.logger.debug("%d %s items prepared (%d labels).", len(items), kind.value, len(labels))    # noqa: E501
        return labels

    def invalidate(self) -> None:
        """Mark the caches stale after a failed transaction: the next `prepare` reads them again.

        Notes:
            The classifier and the labels are kept meanwhile: the concurrent crawls of the process keep using them.
        """
        self.logger.warning("The categorization caches are read again after a failed write.")
        self.registry.invalidate()
        self.revision = None
        self.seeded = False

    def classify(self, item: CategorizedItem, labels: Dict[str, ResolvedLabel]) -> Classification:    # noqa: E501
        """Classify an item with the stored links of its source labels.

        Args:
            item (CategorizedItem): The item.
            labels (Dict[str, ResolvedLabel]): The resolved labels (see `prepare`).

        Returns:
            Classification: Its audiences, categories and domains.
        """
        name, description = item.name_and_description()
        return self.current().classify(
            name,
            description,
            item.raw_labels(),
            item.delivery_method(),
            label_nodes=[label.nodes for label in self._resolved(item, labels)],    # noqa: E501
        )

    def categorize(
        self,
        item: CategorizedItem,
        labels: Dict[str, ResolvedLabel],
        stored: Optional[RowMapping],
        fingerprint: bytes,
    ) -> Tuple[Dict[str, RowValue], Optional[Classification]]:
        """Categorize an item about to be written.

        Args:
            item (CategorizedItem): The item.
            labels (Dict[str, ResolvedLabel]): The resolved labels (see `prepare`).
            stored (Optional[RowMapping]): Its stored row, `None` for a new item.
            fingerprint (bytes): The hash of its content fields.

        Returns:
            Tuple[Dict[str, RowValue], Optional[Classification]]: The categorization columns (see `_values`), then
                the classification computed for them, `None` when a person set its categories.
        """
        classifier = self.current()
        label_ids = [label.id for label in self._resolved(item, labels)]
        if item.categories_source is CategorySource.USER:
            domains = [domain for slug in item.service_categories if (domain := classifier.taxonomy.domain_of(slug))]    # noqa: E501
            values = self._values(
                label_ids,
                classifier.taxonomy.ordered(item.service_categories),
                classifier.taxonomy.ordered(domains),
                CategorySource.USER,
            )
            return values, None
        if stored is not None and stored["categories_source"] == CategorySource.USER.value:    # noqa: E501
            values = self._values( 
                label_ids, list(stored["service_categories"]), list(stored["service_domains"]), CategorySource.USER    # noqa: E501
            )
            return values, None
        classification = self.classify(item, labels)
        if (
            classification.categories == [SoftwareClassifier.OTHER]
            and stored is not None
            and stored["categories_source"] == CategorySource.LLM.value
            and stored["categories_fingerprint"] == fingerprint
        ):
            values = self._values(
                label_ids,
                list(stored["service_categories"]),
                list(stored["service_domains"]),
                CategorySource.LLM,
                fingerprint,
            )
            return values, classification
        values = self._values(label_ids, classification.categories, classification.domains, CategorySource.RULES)    # noqa: E501
        return values, classification

    def columns(
        self,
        item: CategorizedItem,
        labels: Dict[str, ResolvedLabel],
        stored: Optional[RowMapping],
        fingerprint: bytes,
    ) -> Dict[str, RowValue]:
        """Get the categorization columns of an item about to be written.

        Args:
            item (CategorizedItem): The item.
            labels (Dict[str, ResolvedLabel]): The resolved labels (see `prepare`).
            stored (Optional[RowMapping]): Its stored row, `None` for a new item.
            fingerprint (bytes): The hash of its content fields.

        Returns:
            Dict[str, RowValue]: The categorization columns (see `categorize`).
        """
        return self.categorize(item, labels, stored, fingerprint)[0]

    async def recompute[T: CategorizedItem](
        self,
        connection: AsyncConnection,
        mapper: ItemMapper[T],
        kind: DatasetKind,
        provider: str,
        label_ids: Optional[Sequence[int]] = None,
        node_slugs: Optional[Sequence[str]] = None,
    ) -> int:
        """Categorize the stored items of a provider again (all, or those of some labels or taxonomy nodes).

        Args:
            connection (AsyncConnection): The connection, in a transaction, holding the lock of the dataset.
            mapper (ItemMapper[T]): The converter of the items to rows.
            kind (DatasetKind): The kind of the items.
            provider (str): The cloud provider.
            label_ids (Optional[Sequence[int]]): Only the items carrying one of these labels.
            node_slugs (Optional[Sequence[str]]): Only the items filed under one of these categories or domains.

        Returns:
            int: The number of items whose categorization or audiences changed.

        Notes:
            The items are read by pages of `RECOMPUTE_PAGE`,
            by identifier: their source labels are resolved again
            (the labels never seen are stored), and only
            the rows which change are written.
        """
        table = mapper.table
        conditions = [table.c.provider == provider]
        if label_ids is not None:
            labelled = bindparam("label_ids", list(label_ids), type_=ARRAY(BigInteger))    # noqa: E501
            conditions.append(table.c.source_label_ids.overlap(labelled))
        if node_slugs is not None:
            slugs = bindparam("node_slugs", list(node_slugs), type_=ARRAY(String))     # noqa: E501
            conditions.append(or_(table.c.service_categories.overlap(slugs), table.c.service_domains.overlap(slugs)))    # noqa: E501
        changed = 0
        last = 0
        while True:
            page = select(table).where(*conditions, table.c.id > last).order_by(table.c.id).limit(self.RECOMPUTE_PAGE)
            rows = (await connection.execute(page)).mappings().all()
            if not rows:
                break
            items = [mapper.to_model(row) for row in rows]
            labels = await self.prepare(connection, items, kind, provider)
            updates: List[Dict[str, RowValue]] = []
            for row, item in zip(rows, items, strict=True):
                values, classification = self.categorize(item, labels, row, bytes(row["fingerprint"]))    # noqa: E501
                audiences: List[JsonValue] = [*row["categories"]]
                if classification is not None:
                    audiences = [audience.value for audience in classification.audiences]    # noqa: E501
                values["categories"] = audiences
                if mapper.differs(values, row):
                    updates.append({**{f"new_{name}": value for name, value in values.items()}, "row_id": row["id"]})
            await self._update(connection, mapper, updates)
            changed += len(updates)
            last = int(rows[-1]["id"])
        self.logger.info("%s %s categorized again: %d items changed.", provider, kind.value, changed)    # noqa: E501
        return changed
