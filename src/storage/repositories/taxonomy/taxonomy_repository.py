from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from sqlalchemy import Table, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from models.taxonomy.enums import LinkSource, NodeOrigin

# First Party Imports.
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.taxonomy.label_link_row import LabelLinkRow
from storage.tables.taxonomy.source_label_row import SourceLabelRow
from storage.tables.taxonomy.taxonomy_node_row import TaxonomyNodeRow
from storage.tables.taxonomy.taxonomy_state_row import TaxonomyStateRow


class TaxonomyRepository:
    """Read the unified taxonomy stored in SQL, and its revision.

    Attributes:
        SLUG_SEPARATORS (ClassVar[str]): The pattern of the characters replaced by a dash in a new slug.
        database (Database): The open database.
        nodes (Table): The `taxonomy_nodes` table.
        links (Table): The `label_links` table.
        state (Table): The `taxonomy_state` table.
        labels (Table): The `source_labels` table.
        logger (Logger): The repository logger.

    Notes:
        - The revision changes with every manual or language model edit of the taxonomy or of the labels: the writers
          reload their caches when it changes. The crawls never change it (they only add labels, found by the largest
          label identifier).
        - A node without its Russian or Chinese name (added by hand) is read with its English name instead.
        - The edits of the Categories manager (`add_node`, `update_node`, `set_hidden`, `move_node`, `merge_node`) mark
          the nodes edited (the seed no longer overwrites them), increment the revision and return the nodes whose
          items must be categorized again. A node is never deleted: the items store its slug.
    """

    SLUG_SEPARATORS: ClassVar[str] = r"[^a-z0-9]+"

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        tables = Base.metadata.tables
        self.nodes: Table = tables[TaxonomyNodeRow.__tablename__]
        self.state: Table = tables[TaxonomyStateRow.__tablename__]
        self.labels: Table = tables[SourceLabelRow.__tablename__]
        self.links: Table = tables[LabelLinkRow.__tablename__]
        self.logger.debug("Repository of the taxonomy ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _node(self, row: RowMapping) -> Dict[str, JsonValue]:
        """Convert a node row to the raw values of a `TaxonomyNode`.

        Args:
            row (RowMapping): The `taxonomy_nodes` row.

        Returns:
            Dict[str, JsonValue]: The node values, the missing translations replaced by the English name.
        """
        name_en = str(row["name_en"])
        return {
            "slug": row["slug"],
            "parent_slug": row["parent_slug"],
            "name_en": name_en,
            "name_ru": row["name_ru"] or name_en,
            "name_zh": row["name_zh"] or name_en,
            "description_en": row["description_en"],
            "position": row["position"],
            "audiences": list(row["audiences"]),
            "origin": row["origin"],
            "edited": row["edited"],
            "hidden": row["hidden"],
            "umbrella": row["umbrella"],
        }

    async def _node_row(self, connection: AsyncConnection, slug: str) -> RowMapping:
        """Read a stored node.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            slug (str): The node slug.

        Returns:
            RowMapping: Its row.

        Raises:
            StorageWriteError: If the node does not exist.
        """
        row = (await connection.execute(select(self.nodes).where(self.nodes.c.slug == slug))).mappings().first()
        if row is None:
            self.logger.error("No taxonomy node %r.", slug)
            raise StorageWriteError(f"taxonomy node {slug}", "unknown node")
        return row

    async def _new_slug(self, connection: AsyncConnection, name_en: str) -> str:
        """Make the slug of a new node from its English name, unique.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            name_en (str): The English name.

        Returns:
            str: The kebab-case name (`category` without any Latin letter), numbered when taken.
        """
        base = re.sub(self.SLUG_SEPARATORS, "-", name_en.casefold()).strip("-")[:50] or "category"
        taken = set(
            (await connection.execute(select(self.nodes.c.slug).where(self.nodes.c.slug.like(f"{base}%")))).scalars()
        )
        slug, number = base, 2
        while slug in taken:
            slug, number = f"{base}-{number}", number + 1
        return slug

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, connection: AsyncConnection) -> Taxonomy:
        """Read the stored taxonomy.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            Taxonomy: The domains by position, each followed by its categories by position (the hidden ones included).

        Raises:
            StorageReadError: If the stored nodes do not make a valid taxonomy.
        """
        self.logger.debug("Reading the stored taxonomy.")
        rows = (await connection.execute(select(self.nodes))).mappings().all()
        domains = sorted((row for row in rows if row["parent_slug"] is None), key=lambda row: row["position"])
        children: Dict[str, List[RowMapping]] = {}
        for row in rows:
            if row["parent_slug"] is not None:
                children.setdefault(str(row["parent_slug"]), []).append(row)
        ordered = [
            node
            for domain in domains
            for node in [domain, *sorted(children.get(str(domain["slug"]), []), key=lambda row: row["position"])]
        ]
        try:
            taxonomy = Taxonomy.model_validate({"nodes": [self._node(row) for row in ordered]})
        except ValidationError as e:
            self.logger.error("The stored taxonomy is invalid: %s", e.errors()[0]["msg"])
            raise StorageReadError("taxonomy", f"invalid nodes ({e.errors()[0]['msg']})") from e
        self.logger.info("Stored taxonomy read: %d domains, %d nodes.", len(domains), len(ordered))
        return taxonomy

    async def read(self) -> Taxonomy:
        """Read the stored taxonomy, in its own transaction.

        Returns:
            Taxonomy: The stored taxonomy (see `load`).

        Raises:
            StorageReadError: If the taxonomy cannot be read.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                return await self.load(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy cannot be read: %s", e)
            raise StorageReadError("taxonomy", str(e)) from e

    async def revision(self, connection: AsyncConnection) -> Tuple[Optional[int], int]:
        """Read the revision of the taxonomy and the largest label identifier.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            Tuple[Optional[int], int]: The revision, `None` before the first seed, then the largest identifier of the
                source labels (0 without labels).
        """
        largest = select(func.coalesce(func.max(self.labels.c.id), 0)).scalar_subquery()
        row = (await connection.execute(select(largest, self.state.c.revision).select_from(self.state))).first()
        if row is None:
            self.logger.debug("The taxonomy is not seeded.")
            largest_id = await connection.scalar(select(func.coalesce(func.max(self.labels.c.id), 0)))
            return None, int(largest_id or 0)
        return int(row[1]), int(row[0])

    async def bump(self, connection: AsyncConnection) -> int:
        """Increment the revision of the taxonomy, telling the writers to reload their caches.

        Args:
            connection (AsyncConnection): The connection, in a transaction.

        Returns:
            int: The new revision.
        """
        statement = upsert(self.state).values(id=1, revision=1)
        revision = await connection.scalar(
            statement.on_conflict_do_update(
                index_elements=[self.state.c.id], set_={"revision": self.state.c.revision + 1}
            ).returning(self.state.c.revision)
        )
        self.logger.info("Taxonomy revision %d.", revision)
        return int(revision or 0)

    async def add_node(
        self,
        name_en: str,
        parent_slug: Optional[str] = None,
        name_ru: str = "",
        name_zh: str = "",
        description_en: str = "",
    ) -> str:
        """Add a node by hand: a category under a domain, or a domain.

        Args:
            name_en (str): Its English name.
            parent_slug (Optional[str]): Its domain, `None` to add a domain.
            name_ru (str): Its Russian name, empty to show the English one.
            name_zh (str): Its Chinese name, empty to show the English one.
            description_en (str): Its one-line description.

        Returns:
            str: The slug of the new node (from its English name).

        Raises:
            StorageWriteError: If the node cannot be added (e.g. its parent is not a domain, or its name is taken).
        """
        name = " ".join(name_en.split())
        try:
            async with self.database.connect() as connection, connection.begin():
                if parent_slug is not None and (await self._node_row(connection, parent_slug))["parent_slug"]:
                    self.logger.error("The node %r is not a domain: no category can be added under it.", parent_slug)
                    raise StorageWriteError(f"taxonomy node {parent_slug}", "a category must be under a domain")
                slug = await self._new_slug(connection, name)
                position = await connection.scalar(
                    select(func.coalesce(func.max(self.nodes.c.position), -1) + 1).where(
                        self.nodes.c.parent_slug.is_(None)
                        if parent_slug is None
                        else self.nodes.c.parent_slug == parent_slug
                    )
                )
                await connection.execute(
                    self.nodes.insert().values(
                        slug=slug,
                        parent_slug=parent_slug,
                        name_en=name,
                        name_ru=name_ru.strip(),
                        name_zh=name_zh.strip(),
                        description_en=description_en.strip(),
                        position=int(position or 0),
                        origin=NodeOrigin.USER.value,
                        edited=True,
                    )
                )
                await self.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy node %r cannot be added: %s", name, e)
            raise StorageWriteError(f"taxonomy node {name}", str(e)) from e
        self.logger.info("Taxonomy node %s added under %s.", slug, parent_slug or "the root")
        return slug

    async def update_node(
        self, slug: str, name_en: str, name_ru: str = "", name_zh: str = "", description_en: str = ""
    ) -> List[str]:
        """Rename a node and change its description by hand.

        Args:
            slug (str): The node.
            name_en (str): Its English name.
            name_ru (str): Its Russian name.
            name_zh (str): Its Chinese name.
            description_en (str): Its one-line description.

        Returns:
            List[str]: The nodes whose items must be categorized again (none: the items store the slugs).

        Raises:
            StorageWriteError: If the node does not exist or its name is taken.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._node_row(connection, slug)
                await connection.execute(
                    update(self.nodes)
                    .where(self.nodes.c.slug == slug)
                    .values(
                        name_en=" ".join(name_en.split()),
                        name_ru=name_ru.strip(),
                        name_zh=name_zh.strip(),
                        description_en=description_en.strip(),
                        edited=True,
                        updated_at=func.now(),
                    )
                )
                await self.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy node %s cannot be renamed: %s", slug, e)
            raise StorageWriteError(f"taxonomy node {slug}", str(e)) from e
        self.logger.info("Taxonomy node %s renamed %r.", slug, name_en)
        return []

    async def set_hidden(self, slug: str, hidden: bool) -> List[str]:
        """Hide a node from the pickers, or show it again (its items keep it).

        Args:
            slug (str): The node.
            hidden (bool): Whether it is hidden.

        Returns:
            List[str]: The nodes whose items must be categorized again (none).

        Raises:
            StorageWriteError: If the node does not exist.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._node_row(connection, slug)
                await connection.execute(
                    update(self.nodes)
                    .where(self.nodes.c.slug == slug)
                    .values(hidden=hidden, edited=True, updated_at=func.now())
                )
                await self.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy node %s cannot be %s: %s", slug, "hidden" if hidden else "shown", e)
            raise StorageWriteError(f"taxonomy node {slug}", str(e)) from e
        self.logger.info("Taxonomy node %s %s.", slug, "hidden" if hidden else "shown")
        return []

    async def move_node(self, slug: str, parent_slug: str) -> List[str]:
        """Move a category under another domain.

        Args:
            slug (str): The category.
            parent_slug (str): Its new domain.

        Returns:
            List[str]: The nodes whose items must be categorized again (the category: its domain changed).

        Raises:
            StorageWriteError: If the node is a domain, or the new parent is not a domain.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                node, parent = await self._node_row(connection, slug), await self._node_row(connection, parent_slug)
                if node["parent_slug"] is None or parent["parent_slug"] is not None:
                    self.logger.error("Only a category moves, under a domain (%s under %s).", slug, parent_slug)
                    raise StorageWriteError(f"taxonomy node {slug}", "only a category moves, under a domain")
                await connection.execute(
                    update(self.nodes)
                    .where(self.nodes.c.slug == slug)
                    .values(parent_slug=parent_slug, edited=True, updated_at=func.now())
                )
                await self.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy node %s cannot be moved: %s", slug, e)
            raise StorageWriteError(f"taxonomy node {slug}", str(e)) from e
        self.logger.info("Taxonomy node %s moved under %s.", slug, parent_slug)
        return [slug]

    async def merge_node(self, slug: str, target_slug: str) -> List[str]:
        """Merge a node into another one: its label links move to the other node, and it is hidden.

        Args:
            slug (str): The merged node.
            target_slug (str): The node it is merged into.

        Returns:
            List[str]: The nodes whose items must be categorized again (both).

        Raises:
            StorageWriteError: If a node does not exist, or a node is merged into itself.
        """
        if slug == target_slug:
            self.logger.error("The taxonomy node %s cannot be merged into itself.", slug)
            raise StorageWriteError(f"taxonomy node {slug}", "a node cannot be merged into itself")
        links = self.links
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._node_row(connection, slug)
                await self._node_row(connection, target_slug)
                moved = select(links.c.label_id, links.c.excluded).where(links.c.node_slug == slug)
                for label_id, excluded in (await connection.execute(moved)).all():
                    statement = upsert(links).values(
                        label_id=label_id, node_slug=target_slug, source=LinkSource.USER.value, excluded=excluded
                    )
                    await connection.execute(statement.on_conflict_do_nothing())
                await connection.execute(delete(links).where(links.c.node_slug == slug))
                await connection.execute(
                    update(self.nodes)
                    .where(self.nodes.c.slug == slug)
                    .values(hidden=True, edited=True, updated_at=func.now())
                )
                await self.bump(connection)
        except SQLAlchemyError as e:
            self.logger.error("The taxonomy node %s cannot be merged into %s: %s", slug, target_slug, e)
            raise StorageWriteError(f"taxonomy node {slug}", str(e)) from e
        self.logger.info("Taxonomy node %s merged into %s.", slug, target_slug)
        return [slug, target_slug]
