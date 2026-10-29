from __future__ import annotations

# Standard Library Imports.
from hashlib import sha256
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third Party Imports.
from sqlalchemy import BigInteger, Table, and_, any_, bindparam, case, delete, func, select, text, tuple_, update  # noqa: E501
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from conf import CLASSIFICATION_RULES_PATH, LABEL_SEED_PATH, TAXONOMY_SEED_PATH
from models.classification.classification_rules import ClassificationRules
from models.taxonomy.enums import LabelStatus, Language, LinkSource, NameSource, NodeOrigin    # noqa: E501
from models.taxonomy.nodes.taxonomy import Taxonomy
from models.taxonomy.seed.label_seed import LabelSeed
from storage.engine.database import Database
from storage.exception import StorageWriteError
from storage.repositories.taxonomy.label_repository import LabelRepository
from storage.repositories.taxonomy.taxonomy_repository import TaxonomyRepository    # noqa: E501
from storage.tables.base import Base
from storage.tables.taxonomy.label_link_row import LabelLinkRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from storage.tables.taxonomy.taxonomy_node_row import TaxonomyNodeRow
from storage.tables.taxonomy.taxonomy_state_row import TaxonomyStateRow
from taxonomy.label_normalizer import LabelNormalizer
from taxonomy.seed_loader import TaxonomySeedLoader

type SeedValue = Optional[Union[str, int, bool, List[str]]]


class TaxonomySeeder:
    """Apply the seed files of the project (taxonomy, label seed, classification rules) to the SQL taxonomy.

    Attributes:
        LOCK_KEYS (ClassVar[Tuple[int, int]]): The keys of the advisory lock of the seed (after the dataset locks).
        database (Database): The open database.
        taxonomy (TaxonomyRepository): The stored taxonomy.
        labels (LabelRepository): The stored source labels.
        loader (TaxonomySeedLoader): The reader of the seed files.
        normalizer (LabelNormalizer): The normalizer of the label texts.
        paths (Tuple[Path, ...]): The seed files: their content hash tells whether the seed changed.
        logger (Logger): The seeder logger.

    Notes:
        - The seed is idempotent and never overwrites a person's edits: the nodes are updated while not edited, the
          English names and statuses while their source is not `user`, the links while not made or excluded by a
          person, and the merges while not made by a person. A seed node missing from the file is hidden, never
          deleted (the items store its slug).
        - It runs under a transaction advisory lock: concurrent processes seed once. It runs after `migrate-db
          upgrade`, on `migrate-db seed`, on `CRAWLER_SOURCE=reclassify`, and lazily before the first categorization
          when the seed files changed.
        - After the labels, the rule links of every label are recomputed with the rules of the seed.
    """

    LOCK_KEYS: ClassVar[Tuple[int, int]] = (4, 0)

    def __init__(
        self,
        database: Database,
        taxonomy: TaxonomyRepository,
        labels: LabelRepository,
        paths: Tuple[Path, ...] = (TAXONOMY_SEED_PATH, LABEL_SEED_PATH, CLASSIFICATION_RULES_PATH),    # noqa: E501
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the seeder.

        Args:
            database (Database): The open database.
            taxonomy (TaxonomyRepository): The stored taxonomy.
            labels (LabelRepository): The stored source labels.
            paths (Tuple[Path, ...]): The taxonomy seed, the label seed and the classification rules.
            logger (Optional[Logger]): The seeder logger.
        """
        self.database = database
        self.taxonomy = taxonomy
        self.labels = labels
        self.paths = paths
        self.logger = logger if logger else getLogger(__name__)
        self.loader = TaxonomySeedLoader(self.logger)
        self.normalizer = LabelNormalizer()
        self.logger.debug("Taxonomy seeder ready (%s).", ", ".join(path.name for path in paths))    # noqa: E501

    ############################
    # Internal Helpers Methods #
    ############################

    def _table(self, name: str) -> Table:
        """Get a table of the taxonomy.

        Args:
            name (str): The table name.

        Returns:
            Table: The table.
        """
        return Base.metadata.tables[name]

    def _label_row(self, label_text: str, name_en: Optional[str], noise: bool) -> Dict[str, SeedValue]:    # noqa: E501
        """Build the row of a seed label.

        Args:
            label_text (str): The label text.
            name_en (Optional[str]): Its English name from the seed, `None` to keep the text of an English label.
            noise (bool): Whether the label is not a category.

        Returns:
            Dict[str, SeedValue]: The `source_labels` values.
        """
        language = self.normalizer.language(label_text)
        english = name_en or (label_text if language is Language.ENGLISH else None)    # noqa: E501
        status = LabelStatus.NOISE if noise else LabelStatus.TRANSLATED if english else LabelStatus.PENDING    # noqa: E501
        if name_en:
            source: Optional[str] = NameSource.SEED.value
        else:
            source = NameSource.IDENTITY.value if english else None
        return {
            "key": self.normalizer.key(label_text),
            "text": label_text,
            "language": language.value,
            "name_en": english,
            "name_key": self.normalizer.key(english) if english else None,
            "name_source": source,
            "status": status.value,
            "status_source": NameSource.SEED.value,
        }

    async def _seed_nodes(self, connection: AsyncConnection, seed: Taxonomy) -> None:    # noqa: E501
        """Insert or update the seed nodes, domains first, and hide the seed nodes the file no longer holds.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            seed (Taxonomy): The taxonomy of the seed file.
        """
        nodes = self._table(TaxonomyNodeRow.__tablename__)
        self.logger.debug("Seeding %d taxonomy nodes.", len(seed.nodes))
        rows = [
            {
                "slug": node.slug,
                "parent_slug": node.parent_slug,
                "name_en": node.name_en,
                "name_ru": node.name_ru,
                "name_zh": node.name_zh,
                "description_en": node.description_en,
                "position": node.position,
                "audiences": [audience.value for audience in node.audiences],
                "umbrella": node.umbrella,
                "origin": NodeOrigin.SEED.value,
                "hidden": node.hidden,
            }
            for node in seed.nodes
        ]
        for level in ([row for row in rows if row["parent_slug"] is None], [row for row in rows if row["parent_slug"]]):    # noqa: E501
            if not level:
                continue
            statement = upsert(nodes).values(level)
            excluded = statement.excluded
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[nodes.c.slug],
                    set_={
                        "parent_slug": excluded.parent_slug,
                        "name_en": excluded.name_en,
                        "name_ru": excluded.name_ru,
                        "name_zh": excluded.name_zh,
                        "description_en": excluded.description_en,
                        "position": excluded.position,
                        "audiences": excluded.audiences,
                        "umbrella": excluded.umbrella,
                        "hidden": excluded.hidden,
                        "updated_at": func.now(),
                    },
                    where=nodes.c.edited.is_(False),
                )
            )
        slugs = [node.slug for node in seed.nodes]
        hidden = await connection.execute(
            update(nodes)
            .where(
                nodes.c.origin == NodeOrigin.SEED.value,
                nodes.c.edited.is_(False),
                nodes.c.hidden.is_(False),
                nodes.c.slug.not_in(slugs),
            )
            .values(hidden=True, updated_at=func.now())
        )
        if hidden.rowcount:
            self.logger.warning("%d seed nodes missing from the seed file are hidden.", hidden.rowcount)

    async def _upsert_labels(self, connection: AsyncConnection, rows: List[Dict[str, SeedValue]]) -> Dict[str, int]:    # noqa: E501
        """Insert or update seed labels, keeping the values a person set.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            rows (List[Dict[str, SeedValue]]): The label rows, one per key.

        Returns:
            Dict[str, int]: The identifier of each label, by key.
        """
        if not rows:
            self.logger.debug("No seed label to write.")
            return {}
        labels = self._table(SourceLabelRow.__tablename__)
        statement = upsert(labels).values(sorted(rows, key=lambda row: str(row["key"])))
        excluded = statement.excluded
        named_by_user = labels.c.name_source == NameSource.USER.value
        status_by_user = labels.c.status_source == NameSource.USER.value
        result = await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[labels.c.key],
                set_={
                    "name_en": case((named_by_user, labels.c.name_en), else_=excluded.name_en),
                    "name_key": case((named_by_user, labels.c.name_key), else_=excluded.name_key),
                    "name_source": case((named_by_user, labels.c.name_source), else_=excluded.name_source),
                    "status": case((status_by_user, labels.c.status), else_=excluded.status),
                    "status_source": case((status_by_user, labels.c.status_source), else_=excluded.status_source),
                    "translated_at": func.now(),
                },
            ).returning(labels.c.id, labels.c.key)
        )
        written = {str(row[1]): int(row[0]) for row in result.all()}
        self.logger.debug("%d seed labels written.", len(written))
        return written

    async def _seed_merges(self, connection: AsyncConnection, seed: LabelSeed, ids: Dict[str, int]) -> None:    # noqa: E501
        """Merge the seed labels into the labels they are the same as, and undo the merges the seed no longer makes.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            seed (LabelSeed): The label seed.
            ids (Dict[str, int]): The identifier of each seed label, by key.
        """
        labels = self._table(SourceLabelRow.__tablename__)
        merges = sorted(
            {
                (ids[source], ids[target])
                for label in seed.labels
                if label.same_as
                and (source := self.normalizer.key(label.text)) in ids
                and (target := self.normalizer.key(label.same_as)) in ids
                and source != target
            }
        )
        self.logger.debug("Applying %d seed merges.", len(merges))
        merged = [source for source, _ in merges]
        not_by_user = labels.c.canonical_source.is_distinct_from(NameSource.USER.value)   # noqa: E501
        await connection.execute(
            update(labels)
            .where(
                labels.c.canonical_source == NameSource.SEED.value,
                ~(labels.c.id == any_(bindparam("merged", merged, type_=ARRAY(BigInteger)))),    # noqa: E501
            )
            .values(canonical_id=None, canonical_source=None)
        )
        if merges:
            await connection.execute(
                update(labels)
                .where(labels.c.id == bindparam("source_id"), not_by_user)
                .values(canonical_id=bindparam("target_id"), canonical_source=NameSource.SEED.value),    # noqa: E501
                [{"source_id": source, "target_id": target} for source, target in merges],    # noqa: E501
            )

    async def _seed_labels(self, connection: AsyncConnection, seed: LabelSeed, taxonomy: Taxonomy) -> None:    # noqa: E501
        """Apply the label seed: English names, statuses, links and merges.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            seed (LabelSeed): The label seed.
            taxonomy (Taxonomy): The taxonomy of the seed, which the links must name.
        """
        self.logger.debug("Seeding %d labels.", len(seed.labels))
        rows: Dict[str, Dict[str, SeedValue]] = {}
        for label in seed.labels:
            row = self._label_row(label.text, label.en, label.noise)
            if not row["key"]:
                self.logger.warning("The seed label %r has no letter: it is skipped.", label.text)
                continue
            if row["key"] in rows:
                self.logger.warning("The seed label %r repeats another one: the last one is kept.", label.text)
            rows[str(row["key"])] = row
        for label in seed.labels:
            if label.same_as and self.normalizer.key(label.same_as) not in rows:    # noqa: E501
                target = self._label_row(label.same_as, None, False)
                if target["key"]:
                    rows[str(target["key"])] = target
        ids = await self._upsert_labels(connection, list(rows.values()))
        links = self._table(LabelLinkRow.__tablename__)
        wanted = sorted(
            {
                (ids[key], slug)
                for label in seed.labels
                if (key := self.normalizer.key(label.text)) in ids
                for slug in label.links
                if taxonomy.node(slug) is not None
            }
        )
        stale = links.c.source == LinkSource.SEED.value
        if wanted:
            stale = and_(stale, tuple_(links.c.label_id, links.c.node_slug).not_in(wanted))    # noqa: E501
        await connection.execute(delete(links).where(stale))
        if wanted:
            statement = upsert(links).values(
                [{"label_id": i, "node_slug": slug, "source": LinkSource.SEED.value} for i, slug in wanted]    # noqa: E501
            )
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[links.c.label_id, links.c.node_slug],
                    set_={"source": LinkSource.SEED.value, "excluded": False},
                    where=links.c.source != LinkSource.USER.value,
                )
            )
        await self._seed_merges(connection, seed, ids)
        self.logger.info("%d seed labels applied (%d links).", len(rows), len(wanted))

    async def _write_state(self, connection: AsyncConnection, seed_hash: str) -> int:    # noqa: E501
        """Record the seed, incrementing the revision.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            seed_hash (str): The hash of the seed files.

        Returns:
            int: The new revision.
        """
        state = self._table(TaxonomyStateRow.__tablename__)
        statement = upsert(state).values(id=1, revision=1, seed_hash=seed_hash, seeded_at=func.now())
        revision = await connection.scalar(
            statement.on_conflict_do_update(
                index_elements=[state.c.id],
                set_={"revision": state.c.revision + 1, "seed_hash": seed_hash, "seeded_at": func.now()},
            ).returning(state.c.revision)
        )
        self.logger.debug("Taxonomy state written: revision %s, seed %s.", revision, seed_hash[:12])
        return int(revision or 0)

    ############################
    # Publicly Exposed Methods #
    ############################

    def seed_hash(self) -> str:
        """Hash the seed files.

        Returns:
            str: The SHA-256 of their contents (a missing file counts as empty).
        """
        digest = sha256()
        for path in self.paths:
            digest.update(path.name.encode("utf-8"))
            if not path.is_file():
                self.logger.warning("The seed file %s is missing: it counts as empty.", path)
            digest.update(path.read_bytes() if path.is_file() else b"")
        self.logger.debug("Seed hash of %d files computed: %s.", len(self.paths), digest.hexdigest()[:12])
        return digest.hexdigest()

    async def stored_hash(self, connection: AsyncConnection) -> Optional[str]:
        """Read the hash of the seed last applied.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            Optional[str]: The hash, `None` before the first seed.
        """
        state = self._table(TaxonomyStateRow.__tablename__)
        stored = await connection.scalar(select(state.c.seed_hash).where(state.c.id == 1))    # noqa: E501
        if stored is None:
            self.logger.debug("The taxonomy was never seeded.")
            return None
        return str(stored)

    async def apply(
        self, connection: AsyncConnection, rules: Optional[ClassificationRules] = None, force: bool = False
    ) -> bool:
        """Apply the seed files when they changed since the last seed (or when forced).

        Args:
            connection (AsyncConnection): The connection, in a transaction (the lock is released at its end).
            rules (Optional[ClassificationRules]): The classification rules, read from their file when not given.
            force (bool): Whether the seed is applied even when unchanged.

        Returns:
            bool: Whether the seed was applied.

        Raises:
            TaxonomySeedFileError: If a seed file cannot be loaded.
            UnknownTaxonomySlugError: If the rules or the label seed name nodes the taxonomy does not hold.
        """
        seed_hash = self.seed_hash()
        if not force and await self.stored_hash(connection) == seed_hash:
            self.logger.debug("The taxonomy seed is up to date.")
            return False
        kind, key = self.LOCK_KEYS
        await connection.execute(text("SELECT pg_advisory_xact_lock(:kind, :key)"), {"kind": kind, "key": key})
        if not force and await self.stored_hash(connection) == seed_hash:
            self.logger.debug("The taxonomy seed was applied by another process meanwhile.")
            return False
        seed = self.loader.load_taxonomy(self.paths[0])
        labels = self.loader.load_labels(self.paths[1])
        classifier = SoftwareClassifier(rules=rules, path=self.paths[2], taxonomy=seed)
        self.loader.check(seed, classifier.rules, labels)
        await self._seed_nodes(connection, seed)
        await self._seed_labels(connection, labels, seed)
        await self.labels.relink(connection, classifier)
        revision = await self._write_state(connection, seed_hash)
        self.logger.info(
            "Taxonomy seeded: %d nodes, %d seed labels (revision %d).", len(seed.nodes), len(labels.labels), revision    # noqa: E501
        )
        return True

    async def seed(self, force: bool = False) -> bool:
        """Apply the seed files in their own transaction.

        Args:
            force (bool): Whether the seed is applied even when unchanged.

        Returns:
            bool: Whether the seed was applied.

        Raises:
            StorageWriteError: If the seed cannot be written.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                return await self.apply(connection, force=force)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy seed cannot be written: %s", e)
            raise StorageWriteError("taxonomy seed", str(e)) from e
