from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Third Party Imports.
from sqlalchemy import Table, any_, bindparam, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import Text

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from models.taxonomy.enums import LabelStatus, Language, NameSource
from models.taxonomy.labels.resolved_label import ResolvedLabel
from storage.repositories.taxonomy.label_repository import LabelRepository
from storage.tables.base import Base
from storage.tables.taxonomy.label_link_row import LabelLinkRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from taxonomy.label_normalizer import LabelNormalizer

type LabelValue = Optional[str]


class LabelRegistry:
    """Resolve the source labels of the crawled items into stored labels, inserting the new ones, with a cache.

    Attributes:
        labels (LabelRepository): The stored source labels.
        normalizer (LabelNormalizer): The normalizer of the label texts.
        table (Table): The `source_labels` table.
        links (Table): The `label_links` table.
        revision (Optional[int]): The taxonomy revision the cache was loaded at, `None` before the first load.
        largest (int): The largest label identifier loaded.
        ids (Dict[str, int]): The identifier of each label, by key.
        info (Dict[int, Tuple[str, Optional[str], Optional[int], bool]]): The key, the English name key, the canonical
            label and whether it is noise, of each label.
        own_links (Dict[int, Dict[str, bool]]): The links of each label: whether each node is excluded.
        resolved (Dict[str, ResolvedLabel]): The resolved labels, by key.
        logger (Logger): The registry logger.

    Notes:
        - The labels sharing an English name (the same normalized key) are aliases, and so is a label merged into
          another (`canonical_id`): they make a group, whose nodes are those linked to any member, but those excluded
          by any member. "Базы данных" translated as "Databases" files its items like "Databases" does.
        - A new key is inserted with `INSERT ... ON CONFLICT (key) DO NOTHING` (the keys sorted), with its rule links,
          then read back: when concurrent crawls see the same new label, one row is stored and both get it.
        - The cache is reloaded when the taxonomy revision changes (a manual or language model edit), and extended
          with the labels other processes inserted (a larger identifier). A failed transaction invalidates it.
    """

    def __init__(self, labels: LabelRepository, logger: Optional[Logger] = None) -> None:    # noqa: E501
        """Initialize the registry, empty.

        Args:
            labels (LabelRepository): The stored source labels.
            logger (Optional[Logger]): The registry logger.
        """
        self.labels = labels
        self.logger = logger if logger else getLogger(__name__)
        self.normalizer = LabelNormalizer()
        tables = Base.metadata.tables
        self.table: Table = tables[SourceLabelRow.__tablename__]
        self.links: Table = tables[LabelLinkRow.__tablename__]
        self.revision: Optional[int] = None
        self.largest = 0
        self.ids: Dict[str, int] = {}
        self.info: Dict[int, Tuple[str, Optional[str], Optional[int], bool]] = {}  # noqa: E501
        self.own_links: Dict[int, Dict[str, bool]] = {}
        self.resolved: Dict[str, ResolvedLabel] = {}
        self.logger.debug("Label registry ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _group(self, label_id: int) -> str:
        """Get the group of a label: that of its canonical label, else its English name key, else its key.

        Args:
            label_id (int): The label.

        Returns:
            str: The group key (`n:` English name key, `k:` label key).
        """
        key, name_key, canonical, _ = self.info[label_id]
        if canonical is not None and canonical in self.info:
            key, name_key, _, _ = self.info[canonical]
        return f"n:{name_key}" if name_key else f"k:{key}"

    def _rebuild(self) -> None:
        """Resolve every cached label: its group and the nodes of the group."""
        groups = {label_id: self._group(label_id) for label_id in self.info}
        included: Dict[str, List[str]] = {}
        excluded: Dict[str, Set[str]] = {}
        for label_id, links in self.own_links.items():
            group = groups.get(label_id)
            if group is None:
                continue
            for slug, is_excluded in links.items():
                if is_excluded:
                    excluded.setdefault(group, set()).add(slug)
                else:
                    included.setdefault(group, []).append(slug)
        self.resolved = {
            key: ResolvedLabel(
                id=label_id,
                key=key,
                group=groups[label_id],
                noise=self.info[label_id][3],
                nodes=[]
                if self.info[label_id][3]
                else [
                    slug
                    for slug in included.get(groups[label_id], [])
                    if slug not in excluded.get(groups[label_id], set())
                ],
            )
            for key, label_id in self.ids.items()
        }
        self.logger.debug("%d labels resolved in %d groups.", len(self.resolved), len(set(groups.values())))

    async def _load(self, connection: AsyncConnection, after: int = 0, keys: Optional[List[str]] = None) -> None:    # noqa: E501
        """Load labels and their links into the cache, replacing it when every label is read.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            after (int): Only the labels with a larger identifier (0, without keys: every label, the cache replaced).
            keys (Optional[List[str]]): Only the labels with these keys (with `after`, either matches).

        Notes:
            The rows are read first, then the cache is changed
            without awaiting: concurrent crawls of the process
            share the cache, and never see it half loaded.
        """
        table = self.table
        condition = table.c.id > after
        if keys:
            condition = condition | (table.c.key == any_(bindparam("keys", keys, type_=ARRAY(Text))))
        rows = (
            await connection.execute(
                select(table.c.id, table.c.key, table.c.name_key, table.c.canonical_id, table.c.status).where(condition)
            )
        ).all()
        loaded = [int(row[0]) for row in rows]
        links: List[Tuple[int, str, bool]] = []
        if loaded:
            found = await connection.execute(
                select(self.links.c.label_id, self.links.c.node_slug, self.links.c.excluded).where(
                    self.links.c.label_id == any_(bindparam("loaded", loaded, type_=ARRAY(self.links.c.label_id.type)))
                )
            )
            links = [(int(label_id), str(slug), bool(is_excluded)) for label_id, slug, is_excluded in found.all()]    # noqa: E501
        replacing = after == 0 and not keys
        ids = {} if replacing else dict(self.ids)
        info = {} if replacing else dict(self.info)
        own_links = {} if replacing else dict(self.own_links)
        for label_id, key, name_key, canonical, status in rows:
            ids[str(key)] = int(label_id)
            noise = status == LabelStatus.NOISE.value
            info[int(label_id)] = (str(key), name_key, int(canonical) if canonical else None, noise)    # noqa: E501
            own_links[int(label_id)] = {}
        for label_id, slug, is_excluded in links:
            own_links[label_id][slug] = is_excluded
        self.ids, self.info, self.own_links = ids, info, own_links
        self.largest = max([0 if replacing else self.largest, *loaded])
        self.logger.debug("%d labels loaded in the cache (after %d).", len(loaded), after)    # noqa: E501

    def _new_row(self, classifier: SoftwareClassifier, key: str, label_text: str) -> Dict[str, LabelValue]:    # noqa: E501
        """Build the row of a label seen for the first time.

        Args:
            classifier (SoftwareClassifier): The classifier with the current rules.
            key (str): Its normalized key.
            label_text (str): Its text.

        Returns:
            Dict[str, LabelValue]: The `source_labels` values: an English label is its own English name, another one
                waits for its translation (`pending`), a noise label is `noise`.
        """
        language = self.normalizer.language(label_text)
        english = label_text if language is Language.ENGLISH else None
        return {
            "key": key,
            "text": label_text,
            "language": language.value,
            "name_en": english,
            "name_key": key if english else None,
            "name_source": NameSource.IDENTITY.value if english else None,
            "status": self.labels.rule_status(classifier, label_text, english).value,   # noqa: E501
            "status_source": NameSource.RULE.value,
        }

    ############################
    # Publicly Exposed Methods #
    ############################

    def invalidate(self) -> None:
        """Mark the cache stale: it is read again by the next refresh (a transaction failed, or the database changed).

        Notes:
            The cache is kept meanwhile, for the concurrent crawls of the process using it.
        """
        self.logger.debug("Label registry invalidated.")
        self.revision = None

    async def refresh(self, connection: AsyncConnection, revision: int, largest: int) -> None:    # noqa: E501
        """Reload the cache when the taxonomy changed, extend it with the labels other processes inserted.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            revision (int): The current taxonomy revision.
            largest (int): The current largest label identifier.
        """
        if revision != self.revision:
            self.logger.info("Loading the source labels (taxonomy revision %d).", revision)
            await self._load(connection)
            self.revision = revision
            self._rebuild()
        elif largest > self.largest:
            await self._load(connection, after=self.largest)
            self._rebuild()

    async def resolve(
        self, connection: AsyncConnection, texts: Iterable[str], classifier: SoftwareClassifier   # noqa: E501
    ) -> Dict[str, ResolvedLabel]:
        """Resolve label texts, inserting the labels seen for the first time with their rule links.

        Args:
            connection (AsyncConnection): The connection, in a transaction (call `refresh` first).
            texts (Iterable[str]): The label texts, in any language and spelling.
            classifier (SoftwareClassifier): The classifier with the current rules (for the new labels).

        Returns:
            Dict[str, ResolvedLabel]: The resolved labels, by key (the texts without any letter are left out).
        """
        keys: Dict[str, str] = {}
        for label_text in texts:
            cleaned = " ".join(label_text.split())
            key = self.normalizer.key(cleaned)
            if key and key not in keys:
                keys[key] = cleaned
        unknown = sorted(key for key in keys if key not in self.ids)
        if unknown:
            rows = [self._new_row(classifier, key, keys[key]) for key in unknown]   # noqa: E501
            inserted = await connection.execute(
                upsert(self.table)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[self.table.c.key])
                .returning(self.table.c.id, self.table.c.key, self.table.c.name_en)   # noqa: E501
            )
            links = {
                int(label_id): self.labels.rule_nodes(classifier, keys[str(key)], name_en)   # noqa: E501
                for label_id, key, name_en in inserted.all()
            }
            await self.labels.write_rule_links(connection, links)
            await self._load(connection, after=self.largest, keys=unknown)
            self._rebuild()
            self.logger.info("%d new source labels stored, %d seen before.", len(links), len(unknown) - len(links))   # noqa: E501
        return {key: self.resolved[key] for key in keys if key in self.resolved}   # noqa: E501
