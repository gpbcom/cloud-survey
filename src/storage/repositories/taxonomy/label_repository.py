from __future__ import annotations

# Standard Library Imports.
from datetime import timedelta
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple, Union

# Third Party Imports.
from sqlalchemy import (
    BigInteger,
    Table,
    and_,
    any_,
    bindparam,
    case,
    column,
    delete,
    func,
    insert,
    or_,
    select,
    true,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from models.storage.enums import DatasetKind
from models.taxonomy.enums import LabelStatus, Language, LinkSource, NameSource
from models.taxonomy.labels.label_details import LabelDetails
from models.taxonomy.labels.source_label import SourceLabel
from models.taxonomy.llm.label_translation import LabelTranslation
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.repositories.taxonomy.taxonomy_repository import TaxonomyRepository
from storage.tables.base import Base
from storage.tables.items.product_row import ProductRow
from storage.tables.items.software_row import SoftwareRow
from storage.tables.taxonomy.label_link_row import LabelLinkRow
from storage.tables.taxonomy.label_sighting_row import LabelSightingRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from taxonomy.label_normalizer import LabelNormalizer


class LabelRepository:
    """Create, read, update, delete and list the source labels, with their links to the taxonomy and sightings.

    Attributes:
        RULE_STATUS_SOURCES (ClassVar[Tuple[str, ...]]): The status sources the rules may overwrite.
        database (Database): The open database.
        taxonomy (TaxonomyRepository): The taxonomy, whose revision every edit increments.
        labels (Table): The `source_labels` table.
        links (Table): The `label_links` table.
        sightings (Table): The `label_sightings` table.
        items (Tuple[Table, ...]): The items tables (products and software), counting the items of each label.
        normalizer (LabelNormalizer): The normalizer of the English names.
        classifier (Optional[SoftwareClassifier]): The classifier of the project rules, read when a label is renamed.
        logger (Logger): The repository logger.

    Notes:
        - The rule links of a label are those of its text and of its English name (see
          `SoftwareClassifier.label_categories`). Recomputing them replaces the `rule` links only: the seed, language
          model and user links (and the exclusions) are kept, and own their nodes (no rule link is added beside them).
        - The rows are always locked in the order of their keys, so that concurrent crawls never deadlock.
        - The edits of the Categories manager (`update`, `set_status`, `link`, `unlink`, `merge`, `unmerge`) are made
          by a person: they are never overwritten. Each increments the revision and returns the labels whose items must
          be categorized again (the label and its aliases, before and after the edit).
        - A label is the aggregate root: `create` writes it with its rule links, `update` sets its English name,
          `delete` removes it with its links and sightings (its aliases are left unmerged) when no item carries it.
    """

    RULE_STATUS_SOURCES: ClassVar[Tuple[str, ...]] = (NameSource.RULE.value, NameSource.IDENTITY.value)

    def __init__(self, database: Database, taxonomy: TaxonomyRepository, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            taxonomy (TaxonomyRepository): The taxonomy, whose revision every edit increments.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.taxonomy = taxonomy
        self.logger = logger if logger else getLogger(__name__)
        tables = Base.metadata.tables
        self.labels: Table = tables[SourceLabelRow.__tablename__]
        self.links: Table = tables[LabelLinkRow.__tablename__]
        self.sightings: Table = tables[LabelSightingRow.__tablename__]
        self.items: Tuple[Table, ...] = (tables[ProductRow.__tablename__], tables[SoftwareRow.__tablename__])
        self.normalizer = LabelNormalizer()
        self.classifier: Optional[SoftwareClassifier] = None
        self.logger.debug("Repository of the source labels ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _group_ids(self, connection: AsyncConnection, label_ids: Sequence[int]) -> List[int]:
        """Get some labels with their aliases: the same English name, the label they were merged into, its aliases.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            label_ids (Sequence[int]): The labels.

        Returns:
            List[int]: The identifiers of the labels and of their aliases, sorted.
        """
        labels = self.labels
        chosen = labels.c.id.in_(list(label_ids))
        names = select(labels.c.name_key).where(chosen, labels.c.name_key.is_not(None))
        canonicals = select(labels.c.canonical_id).where(chosen, labels.c.canonical_id.is_not(None))
        members = or_(
            chosen,
            labels.c.canonical_id.in_(list(label_ids)),
            labels.c.name_key.in_(names),
            labels.c.id.in_(canonicals),
            labels.c.canonical_id.in_(canonicals),
        )
        found = (await connection.execute(select(labels.c.id).where(members))).scalars().all()
        group = sorted({int(label_id) for label_id in found})
        self.logger.debug("%d labels extended to their %d aliases.", len(label_ids), len(group))
        return group

    def _rules(self) -> SoftwareClassifier:
        """Get the classifier of the project rules, reading them the first time.

        Returns:
            SoftwareClassifier: The classifier.
        """
        if self.classifier is None:
            self.logger.debug("Reading the classification rules for the label links.")
            self.classifier = SoftwareClassifier(logger=self.logger)
        return self.classifier

    async def _edit(self, connection: AsyncConnection, label_ids: Sequence[int], before: List[int]) -> List[int]:
        """Close an edit: increment the revision, and get the labels whose items must be categorized again.

        Args:
            connection (AsyncConnection): The connection, in the transaction of the edit.
            label_ids (Sequence[int]): The edited labels.
            before (List[int]): The edited labels and their aliases before the edit.

        Returns:
            List[int]: The edited labels and their aliases, before and after the edit.
        """
        after = await self._group_ids(connection, label_ids)
        await self.taxonomy.bump(connection)
        affected = sorted({*before, *after})
        self.logger.debug("Label edit of %d labels affects %d labels.", len(label_ids), len(affected))
        return affected

    ############################
    # Publicly Exposed Methods #
    ############################

    def rule_nodes(self, classifier: SoftwareClassifier, text: str, name_en: Optional[str]) -> List[str]:
        """Get the taxonomy nodes the rules give a label.

        Args:
            classifier (SoftwareClassifier): The classifier with the current rules.
            text (str): The label text.
            name_en (Optional[str]): Its English name, if known.

        Returns:
            List[str]: The slugs of its text, then those of its English name, each once (none for a noise label).
        """
        if classifier.is_noise(text):
            return []
        names = [text, name_en] if name_en and name_en != text else [text]
        return list(dict.fromkeys(slug for name in names for slug in classifier.label_categories(name)))

    def rule_status(self, classifier: SoftwareClassifier, text: str, name_en: Optional[str]) -> LabelStatus:
        """Get the status the rules give a label.

        Args:
            classifier (SoftwareClassifier): The classifier with the current rules.
            text (str): The label text.
            name_en (Optional[str]): Its English name, if known.

        Returns:
            LabelStatus: `noise` for a noise label, else `translated` with an English name, else `pending`.
        """
        if classifier.is_noise(text) or (name_en is not None and classifier.is_noise(name_en)):
            return LabelStatus.NOISE
        return LabelStatus.TRANSLATED if name_en else LabelStatus.PENDING

    async def write_rule_links(self, connection: AsyncConnection, links: Dict[int, List[str]]) -> None:
        """Replace the rule links of some labels.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            links (Dict[int, List[str]]): The taxonomy slugs the rules give each label.
        """
        self.logger.debug("Writing the rule links of %d labels.", len(links))
        if not links:
            return
        label_ids = sorted(links)
        wanted = sorted({(label_id, slug) for label_id, slugs in links.items() for slug in slugs})
        stale = and_(
            self.links.c.source == LinkSource.RULE.value,
            self.links.c.label_id == any_(bindparam("label_ids", label_ids, type_=ARRAY(BigInteger))),
        )
        if wanted:
            stale = and_(stale, tuple_(self.links.c.label_id, self.links.c.node_slug).not_in(wanted))
        await connection.execute(delete(self.links).where(stale))
        if wanted:
            await connection.execute(
                upsert(self.links)
                .values([{"label_id": i, "node_slug": slug, "source": LinkSource.RULE.value} for i, slug in wanted])
                .on_conflict_do_nothing(index_elements=[self.links.c.label_id, self.links.c.node_slug])
            )

    async def sight(
        self, connection: AsyncConnection, label_ids: Sequence[int], kind: DatasetKind, provider: str
    ) -> None:
        """Record that a dataset gives some labels.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            label_ids (Sequence[int]): The labels seen.
            kind (DatasetKind): The kind of the dataset.
            provider (str): The cloud provider.
        """
        self.logger.debug("%d labels seen in the %s %s.", len(label_ids), provider, kind.value)
        if not label_ids:
            return
        ordered = sorted(set(label_ids))
        statement = upsert(self.sightings).values(
            [{"label_id": label_id, "kind": kind.value, "provider": provider} for label_id in ordered]
        )
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[self.sightings.c.label_id, self.sightings.c.kind, self.sightings.c.provider],
                set_={"last_seen_at": func.now()},
            )
        )
        await connection.execute(
            update(self.labels)
            .where(self.labels.c.id == any_(bindparam("seen", ordered, type_=ARRAY(BigInteger))))
            .values(last_seen_at=func.now())
        )

    async def relink(self, connection: AsyncConnection, classifier: SoftwareClassifier) -> int:
        """Recompute the rule links and the rule statuses of every label, with the current rules.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            classifier (SoftwareClassifier): The classifier with the current rules.

        Returns:
            int: The number of labels whose links or status changed (the revision is incremented when any did).
        """
        self.logger.debug("Recomputing the rule links of the labels.")
        rows = (
            (
                await connection.execute(
                    select(
                        self.labels.c.id,
                        self.labels.c.text,
                        self.labels.c.name_en,
                        self.labels.c.status,
                        self.labels.c.status_source,
                    ).order_by(self.labels.c.id)
                )
            )
            .mappings()
            .all()
        )
        current: Dict[int, Set[str]] = {}
        owned: Dict[int, Set[str]] = {}
        for label_id, slug, source in (
            await connection.execute(select(self.links.c.label_id, self.links.c.node_slug, self.links.c.source))
        ).all():
            target = current if source == LinkSource.RULE.value else owned
            target.setdefault(int(label_id), set()).add(str(slug))
        links: Dict[int, List[str]] = {}
        statuses: List[Dict[str, Union[int, str]]] = []
        for row in rows:
            label_id = int(row["id"])
            nodes = self.rule_nodes(classifier, row["text"], row["name_en"])
            if set(nodes) - owned.get(label_id, set()) != current.get(label_id, set()):
                links[label_id] = nodes
            rule_source = row["status_source"] is None or row["status_source"] in self.RULE_STATUS_SOURCES
            status = self.rule_status(classifier, row["text"], row["name_en"])
            if rule_source and status.value != row["status"]:
                statuses.append({"row_id": label_id, "new_status": status.value})
        await self.write_rule_links(connection, links)
        if statuses:
            await connection.execute(
                update(self.labels)
                .where(self.labels.c.id == bindparam("row_id"))
                .values(status=bindparam("new_status"), status_source=NameSource.RULE.value),
                statuses,
            )
        changed = len(set(links) | {int(status["row_id"]) for status in statuses})
        if changed:
            await self.taxonomy.bump(connection)
        self.logger.info("Rule links recomputed: %d of %d labels changed.", changed, len(rows))
        return changed

    async def recompute_rule_links(self, classifier: SoftwareClassifier) -> int:
        """Recompute the rule links and the rule statuses of every label, in their own transaction.

        Args:
            classifier (SoftwareClassifier): The classifier with the current rules.

        Returns:
            int: The number of labels whose links or status changed (see `relink`).

        Raises:
            StorageWriteError: If the links cannot be written.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                return await self.relink(connection, classifier)
        except SQLAlchemyError as e:
            self.logger.error("The rule links of the labels cannot be recomputed: %s", e)
            raise StorageWriteError("rule links of the labels", str(e)) from e

    async def pending(self) -> int:
        """Count the labels waiting for their English name.

        Returns:
            int: The number of pending labels.
        """
        async with self.database.connect() as connection:
            count = await connection.scalar(
                select(func.count()).select_from(self.labels).where(self.labels.c.status == LabelStatus.PENDING.value)
            )
        self.logger.debug("%d labels are pending.", count or 0)
        return int(count or 0)

    async def delete(self, label_id: int) -> bool:
        """Delete a label no item carries, with its links and sightings (its aliases are no longer merged into it).

        Args:
            label_id (int): The label.

        Returns:
            bool: Whether the label existed.

        Raises:
            StorageWriteError: If an item still carries the label, or it cannot be deleted.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                for table in self.items:
                    carried = select(func.count()).where(table.c.source_label_ids.contains([label_id]))
                    if await connection.scalar(carried):
                        self.logger.error("Items of %s still carry the label %d: not deleted.", table.name, label_id)
                        raise StorageWriteError(f"label {label_id}", f"{table.name} still carry it")
                for owned in (self.links, self.sightings):
                    await connection.execute(delete(owned).where(owned.c.label_id == label_id))
                result = await connection.execute(delete(self.labels).where(self.labels.c.id == label_id))
                if result.rowcount:
                    await self.taxonomy.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The label %d cannot be deleted: %s", label_id, e)
            raise StorageWriteError(f"label {label_id}", str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("Label %d deleted.", label_id)
        else:
            self.logger.debug("No source label %d: nothing deleted.", label_id)
        return found

    async def read_all(self) -> List[SourceLabel]:
        """Read every stored label, for the names shown by the GUI.

        Returns:
            List[SourceLabel]: The labels, by identifier.

        Raises:
            StorageReadError: If the labels cannot be read.
        """
        columns = [
            self.labels.c.id,
            self.labels.c.text,
            self.labels.c.language,
            self.labels.c.name_en,
            self.labels.c.status,
            self.labels.c.canonical_id,
        ]
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(select(*columns).order_by(self.labels.c.id))).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The source labels cannot be read: %s", e)
            raise StorageReadError("source labels", str(e)) from e
        labels = [SourceLabel.model_validate(dict(row)) for row in rows]
        self.logger.debug("%d source labels read.", len(labels))
        return labels

    async def list(self, label_ids: Optional[Sequence[int]] = None) -> List[LabelDetails]:
        """List the labels with their links, where they were seen and their number of items (the Categories manager).

        Args:
            label_ids (Optional[Sequence[int]]): Only these labels, every one when `None`.

        Returns:
            List[LabelDetails]: The labels, by identifier.

        Raises:
            StorageReadError: If the labels cannot be read.
        """
        labels = self.labels
        chosen = select(labels).order_by(labels.c.id)
        linked = select(self.links.c.label_id, self.links.c.node_slug, self.links.c.excluded)
        seen_in = select(self.sightings.c.label_id, self.sightings.c.kind, self.sightings.c.provider)
        if label_ids is not None:
            chosen = chosen.where(labels.c.id.in_(list(label_ids)))
            linked = linked.where(self.links.c.label_id.in_(list(label_ids)))
            seen_in = seen_in.where(self.sightings.c.label_id.in_(list(label_ids)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(chosen)).mappings().all()
                links = (await connection.execute(linked)).all()
                sightings = (await connection.execute(seen_in)).all()
                counts: Dict[int, int] = {}
                for table in self.items:
                    carried = func.unnest(table.c.source_label_ids).table_valued("label_id").render_derived()
                    label_id = column("label_id", BigInteger)
                    statement = (
                        select(label_id, func.count())
                        .select_from(table)
                        .join(carried, true())
                        .where(table.c.deleted_at.is_(None))
                        .group_by(label_id)
                    )
                    if label_ids is not None:
                        statement = statement.where(table.c.source_label_ids.overlap(list(label_ids)))
                    for found_id, count in (await connection.execute(statement)).all():
                        counts[int(found_id)] = counts.get(int(found_id), 0) + int(count)
        except SQLAlchemyError as e:
            self.logger.error("The source labels cannot be read: %s", e)
            raise StorageReadError("source labels", str(e)) from e
        included: Dict[int, List[str]] = {}
        excluded: Dict[int, List[str]] = {}
        for label_id, slug, is_excluded in links:
            (excluded if is_excluded else included).setdefault(int(label_id), []).append(str(slug))
        seen: Dict[int, List[str]] = {}
        for label_id, kind, provider in sightings:
            seen.setdefault(int(label_id), []).append(f"{kind}:{provider}")
        details = [
            LabelDetails.model_validate(
                {
                    **{name: row[name] for name in ("id", "text", "language", "name_en", "status", "canonical_id")},
                    "name_source": row["name_source"],
                    "status_source": row["status_source"],
                    "links": included.get(int(row["id"]), []),
                    "excluded": excluded.get(int(row["id"]), []),
                    "providers": seen.get(int(row["id"]), []),
                    "items": counts.get(int(row["id"]), 0),
                }
            )
            for row in rows
        ]
        self.logger.info("%d source labels read for the Categories manager.", len(details))
        return details

    async def read(self, label_id: int) -> Optional[LabelDetails]:
        """Read one label with its links, where it was seen and its number of items.

        Args:
            label_id (int): The label.

        Returns:
            Optional[LabelDetails]: The label, `None` when there is none.

        Raises:
            StorageReadError: If the label cannot be read.
        """
        found = await self.list([label_id])
        if not found:
            self.logger.debug("No source label %d.", label_id)
            return None
        return found[0]

    async def create(self, label_text: str) -> LabelDetails:
        """Store a label never seen, from its text: its language, English name, status and rule links are derived.

        Args:
            label_text (str): Its text as the providers write it.

        Returns:
            LabelDetails: The label, as stored.

        Raises:
            StorageWriteError: If the text has no letter, the label is already stored, or it cannot be written.
        """
        cleaned = " ".join(label_text.split())
        key = self.normalizer.key(cleaned)
        if not key:
            self.logger.error("The label %r has no letter: not created.", label_text)
            raise StorageWriteError("source labels", f"{label_text!r} has no letter")
        rules = self._rules()
        language = self.normalizer.language(cleaned)
        english = cleaned if language is Language.ENGLISH else None
        row = {
            "key": key,
            "text": cleaned,
            "language": language.value,
            "name_en": english,
            "name_key": key if english else None,
            "name_source": NameSource.IDENTITY.value if english else None,
            "status": self.rule_status(rules, cleaned, english).value,
            "status_source": NameSource.RULE.value,
        }
        try:
            async with self.database.connect() as connection, connection.begin():
                label_id = int(
                    (await connection.execute(insert(self.labels).values(row).returning(self.labels.c.id))).scalar_one()
                )
                await self.write_rule_links(connection, {label_id: self.rule_nodes(rules, cleaned, english)})
                await self.taxonomy.bump(connection)
        except IntegrityError as e:
            self.logger.error("The label %r is already stored (key %s): not created.", cleaned, key)
            raise StorageWriteError("source labels", f"{cleaned!r} already exists") from e
        except SQLAlchemyError as e:
            self.logger.error("The label %r cannot be created: %s", cleaned, e)
            raise StorageWriteError("source labels", str(e)) from e
        created = await self.read(label_id)
        if created is None:
            self.logger.error("The label %d was written but cannot be read back.", label_id)
            raise StorageWriteError("source labels", f"label {label_id} was not stored")
        self.logger.info("Label %d %r created.", label_id, cleaned)
        return created

    async def update(self, label_id: int, name_en: Optional[str]) -> List[int]:
        """Set the English name of a label by hand: it joins the aliases of the name, and the rules link it again.

        Args:
            label_id (int): The label.
            name_en (Optional[str]): Its English name, `None` (or blank) to make it pending again.

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the name cannot be written.
        """
        name = " ".join((name_en or "").split()) or None
        status = LabelStatus.REVIEWED if name else LabelStatus.PENDING
        try:
            async with self.database.connect() as connection, connection.begin():
                before = await self._group_ids(connection, [label_id])
                label_text = await connection.scalar(select(self.labels.c.text).where(self.labels.c.id == label_id))
                if label_text is not None:
                    nodes = self.rule_nodes(self._rules(), str(label_text), name)
                    await self.write_rule_links(connection, {label_id: nodes})
                await connection.execute(
                    update(self.labels)
                    .where(self.labels.c.id == label_id)
                    .values(
                        name_en=name,
                        name_key=self.normalizer.key(name) if name else None,
                        name_source=NameSource.USER.value,
                        status=status.value,
                        status_source=NameSource.USER.value,
                        translated_at=func.now(),
                    )
                )
                affected = await self._edit(connection, [label_id], before)
        except SQLAlchemyError as e:
            self.logger.error("The English name of the label %d cannot be set: %s", label_id, e)
            raise StorageWriteError(f"label {label_id}", str(e)) from e
        self.logger.info("Label %d named %r by hand.", label_id, name)
        return affected

    async def set_status(self, label_ids: Sequence[int], status: LabelStatus) -> List[int]:
        """Set the status of labels by hand (e.g. noise, or reviewed).

        Args:
            label_ids (Sequence[int]): The labels.
            status (LabelStatus): Their status.

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the status cannot be written.
        """
        ordered = sorted(set(label_ids))
        try:
            async with self.database.connect() as connection, connection.begin():
                before = await self._group_ids(connection, ordered)
                await connection.execute(
                    update(self.labels)
                    .where(self.labels.c.id == any_(bindparam("ids", ordered, type_=ARRAY(BigInteger))))
                    .values(status=status.value, status_source=NameSource.USER.value)
                )
                affected = await self._edit(connection, ordered, before)
        except SQLAlchemyError as e:
            self.logger.error("The status of %d labels cannot be set: %s", len(ordered), e)
            raise StorageWriteError("label status", str(e)) from e
        self.logger.info("%d labels marked %s by hand.", len(ordered), status.value)
        return affected

    async def link(self, label_id: int, slug: str, linked: bool = True) -> List[int]:
        """Link a label to a taxonomy node by hand, or remove the link (an exclusion surviving the rules).

        Args:
            label_id (int): The label.
            slug (str): The category or domain.
            linked (bool): Whether the label tells the node (`False`: it must not).

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the link cannot be written (e.g. an unknown node).
        """
        statement = upsert(self.links).values(
            label_id=label_id, node_slug=slug, source=LinkSource.USER.value, excluded=not linked
        )
        try:
            async with self.database.connect() as connection, connection.begin():
                before = await self._group_ids(connection, [label_id])
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[self.links.c.label_id, self.links.c.node_slug],
                        set_={"source": LinkSource.USER.value, "excluded": not linked},
                    )
                )
                affected = await self._edit(connection, [label_id], before)
        except SQLAlchemyError as e:
            self.logger.error("The label %d cannot be linked to %s: %s", label_id, slug, e)
            raise StorageWriteError(f"link of the label {label_id}", str(e)) from e
        self.logger.info("Label %d %s %s by hand.", label_id, "linked to" if linked else "unlinked from", slug)
        return affected

    async def unlink(self, label_id: int, slug: str) -> List[int]:
        """Remove a link of a label by hand: the rules never add it back.

        Args:
            label_id (int): The label.
            slug (str): The category or domain.

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the exclusion cannot be written.
        """
        return await self.link(label_id, slug, linked=False)

    async def merge(self, label_id: int, canonical_id: Optional[int]) -> List[int]:
        """Merge a label into another one by hand (it becomes its alias), or undo its merge.

        Args:
            label_id (int): The label.
            canonical_id (Optional[int]): The label it is merged into, `None` to undo the merge.

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the merge cannot be written (e.g. a label merged into itself).
        """
        if canonical_id == label_id:
            self.logger.error("The label %d cannot be merged into itself.", label_id)
            raise StorageWriteError(f"label {label_id}", "a label cannot be merged into itself")
        try:
            async with self.database.connect() as connection, connection.begin():
                before = await self._group_ids(connection, [label_id])
                target = canonical_id
                if canonical_id is not None:
                    deeper = await connection.scalar(
                        select(self.labels.c.canonical_id).where(self.labels.c.id == canonical_id)
                    )
                    target = int(deeper) if deeper is not None and int(deeper) != label_id else canonical_id
                await connection.execute(
                    update(self.labels)
                    .where(self.labels.c.id == label_id)
                    .values(canonical_id=target, canonical_source=NameSource.USER.value if target else None)
                )
                affected = await self._edit(connection, [label_id, *([target] if target else [])], before)
        except SQLAlchemyError as e:
            self.logger.error("The label %d cannot be merged into %s: %s", label_id, canonical_id, e)
            raise StorageWriteError(f"label {label_id}", str(e)) from e
        self.logger.info("Label %d %s by hand.", label_id, f"merged into {target}" if target else "unmerged")
        return affected

    async def unmerge(self, label_id: int) -> List[int]:
        """Undo the merge of a label by hand.

        Args:
            label_id (int): The label.

        Returns:
            List[int]: The labels whose items must be categorized again.

        Raises:
            StorageWriteError: If the merge cannot be undone.
        """
        return await self.merge(label_id, None)

    async def claim_pending(
        self, limit: int, retry_after: timedelta = timedelta(hours=1), attempts: int = 3
    ) -> List[SourceLabel]:
        """Claim pending labels for the language model, skipping those another process claimed.

        Args:
            limit (int): The largest number of labels claimed.
            retry_after (timedelta): How long a claimed label waits before it is claimed again (a failed run).
            attempts (int): The number of attempts after which a label waits for a person.

        Returns:
            List[SourceLabel]: The claimed labels, by identifier.

        Raises:
            StorageWriteError: If the labels cannot be claimed.

        Notes:
            The labels are locked with `FOR UPDATE SKIP LOCKED`:
            concurrent runs never claim the same label.
        """
        labels = self.labels
        claimable = (
            select(labels.c.id)
            .where(
                labels.c.status == LabelStatus.PENDING.value,
                labels.c.llm_attempts < attempts,
                or_(labels.c.llm_claimed_at.is_(None), labels.c.llm_claimed_at < func.now() - retry_after),
            )
            .order_by(labels.c.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        columns = [
            labels.c.id,
            labels.c.text,
            labels.c.language,
            labels.c.name_en,
            labels.c.status,
            labels.c.canonical_id,
        ]
        try:
            async with self.database.connect() as connection, connection.begin():
                rows = (
                    (
                        await connection.execute(
                            update(labels)
                            .where(labels.c.id.in_(claimable))
                            .values(llm_claimed_at=func.now(), llm_attempts=labels.c.llm_attempts + 1)
                            .returning(*columns)
                        )
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError as e:
            self.logger.error("The pending labels cannot be claimed: %s", e)
            raise StorageWriteError("pending labels", str(e)) from e
        claimed = sorted((SourceLabel.model_validate(dict(row)) for row in rows), key=lambda label: label.id)
        self.logger.info("%d pending labels claimed for the language model.", len(claimed))
        return claimed

    async def apply_translations(self, translations: Sequence[LabelTranslation], slugs: Set[str]) -> List[int]:
        """Write the English names and the links the language model gave labels.

        Args:
            translations (Sequence[LabelTranslation]): The answers, by label identifier.
            slugs (Set[str]): The taxonomy slugs which exist (the others are left out).

        Returns:
            List[int]: The labels whose items must be categorized again (the labels and their aliases).

        Raises:
            StorageWriteError: If the translations cannot be written.

        Notes:
            - A name or a status a person set is never overwritten, nor a link a person made or excluded.
            - The rules link the labels again from their new English names.
        """
        ids = sorted({translation.id for translation in translations})
        if not ids:
            return []
        labels, links = self.labels, self.links
        by_user_name = labels.c.name_source == NameSource.USER.value
        by_user_status = labels.c.status_source == NameSource.USER.value
        try:
            async with self.database.connect() as connection, connection.begin():
                before = await self._group_ids(connection, ids)
                texts = dict(
                    (await connection.execute(select(labels.c.id, labels.c.text).where(labels.c.id.in_(ids)))).all()
                )
                rule_links: Dict[int, List[str]] = {}
                for translation in sorted(translations, key=lambda one: one.id):
                    if translation.id not in texts:
                        continue
                    name = translation.english or None
                    status = LabelStatus.NOISE if translation.noise else LabelStatus.TRANSLATED
                    await connection.execute(
                        update(labels)
                        .where(labels.c.id == translation.id)
                        .values(
                            name_en=case((by_user_name, labels.c.name_en), else_=name),
                            name_key=case(
                                (by_user_name, labels.c.name_key), else_=self.normalizer.key(name) if name else None
                            ),
                            name_source=case((by_user_name, labels.c.name_source), else_=NameSource.LLM.value),
                            status=case((by_user_status, labels.c.status), else_=status.value),
                            status_source=case((by_user_status, labels.c.status_source), else_=NameSource.LLM.value),
                            translated_at=func.now(),
                            llm_claimed_at=None,
                            llm_error=None,
                        )
                    )
                    wanted = [slug for slug in translation.slugs if slug in slugs] if not translation.noise else []
                    if wanted:
                        await connection.execute(
                            upsert(links)
                            .values(
                                [
                                    {"label_id": translation.id, "node_slug": slug, "source": LinkSource.LLM.value}
                                    for slug in wanted
                                ]
                            )
                            .on_conflict_do_nothing(index_elements=[links.c.label_id, links.c.node_slug])
                        )
                    rule_links[translation.id] = self.rule_nodes(self._rules(), str(texts[translation.id]), name)
                await self.write_rule_links(connection, rule_links)
                affected = await self._edit(connection, ids, before)
        except SQLAlchemyError as e:
            self.logger.error("The translations of %d labels cannot be written: %s", len(ids), e)
            raise StorageWriteError("label translations", str(e)) from e
        self.logger.info("%d labels translated by the language model.", len(ids))
        return affected

    async def release(self, label_ids: Sequence[int], error: str) -> None:
        """Give claimed labels back after a failed call, with the error.

        Args:
            label_ids (Sequence[int]): The claimed labels.
            error (str): Why the call failed.

        Raises:
            StorageWriteError: If the labels cannot be released.
        """
        ordered = sorted(set(label_ids))
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(
                    update(self.labels)
                    .where(self.labels.c.id == any_(bindparam("ids", ordered, type_=ARRAY(BigInteger))))
                    .values(llm_claimed_at=None, llm_error=error[:2000])
                )
        except SQLAlchemyError as e:
            self.logger.error("The claimed labels cannot be released: %s", e)
            raise StorageWriteError("claimed labels", str(e)) from e
        self.logger.warning("%d labels released after a failed call: %s", len(ordered), error)

    async def seen_at(self, label_ids: Sequence[int]) -> Dict[int, List[str]]:
        """Read where labels were seen.

        Args:
            label_ids (Sequence[int]): The labels.

        Returns:
            Dict[int, List[str]]: The providers of each label (sorted, each once), by identifier.

        Raises:
            StorageReadError: If the sightings cannot be read.
        """
        statement = select(self.sightings.c.label_id, self.sightings.c.provider).where(
            self.sightings.c.label_id.in_(list(label_ids))
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The sightings of %d labels cannot be read: %s", len(label_ids), e)
            raise StorageReadError("label sightings", str(e)) from e
        seen: Dict[int, Set[str]] = {}
        for label_id, provider in rows:
            seen.setdefault(int(label_id), set()).add(str(provider))
        self.logger.debug("Sightings of %d labels read.", len(seen))
        return {label_id: sorted(providers) for label_id, providers in seen.items()}
