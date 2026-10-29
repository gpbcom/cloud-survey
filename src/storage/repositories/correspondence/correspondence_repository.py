from __future__ import annotations

# Standard Library Imports.
import zlib
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple, Union

# Third Party Imports.
from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Select,
    Table,
    and_,
    any_,
    bindparam,
    case,
    delete,
    func,
    literal,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import Executable

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.correspondence.enums import (
    CardinalityClass,
    ConceptSource,
    CoverageFilter,
    MatchStrength,
    MemberRole,
    ViewMode,
)
from models.correspondence.llm.concept_answer import ConceptAnswer
from models.correspondence.query.correspondence_bucket import CorrespondenceBucket
from models.correspondence.query.correspondence_query import CorrespondenceQuery
from models.correspondence.rows.bucket_service import BucketService
from models.correspondence.rows.concept_member import ConceptMember
from models.correspondence.rows.concept_row import ConceptRow
from models.correspondence.rows.correspondence_stats import CorrespondenceStats
from models.correspondence.rows.coverage_cell import CoverageCell
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.item_query_builder import ItemQueryBuilder
from storage.tables.base import Base
from storage.tables.correspondence.concept_member_row import ConceptMemberRow
from storage.tables.correspondence.correspondence_check_row import CorrespondenceCheckRow
from storage.tables.correspondence.service_concept_row import ServiceConceptRow
from storage.tables.items.product_row import ProductRow
from storage.tables.taxonomy.taxonomy_node_row import TaxonomyNodeRow


class CorrespondenceRepository:
    """Create, read, update, delete and list the service concepts shared by the providers, and check the matches.

    Attributes:
        LOCK_SPACE (ClassVar[int]): The first key of the advisory locks of the categories being matched.
        DESCRIPTION_LIMIT (ClassVar[int]): The largest number of description characters read per service.
        OTHER (ClassVar[str]): The slug of the last-resort category, never matched.
        database (Database): The open database.
        concepts (Table): The `service_concepts` table.
        members (Table): The `concept_members` table.
        checks (Table): The `correspondence_checks` table.
        products (Table): The `products` table.
        nodes (Table): The `taxonomy_nodes` table.
        builder (ItemQueryBuilder): The filters of the catalogue products.
        logger (Logger): The repository logger.

    Notes:
        - The services are matched within a taxonomy category (their categories, or their domains when they have
          none): a listed product is pending in a category until a check holds its current content fingerprint.
        - The language model only adds members: a member a person removed stays excluded, and what a person set is
          never changed by a later answer.
        - A concept is the aggregate root: `create` files its services with it, `update` renames it, `delete`
          removes it with its memberships, `list` reads the rows of the provider columns.
    """

    LOCK_SPACE: ClassVar[int] = 6
    DESCRIPTION_LIMIT: ClassVar[int] = 300
    OTHER: ClassVar[str] = "other"

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.concepts: Table = Base.metadata.tables[ServiceConceptRow.__tablename__]
        self.members: Table = Base.metadata.tables[ConceptMemberRow.__tablename__]
        self.checks: Table = Base.metadata.tables[CorrespondenceCheckRow.__tablename__]
        self.products: Table = Base.metadata.tables[ProductRow.__tablename__]
        self.nodes: Table = Base.metadata.tables[TaxonomyNodeRow.__tablename__]
        self.builder = ItemQueryBuilder(self.products, self.logger)
        self.logger.debug("Repository of the service correspondences ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _lock_keys(self, slug: str) -> Tuple[int, int]:
        """Get the two keys of the advisory lock of a category, as the signed integers PostgreSQL takes.

        Args:
            slug (str): The taxonomy category.

        Returns:
            Tuple[int, int]: The lock space, then the signed CRC-32 of the slug.
        """
        checksum = zlib.crc32(slug.encode("utf-8"))
        return self.LOCK_SPACE, checksum - (1 << 32) if checksum >= (1 << 31) else checksum

    def _buckets(self) -> ColumnElement[List[str]]:
        """Get the categories a product is matched in: its categories, else its domains.

        Returns:
            ColumnElement[List[str]]: The slugs.
        """
        products = self.products
        return case(
            (func.cardinality(products.c.service_categories) > 0, products.c.service_categories),
            else_=products.c.service_domains,
        )

    def _pending(self, attempts: int) -> Select[Tuple[int, str, str]]:
        """Select the listed products waiting to be matched in a category.

        Args:
            attempts (int): The number of failed attempts after which a product waits for its content to change.

        Returns:
            Select[Tuple[int, str, str]]: The product identifier, its provider and the category.
        """
        products, checks = self.products, self.checks
        slug = func.unnest(self._buckets()).label("slug")
        listed = (
            select(products.c.id, products.c.provider, products.c.fingerprint, slug)
            .where(products.c.deleted_at.is_(None))
            .subquery("listed")
        )
        return (
            select(listed.c.id, listed.c.provider, listed.c.slug)
            .join(self.nodes, self.nodes.c.slug == listed.c.slug)
            .outerjoin(checks, and_(checks.c.product_id == listed.c.id, checks.c.node_slug == listed.c.slug))
            .where(
                listed.c.slug != self.OTHER,
                checks.c.fingerprint.is_distinct_from(listed.c.fingerprint),
                func.coalesce(checks.c.llm_attempts, 0) < attempts,
            )
        )

    def _shared(self) -> Select[Tuple[str]]:
        """Select the categories holding listed services of two providers at least (the only ones matched).

        Returns:
            Select[Tuple[str]]: The slugs.
        """
        products = self.products
        slug = func.unnest(self._buckets()).label("slug")
        listed = select(products.c.provider, slug).where(products.c.deleted_at.is_(None)).subquery("shared")
        return select(listed.c.slug).group_by(listed.c.slug).having(func.count(func.distinct(listed.c.provider)) >= 2)

    def _member(self, row: RowMapping) -> ConceptMember:
        """Build a member from a joined row of the members and the products.

        Args:
            row (RowMapping): The row.

        Returns:
            ConceptMember: The member.
        """
        description = str(row["description"] or "")
        return ConceptMember.model_validate(
            {
                "product_id": row["product_id"],
                "provider": row["provider"],
                "name": row["product_name"],
                "description": description[: self.DESCRIPTION_LIMIT],
                "url": row["url"],
                "role": row["role"],
                "confidence": row["confidence"],
                "source": row["member_source"],
                "deleted": row["deleted_at"] is not None,
            }
        )

    def _concept_rows(self, rows: Sequence[RowMapping]) -> List[ConceptRow]:
        """Group joined rows of the concepts, members and products into concepts.

        Args:
            rows (Sequence[RowMapping]): The rows, one per member.

        Returns:
            List[ConceptRow]: The concepts, in the order of their first row.
        """
        heads: Dict[int, RowMapping] = {}
        members: Dict[int, List[ConceptMember]] = {}
        for row in rows:
            concept_id = int(str(row["concept_id"]))
            heads.setdefault(concept_id, row)
            members.setdefault(concept_id, []).append(self._member(row))
        self.logger.debug("%d member rows grouped into %d concepts.", len(rows), len(heads))
        return [
            ConceptRow.model_validate(
                {
                    "id": concept_id,
                    "name": head["concept_name"],
                    "description": head["concept_description"],
                    "node_slug": head["node_slug"],
                    "source": head["concept_source"],
                    "edited": head["edited"],
                    "members": members[concept_id],
                }
            )
            for concept_id, head in heads.items()
        ]

    def _member_selection(self) -> Select[Tuple[int, ...]]:
        """Select the members of the concepts with their concept and their product (the excluded ones left out).

        Returns:
            Select[Tuple[int, ...]]: The joined rows, by concept name then provider and product name.
        """
        concepts, members, products = self.concepts, self.members, self.products
        return (
            select(
                concepts.c.id.label("concept_id"),
                concepts.c.name.label("concept_name"),
                concepts.c.description.label("concept_description"),
                concepts.c.node_slug,
                concepts.c.source.label("concept_source"),
                concepts.c.edited,
                members.c.product_id,
                members.c.role,
                members.c.confidence,
                members.c.source.label("member_source"),
                products.c.provider,
                products.c.name.label("product_name"),
                products.c.description,
                products.c.url,
                products.c.deleted_at,
            )
            .select_from(concepts)
            .join(members, members.c.concept_id == concepts.c.id)
            .join(products, products.c.id == members.c.product_id)
            .where(members.c.excluded.is_(False))
            .order_by(func.lower(concepts.c.name), concepts.c.id, products.c.provider, func.lower(products.c.name))
        )

    def _keeps(self, concept: ConceptRow, query: CorrespondenceQuery) -> bool:
        """Tell whether a concept passes the filters computed over its services.

        Args:
            concept (ConceptRow): The concept, its services filtered already.
            query (CorrespondenceQuery): The query.

        Returns:
            bool: Whether the concept is shown.
        """
        columns, strength = query.columns, query.strength
        covered = concept.covered(columns, strength)
        if covered == 0:
            return False
        match query.coverage:
            case CoverageFilter.COMPLETE if covered < len(columns):
                return False
            case CoverageFilter.GAPS if covered < 2 or covered == len(columns):
                return False
            case CoverageFilter.UNIQUE if covered != 1:
                return False
        if query.cardinalities and concept.row_class(columns, strength) not in query.cardinalities:
            return False
        if query.search:
            wanted = query.search.casefold()
            names = [concept.name, *(member.name for member in concept.members)]
            return any(wanted in name.casefold() for name in names)
        return True

    async def _concepts(self, query: CorrespondenceQuery) -> List[ConceptRow]:
        """Read the concepts the AI matched, their services filtered.

        Args:
            query (CorrespondenceQuery): The columns and the filters.

        Returns:
            List[ConceptRow]: The concepts holding a service of a column at least, by name.

        Raises:
            StorageReadError: If the concepts cannot be read.
        """
        members = self.members
        statement = self._member_selection().where(
            *self.builder.filters(query.item_query()),
            or_(members.c.confidence >= query.min_confidence, members.c.source == ConceptSource.USER.value),
        )
        if query.strength is MatchStrength.EQUIVALENT:
            statement = statement.where(members.c.role == MemberRole.EQUIVALENT.value)
        if query.sources:
            statement = statement.where(members.c.source.in_([source.value for source in query.sources]))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The service concepts cannot be read: %s", e)
            raise StorageReadError("service concepts", str(e)) from e
        concepts = [concept for concept in self._concept_rows(rows) if self._keeps(concept, query)]
        self.logger.debug("%d service concepts read for %d columns.", len(concepts), len(query.columns))
        return concepts[: query.limit]

    async def _categories(self, query: CorrespondenceQuery) -> List[ConceptRow]:
        """Read the taxonomy categories as rows: the services of each provider filed under the same category.

        Args:
            query (CorrespondenceQuery): The columns and the filters (the AI filters do not apply).

        Returns:
            List[ConceptRow]: One read-only row per category holding a service of a column at least, by name (their
                identifiers number the rows, they are not stored concepts).

        Raises:
            StorageReadError: If the services cannot be read.
        """
        products, nodes = self.products, self.nodes
        slug = func.unnest(self._buckets()).label("slug")
        listed = (
            select(
                products.c.id,
                products.c.provider,
                products.c.name,
                products.c.description,
                products.c.url,
                products.c.deleted_at,
                slug,
            )
            .where(*self.builder.filters(query.item_query()))
            .subquery("listed")
        )
        statement = (
            select(listed, nodes.c.name_en, nodes.c.description_en)
            .join(nodes, nodes.c.slug == listed.c.slug)
            .where(listed.c.slug != self.OTHER)
            .order_by(func.lower(nodes.c.name_en), listed.c.provider, func.lower(listed.c.name))
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The services by category cannot be read: %s", e)
            raise StorageReadError("services by category", str(e)) from e
        heads: Dict[str, RowMapping] = {}
        members: Dict[str, List[ConceptMember]] = {}
        for row in rows:
            category = str(row["slug"])
            heads.setdefault(category, row)
            members.setdefault(category, []).append(
                ConceptMember(
                    product_id=int(row["id"]),
                    provider=CloudProvider(row["provider"]),
                    name=row["name"],
                    description=str(row["description"] or "")[: self.DESCRIPTION_LIMIT],
                    url=row["url"],
                    deleted=row["deleted_at"] is not None,
                )
            )
        categories = [
            ConceptRow(
                id=index,
                name=head["name_en"],
                description=head["description_en"],
                node_slug=category,
                members=members[category],
            )
            for index, (category, head) in enumerate(heads.items(), start=1)
        ]
        kept = [row for row in categories if self._keeps(row, query)]
        self.logger.debug("%d taxonomy categories read for %d columns.", len(kept), len(query.columns))
        return kept[: query.limit]

    async def _category_matches(self, providers: Sequence[str]) -> Tuple[Dict[Tuple[str, str], int], Dict[str, int]]:
        """Count, for each pair of providers, the services of the first filed under a category the second offers.

        Args:
            providers (Sequence[str]): The providers.

        Returns:
            Tuple[Dict[Tuple[str, str], int], Dict[str, int]]: The services of each ordered pair, then the listed
                services of each provider.

        Raises:
            StorageReadError: If the services cannot be read.
        """
        products = self.products
        slug = func.unnest(self._buckets()).label("slug")
        statement = select(products.c.id, products.c.provider, slug).where(
            products.c.deleted_at.is_(None), products.c.provider.in_(list(providers))
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The services by category cannot be counted: %s", e)
            raise StorageReadError("services by category", str(e)) from e
        offered: Dict[str, Set[str]] = {}
        services: Dict[str, Dict[int, Set[str]]] = {}
        for product_id, provider, category in rows:
            if category == self.OTHER:
                continue
            offered.setdefault(str(provider), set()).add(str(category))
            services.setdefault(str(provider), {}).setdefault(int(product_id), set()).add(str(category))
        listed = {
            str(provider): len({int(row_id) for row_id, owner, _ in rows if owner == provider})
            for provider in providers
        }
        matched = {
            (source, target): sum(
                bool(slugs & offered.get(target, set())) for slugs in services.get(source, {}).values()
            )
            for source in providers
            for target in providers
            if source != target
        }
        return matched, listed

    async def _fingerprints(self, connection: AsyncConnection, product_ids: Sequence[int]) -> Dict[int, bytes]:
        """Read the content fingerprints of products.

        Args:
            connection (AsyncConnection): The connection.
            product_ids (Sequence[int]): The products.

        Returns:
            Dict[int, bytes]: The fingerprint of each product found.
        """
        statement = select(self.products.c.id, self.products.c.fingerprint).where(
            self.products.c.id == any_(bindparam("ids", sorted(set(product_ids)), type_=ARRAY(BigInteger)))
        )
        fingerprints = {
            int(row_id): bytes(fingerprint) for row_id, fingerprint in (await connection.execute(statement)).all()
        }
        if len(fingerprints) < len(set(product_ids)):
            self.logger.warning(
                "%d of the %d products to check are no longer stored.",
                len(set(product_ids)) - len(fingerprints),
                len(set(product_ids)),
            )
        self.logger.debug("Fingerprints of %d products read.", len(fingerprints))
        return fingerprints

    async def _concept_id(self, connection: AsyncConnection, slug: str, answer: ConceptAnswer, known: Set[int]) -> int:
        """Get the concept of an answer: the existing one it names, the one of the same name, or a new one.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            slug (str): The taxonomy category.
            answer (ConceptAnswer): The answer.
            known (Set[int]): The concepts of the category.

        Returns:
            int: The concept identifier.
        """
        if answer.concept_id is not None and answer.concept_id in known:
            return answer.concept_id
        concepts = self.concepts
        found = await connection.scalar(
            select(concepts.c.id).where(
                func.coalesce(concepts.c.node_slug, "") == slug, func.lower(concepts.c.name) == answer.name.lower()
            )
        )
        if found is not None:
            return int(found)
        created = await connection.scalar(
            upsert(concepts)
            .values(name=answer.name, description=answer.description, node_slug=slug, source=ConceptSource.LLM.value)
            .returning(concepts.c.id)
        )
        self.logger.debug("Concept %r created in %s.", answer.name, slug)
        return int(str(created))

    async def _write_checks(
        self,
        connection: AsyncConnection,
        slug: str,
        product_ids: Sequence[int],
        error: Optional[str],
    ) -> None:
        """Record that products were matched in a category (or that the attempt failed).

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            slug (str): The taxonomy category.
            product_ids (Sequence[int]): The products.
            error (Optional[str]): Why the attempt failed, `None` when the products were matched.
        """
        fingerprints = await self._fingerprints(connection, product_ids) if error is None else {}
        rows = [
            {
                "product_id": product_id,
                "node_slug": slug,
                "fingerprint": fingerprints.get(product_id),
                "llm_attempts": 0 if error is None else 1,
                "llm_error": None if error is None else error[:2000],
            }
            for product_id in sorted(set(product_ids))
        ]
        if not rows:
            self.logger.debug("No check to record in %s.", slug)
            return
        checks = self.checks
        statement = upsert(checks).values(rows)
        excluded = statement.excluded
        await connection.execute(
            statement.on_conflict_do_update(
                index_elements=[checks.c.product_id, checks.c.node_slug],
                set_={
                    "fingerprint": excluded.fingerprint,
                    "checked_at": func.now(),
                    "llm_error": excluded.llm_error,
                    "llm_attempts": excluded.llm_attempts if error is None else checks.c.llm_attempts + 1,
                },
            )
        )
        self.logger.debug(
            "Checks of %d products recorded in %s (%s).", len(rows), slug, "matched" if error is None else "failed"
        )

    async def _edit(self, label: str, statement: Executable) -> None:
        """Run a change made by hand in its own transaction.

        Args:
            label (str): What is changed, for the logs and the error.
            statement (Executable): The statement.

        Raises:
            StorageWriteError: If the change cannot be written.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The %s cannot be written: %s", label, e)
            raise StorageWriteError(label, str(e)) from e
        self.logger.info("Correspondence changed by hand: %s.", label)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def lock(self, connection: AsyncConnection, slug: str) -> bool:
        """Take the session lock of a category being matched, without waiting.

        Args:
            connection (AsyncConnection): The connection holding the lock until `unlock` (or its end).
            slug (str): The taxonomy category.

        Returns:
            bool: Whether the lock was taken, `False` while another run matches the category.
        """
        first, second = self._lock_keys(slug)
        taken = bool(
            await connection.scalar(
                text("SELECT pg_try_advisory_lock(:first, :second)"), {"first": first, "second": second}
            )
        )
        self.logger.debug("Lock of the category %s %s.", slug, "taken" if taken else "held by another run")
        return taken

    async def unlock(self, connection: AsyncConnection, slug: str) -> None:
        """Release the session lock of a category.

        Args:
            connection (AsyncConnection): The connection holding the lock.
            slug (str): The taxonomy category.
        """
        first, second = self._lock_keys(slug)
        await connection.execute(text("SELECT pg_advisory_unlock(:first, :second)"), {"first": first, "second": second})
        self.logger.debug("Lock of the category %s released.", slug)

    async def pending_buckets(self, provider: Optional[CloudProvider] = None, attempts: int = 3) -> List[str]:
        """List the categories holding services to match, among services of two providers at least.

        Args:
            provider (Optional[CloudProvider]): Only the categories holding pending services of this provider.
            attempts (int): The number of failed attempts after which a service waits for its content to change.

        Returns:
            List[str]: The slugs, sorted.

        Raises:
            StorageReadError: If the categories cannot be read.
        """
        pending = self._pending(attempts).subquery("pending")
        wanted = select(pending.c.slug).where(pending.c.slug.in_(self._shared()))
        if provider is not None:
            wanted = wanted.where(pending.c.provider == provider.value)
        statement = wanted.distinct().order_by(pending.c.slug)
        try:
            async with self.database.connect() as connection:
                slugs = [str(value) for value in (await connection.execute(statement)).scalars()]
        except SQLAlchemyError as e:
            self.logger.error("The categories to match cannot be read: %s", e)
            raise StorageReadError("categories to match", str(e)) from e
        self.logger.debug("%d categories hold services to match.", len(slugs))
        return slugs

    async def bucket(self, slug: str, limit: int, attempts: int = 3) -> CorrespondenceBucket:
        """Read the services of a category waiting to be matched, with the concepts already found in it.

        Args:
            slug (str): The taxonomy category.
            limit (int): The largest number of pending services read.
            attempts (int): The number of failed attempts after which a service waits for its content to change.

        Returns:
            CorrespondenceBucket: The pending services, by provider then identifier, and the concepts.

        Raises:
            StorageReadError: If the category cannot be read.
        """
        pending = self._pending(attempts).subquery("pending")
        products = self.products
        services = (
            select(
                products.c.id,
                products.c.provider,
                products.c.name,
                products.c.description,
                products.c.catalogue_categories,
            )
            .join(pending, pending.c.id == products.c.id)
            .where(pending.c.slug == slug)
            .order_by(products.c.provider, products.c.id)
            .limit(limit)
        )
        concepts = self._member_selection().where(self.concepts.c.node_slug == slug)
        try:
            async with self.database.connect() as connection:
                service_rows = (await connection.execute(services)).all()
                concept_rows = (await connection.execute(concepts)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The services of the category %s cannot be read: %s", slug, e)
            raise StorageReadError(f"services of {slug}", str(e)) from e
        bucket = CorrespondenceBucket(
            slug=slug,
            pending=[
                BucketService(
                    product_id=int(row_id),
                    provider=CloudProvider(provider),
                    name=name,
                    description=str(description or "")[: self.DESCRIPTION_LIMIT],
                    labels=list(labels or []),
                )
                for row_id, provider, name, description, labels in service_rows
            ],
            concepts=self._concept_rows(concept_rows),
        )
        self.logger.debug("%s: %d services to match, %d concepts.", slug, len(bucket.pending), len(bucket.concepts))
        return bucket

    async def apply_answer(self, slug: str, answers: Sequence[ConceptAnswer], product_ids: Sequence[int]) -> int:
        """Write the concepts the language model filed services of a category under, and check the services.

        Args:
            slug (str): The taxonomy category.
            answers (Sequence[ConceptAnswer]): The concepts of the answer.
            product_ids (Sequence[int]): The services sent (the members of the answer naming other services are left
                out): they are all checked, filed or not.

        Returns:
            int: The number of services filed under a concept.

        Raises:
            StorageWriteError: If the answer cannot be written.

        Notes:
            A member already stored (filed by a person, or removed by one) is never changed.
        """
        sent = set(product_ids)
        concepts, members = self.concepts, self.members
        added = 0
        try:
            async with self.database.connect() as connection, connection.begin():
                known = set(
                    (await connection.execute(select(concepts.c.id).where(concepts.c.node_slug == slug))).scalars()
                )
                for answer in answers:
                    kept = [member for member in answer.members if member.id in sent]
                    if not kept or not answer.name:
                        continue
                    concept_id = await self._concept_id(connection, slug, answer, known)
                    known.add(concept_id)
                    rows = [
                        {
                            "concept_id": concept_id,
                            "product_id": member.id,
                            "role": member.role.value,
                            "confidence": member.confidence,
                            "source": ConceptSource.LLM.value,
                        }
                        for member in {member.id: member for member in kept}.values()
                    ]
                    result = await connection.execute(
                        upsert(members)
                        .values(rows)
                        .on_conflict_do_nothing(index_elements=[members.c.concept_id, members.c.product_id])
                    )
                    added += max(result.rowcount, 0)
                await self._write_checks(connection, slug, product_ids, None)
        except SQLAlchemyError as e:
            self.logger.error("The correspondences of the category %s cannot be written: %s", slug, e)
            raise StorageWriteError(f"correspondences of {slug}", str(e)) from e
        self.logger.info("%s: %d services matched, %d filed under concepts.", slug, len(sent), added)
        return added

    async def release(self, slug: str, product_ids: Sequence[int], error: str) -> None:
        """Record a failed attempt to match services of a category (they are tried again, three times at most).

        Args:
            slug (str): The taxonomy category.
            product_ids (Sequence[int]): The services sent.
            error (str): Why the attempt failed.

        Raises:
            StorageWriteError: If the attempt cannot be recorded.
        """
        try:
            async with self.database.connect() as connection, connection.begin():
                await self._write_checks(connection, slug, product_ids, error)
        except SQLAlchemyError as e:
            self.logger.error("The failed match of the category %s cannot be recorded: %s", slug, e)
            raise StorageWriteError(f"checks of {slug}", str(e)) from e
        self.logger.warning("%s: %d services not matched: %s", slug, len(product_ids), error)

    async def list(self, query: CorrespondenceQuery) -> List[ConceptRow]:
        """List the rows of the provider columns: the concepts matched by the AI, or the taxonomy categories.

        Args:
            query (CorrespondenceQuery): The columns, the mode and the filters.

        Returns:
            List[ConceptRow]: The rows holding a service of a column at least, by name.

        Raises:
            StorageReadError: If the rows cannot be read.
        """
        self.logger.debug("Reading the correspondence rows of %d columns by %s.", len(query.columns), query.mode)
        if query.mode is ViewMode.CATEGORIES:
            return await self._categories(query)
        return await self._concepts(query)

    async def read(self, concept_id: int) -> Optional[ConceptRow]:
        """Read a concept with every service filed under it (deleted ones included).

        Args:
            concept_id (int): The concept.

        Returns:
            Optional[ConceptRow]: The concept, `None` when it does not exist or holds no service.

        Raises:
            StorageReadError: If the concept cannot be read.
        """
        statement = self._member_selection().where(self.concepts.c.id == concept_id)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The service concept %d cannot be read: %s", concept_id, e)
            raise StorageReadError(f"service concept {concept_id}", str(e)) from e
        concepts = self._concept_rows(rows)
        return concepts[0] if concepts else None

    async def services(self, slug: str, limit: int = 500) -> List[ConceptMember]:
        """Read the listed services of a category, for filing one under a concept by hand.

        Args:
            slug (str): The taxonomy category (or domain).
            limit (int): The largest number of services read.

        Returns:
            List[ConceptMember]: The services, by provider then name.

        Raises:
            StorageReadError: If the services cannot be read.
        """
        products = self.products
        statement = (
            select(products.c.id, products.c.provider, products.c.name, products.c.description, products.c.url)
            .where(products.c.deleted_at.is_(None), literal(slug) == any_(self._buckets()))
            .order_by(products.c.provider, func.lower(products.c.name))
            .limit(limit)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The services of the category %s cannot be read: %s", slug, e)
            raise StorageReadError(f"services of {slug}", str(e)) from e
        return [
            ConceptMember(
                product_id=int(row_id),
                provider=CloudProvider(provider),
                name=name,
                description=str(description or "")[: self.DESCRIPTION_LIMIT],
                url=url,
                source=ConceptSource.USER,
            )
            for row_id, provider, name, description, url in rows
        ]

    async def stats(self, query: CorrespondenceQuery) -> CorrespondenceStats:
        """Count the concepts and services of the provider columns.

        Args:
            query (CorrespondenceQuery): The columns and the filters.

        Returns:
            CorrespondenceStats: The figures.

        Raises:
            StorageReadError: If the figures cannot be read.
        """
        concepts = await self.list(query)
        products = self.products
        services = select(func.count()).select_from(products).where(*self.builder.filters(query.item_query()))
        pending = self._pending(3).subquery("pending")
        columns = [provider.value for provider in query.columns]
        waiting = select(func.count(func.distinct(pending.c.id))).where(
            pending.c.provider.in_(columns), pending.c.slug.in_(self._shared())
        )
        try:
            async with self.database.connect() as connection:
                total = int(await connection.scalar(services) or 0)
                pending_count = int(await connection.scalar(waiting) or 0)
                last: Optional[datetime] = await connection.scalar(select(func.max(self.checks.c.checked_at)))
                stored = int(await connection.scalar(select(func.count()).select_from(self.concepts)) or 0)
        except SQLAlchemyError as e:
            self.logger.error("The correspondence figures cannot be read: %s", e)
            raise StorageReadError("correspondence figures", str(e)) from e
        matched = {
            member.product_id
            for concept in concepts
            if concept.covered(query.columns, query.strength) >= 2
            for provider in query.columns
            for member in concept.members_of(provider, query.strength)
        }
        stats = CorrespondenceStats(
            concepts=len(concepts),
            matched=len(matched),
            services=total,
            pending=pending_count,
            last_checked=last,
            stored=stored,
        )
        self.logger.debug(
            "Correspondence figures: %d concepts, %d of %d services matched.", len(concepts), len(matched), total
        )
        return stats

    async def coverage(
        self, providers: Sequence[CloudProvider], mode: ViewMode = ViewMode.CONCEPTS
    ) -> List[CoverageCell]:
        """Count, for each pair of providers, the services of the first having an equivalent at the second.

        Args:
            providers (Sequence[CloudProvider]): The providers.
            mode (ViewMode): Equivalent through a concept matched by the AI, or through a shared taxonomy category.

        Returns:
            List[CoverageCell]: One cell per ordered pair of distinct providers, in the order of the providers.

        Raises:
            StorageReadError: If the services cannot be counted.
        """
        values = [provider.value for provider in dict.fromkeys(providers)]
        if mode is ViewMode.CATEGORIES:
            by_category, totals_by_provider = await self._category_matches(values)
            return [
                CoverageCell(
                    source=CloudProvider(a),
                    target=CloudProvider(b),
                    matched=by_category.get((a, b), 0),
                    total=totals_by_provider.get(a, 0),
                )
                for a in values
                for b in values
                if a != b
            ]
        members, products = self.members, self.products
        first, second = members.alias("first_member"), members.alias("second_member")
        source, target = products.alias("source_product"), products.alias("target_product")
        pairs = (
            select(source.c.provider, target.c.provider, func.count(func.distinct(source.c.id)))
            .select_from(first)
            .join(source, source.c.id == first.c.product_id)
            .join(second, and_(second.c.concept_id == first.c.concept_id, second.c.product_id != first.c.product_id))
            .join(target, target.c.id == second.c.product_id)
            .where(
                first.c.excluded.is_(False),
                second.c.excluded.is_(False),
                source.c.deleted_at.is_(None),
                target.c.deleted_at.is_(None),
                source.c.provider.in_(values),
                target.c.provider.in_(values),
                source.c.provider != target.c.provider,
            )
            .group_by(source.c.provider, target.c.provider)
        )
        totals = (
            select(products.c.provider, func.count())
            .where(products.c.deleted_at.is_(None), products.c.provider.in_(values))
            .group_by(products.c.provider)
        )
        try:
            async with self.database.connect() as connection:
                matched = {(str(a), str(b)): int(count) for a, b, count in (await connection.execute(pairs)).all()}
                listed = {str(provider): int(count) for provider, count in (await connection.execute(totals)).all()}
        except SQLAlchemyError as e:
            self.logger.error("The correspondence coverage cannot be read: %s", e)
            raise StorageReadError("correspondence coverage", str(e)) from e
        cells = [
            CoverageCell(
                source=CloudProvider(a),
                target=CloudProvider(b),
                matched=matched.get((a, b), 0),
                total=listed.get(a, 0),
            )
            for a in values
            for b in values
            if a != b
        ]
        self.logger.debug("Coverage of %d providers counted.", len(values))
        return cells

    async def update(self, concept_id: int, name: str, description: Optional[str] = None) -> None:
        """Rename a concept by hand (the language model no longer renames it).

        Args:
            concept_id (int): The concept.
            name (str): Its new name.
            description (Optional[str]): Its new description, unchanged when `None`.

        Raises:
            StorageWriteError: If the concept cannot be renamed (e.g. another concept of its category has the name).
        """
        self.logger.debug("Renaming the concept %d to %r.", concept_id, name)
        values: Dict[str, Union[str, bool, ColumnElement[datetime]]] = {
            "name": " ".join(name.split()),
            "edited": True,
            "updated_at": func.now(),
        }
        if description is not None:
            values["description"] = " ".join(description.split())
        await self._edit(
            f"name of concept {concept_id}",
            update(self.concepts).where(self.concepts.c.id == concept_id).values(values),
        )

    async def link(self, concept_id: int, product_id: int, role: MemberRole = MemberRole.EQUIVALENT) -> None:
        """File a service under a concept by hand.

        Args:
            concept_id (int): The concept.
            product_id (int): The service.
            role (MemberRole): Whether it is equivalent or partial.

        Raises:
            StorageWriteError: If the service cannot be filed.
        """
        self.logger.debug("Filing the service %d under the concept %d as %s.", product_id, concept_id, role)
        members = self.members
        statement = upsert(members).values(
            concept_id=concept_id,
            product_id=product_id,
            role=role.value,
            confidence=100,
            source=ConceptSource.USER.value,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[members.c.concept_id, members.c.product_id],
            set_={"role": role.value, "confidence": 100, "source": ConceptSource.USER.value, "excluded": False},
        )
        await self._edit(f"service {product_id} of concept {concept_id}", statement)

    async def unlink(self, concept_id: int, product_id: int) -> None:
        """Remove a service from a concept by hand: the language model never files it there again.

        Args:
            concept_id (int): The concept.
            product_id (int): The service.

        Raises:
            StorageWriteError: If the service cannot be removed.
        """
        self.logger.debug("Removing the service %d from the concept %d.", product_id, concept_id)
        members = self.members
        statement = upsert(members).values(
            concept_id=concept_id, product_id=product_id, source=ConceptSource.USER.value, excluded=True
        )
        statement = statement.on_conflict_do_update(
            index_elements=[members.c.concept_id, members.c.product_id],
            set_={"source": ConceptSource.USER.value, "excluded": True},
        )
        await self._edit(f"removal of service {product_id} from concept {concept_id}", statement)

    async def merge(self, into: int, merged: int) -> None:
        """Merge a concept into another: its services move, then it is deleted.

        Args:
            into (int): The kept concept.
            merged (int): The concept merged into it.

        Raises:
            StorageWriteError: If the concepts cannot be merged.
        """
        if into == merged:
            return
        members = self.members
        moved = select(
            literal(into, BigInteger),
            members.c.product_id,
            members.c.role,
            members.c.confidence,
            members.c.source,
            members.c.excluded,
        ).where(members.c.concept_id == merged)
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(
                    upsert(members)
                    .from_select(["concept_id", "product_id", "role", "confidence", "source", "excluded"], moved)
                    .on_conflict_do_nothing(index_elements=[members.c.concept_id, members.c.product_id])
                )
                await connection.execute(delete(self.concepts).where(self.concepts.c.id == merged))
                await connection.execute(
                    update(self.concepts).where(self.concepts.c.id == into).values(edited=True, updated_at=func.now())
                )
        except SQLAlchemyError as e:
            self.logger.error("The concept %d cannot be merged into %d: %s", merged, into, e)
            raise StorageWriteError(f"merge of concept {merged}", str(e)) from e
        self.logger.info("Concept %d merged into %d by hand.", merged, into)

    async def create(self, name: str, slug: Optional[str], product_ids: Sequence[int]) -> int:
        """Create a concept by hand, with services.

        Args:
            name (str): Its name.
            slug (Optional[str]): The taxonomy category it belongs to.
            product_ids (Sequence[int]): Its services.

        Returns:
            int: The identifier of the new concept.

        Raises:
            StorageWriteError: If the concept cannot be created (e.g. its name is taken in the category).
        """
        concepts, members = self.concepts, self.members
        try:
            async with self.database.connect() as connection, connection.begin():
                concept_id = int(
                    str(
                        await connection.scalar(
                            upsert(concepts)
                            .values(
                                name=" ".join(name.split()),
                                node_slug=slug,
                                source=ConceptSource.USER.value,
                                edited=True,
                            )
                            .returning(concepts.c.id)
                        )
                    )
                )
                rows = [
                    {
                        "concept_id": concept_id,
                        "product_id": product_id,
                        "confidence": 100,
                        "source": ConceptSource.USER.value,
                    }
                    for product_id in sorted(set(product_ids))
                ]
                if rows:
                    await connection.execute(upsert(members).values(rows).on_conflict_do_nothing())
        except SQLAlchemyError as e:
            self.logger.error("The concept %r cannot be created: %s", name, e)
            raise StorageWriteError(f"concept {name}", str(e)) from e
        self.logger.info("Concept %r created by hand with %d services.", name, len(product_ids))
        return concept_id

    async def delete(self, concept_id: int) -> None:
        """Delete a concept (its services are no longer filed under it).

        Args:
            concept_id (int): The concept.

        Raises:
            StorageWriteError: If the concept cannot be deleted.
        """
        await self._edit(
            f"deletion of concept {concept_id}", delete(self.concepts).where(self.concepts.c.id == concept_id)
        )

    async def invalidate(self, slug: str) -> None:
        """Forget the matches of a category: its services are matched again by the next run.

        Args:
            slug (str): The taxonomy category.

        Raises:
            StorageWriteError: If the checks cannot be deleted.

        Notes:
            The concepts and their services are kept: the next answer adds to them.
        """
        await self._edit(f"checks of {slug}", delete(self.checks).where(self.checks.c.node_slug == slug))

    async def classes(self, query: CorrespondenceQuery) -> Dict[CardinalityClass, int]:
        """Count the concepts of each class over the provider columns, for the filter chips.

        Args:
            query (CorrespondenceQuery): The columns and the filters (its classes ignored).

        Returns:
            Dict[CardinalityClass, int]: The number of concepts of each class.
        """
        concepts = await self.list(query.model_copy(update={"cardinalities": [], "limit": 5000}))
        counts: Dict[CardinalityClass, int] = {}
        for concept in concepts:
            kind = concept.row_class(query.columns, query.strength)
            counts[kind] = counts.get(kind, 0) + 1
        self.logger.debug("%d concepts counted in %d classes.", len(concepts), len(counts))
        return counts

    async def sizes(self) -> Dict[CloudProvider, int]:
        """Count the listed services of each provider (the column presets pick the largest catalogues).

        Returns:
            Dict[CloudProvider, int]: The number of listed products of each provider holding one.

        Raises:
            StorageReadError: If the services cannot be counted.
        """
        products = self.products
        statement = (
            select(products.c.provider, func.count())
            .where(products.c.deleted_at.is_(None))
            .group_by(products.c.provider)
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The catalogue sizes cannot be read: %s", e)
            raise StorageReadError("catalogue sizes", str(e)) from e
        sizes = {CloudProvider(provider): int(count) for provider, count in rows if provider in set(CloudProvider)}
        self.logger.debug("Catalogue sizes of %d providers read.", len(sizes))
        return sizes
