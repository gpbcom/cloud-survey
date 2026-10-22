from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from sqlalchemy import ColumnElement, Integer, Select, Table, and_, cast, column, exists, func, select, true
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.cloud.enums import CloudProvider, DeliveryMethod, MarketRegion, MarketSegment, SoftwareCategory
from models.drivers.enums import MetricSource, ProviderMetric
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from models.stats.market_statistics import MarketStatistics
from storage.engine.database import Database
from storage.exception import StorageReadError
from storage.repositories.statistics_repository import StatisticsRepository
from storage.tables.base import Base
from storage.tables.correspondence.concept_member_row import ConceptMemberRow
from storage.tables.items.product_row import ProductRow
from storage.tables.items.software_row import SoftwareRow


class MetricDeriver:
    """Compute the criteria and targets of the driver analysis from the crawled data.

    Attributes:
        STATISTICS_SOURCE (ClassVar[str]): The market statistics read (Synergy Research Group).
        IGNORED_NODES (ClassVar[Tuple[str, ...]]): The taxonomy nodes not counted as breadth.
        DOMAIN_SHARES (ClassVar[Dict[ProviderMetric, Tuple[str, ...]]]): The domains of each catalogue share.
        DELIVERY_SHARES (ClassVar[Dict[ProviderMetric, DeliveryMethod]]): The delivery of each marketplace share.
        LEADERS (ClassVar[Tuple[CloudProvider, ...]]): The providers the parity is measured against.
        MENTION_PROVIDERS (ClassVar[Dict[str, CloudProvider]]): The provider of each name the articles mention.
        database (Database): The open database.
        statistics (StatisticsRepository): The market statistics.
        products (Table): The `products` table.
        software (Table): The `software` table.
        members (Table): The `concept_members` table.
        logger (Logger): The deriver logger.

    Notes:
        - The catalogue and marketplace measures (sizes, breadth, mixes, parity) are a snapshot: they go on the
          quarter of the computation. The launches, deletions and new listings go on the quarter of their dates.
        - The market share and revenue come from the worldwide cloud infrastructure figures, for the providers
          Synergy quantifies. The parity is computed only once the AI matched services.
    """

    STATISTICS_SOURCE: ClassVar[str] = "synergy"
    IGNORED_NODES: ClassVar[Tuple[str, ...]] = ("other", "unclassified")
    DOMAIN_SHARES: ClassVar[Dict[ProviderMetric, Tuple[str, ...]]] = {
        ProviderMetric.AI_SHARE: ("ai-machine-learning",),
        ProviderMetric.DATA_SHARE: ("databases", "data-analytics"),
        ProviderMetric.SECURITY_SHARE: ("security-services", "identity-access"),
        ProviderMetric.COMPUTE_SHARE: ("compute", "containers-kubernetes"),
    }
    DELIVERY_SHARES: ClassVar[Dict[ProviderMetric, DeliveryMethod]] = {
        ProviderMetric.SAAS_SHARE: DeliveryMethod.SAAS,
        ProviderMetric.VM_SHARE: DeliveryMethod.VIRTUAL_MACHINE,
        ProviderMetric.AI_MODEL_SHARE: DeliveryMethod.AI_MODEL,
    }
    LEADERS: ClassVar[Tuple[CloudProvider, ...]] = (CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.GCP)
    MENTION_PROVIDERS: ClassVar[Dict[str, CloudProvider]] = {
        "amazon": CloudProvider.AWS,
        "aws": CloudProvider.AWS,
        "microsoft": CloudProvider.AZURE,
        "azure": CloudProvider.AZURE,
        "google": CloudProvider.GCP,
        "ibm": CloudProvider.IBM,
        "oracle": CloudProvider.ORACLE,
        "alibaba": CloudProvider.ALIBABA,
        "huawei": CloudProvider.HUAWEI,
        "tencent": CloudProvider.TENCENT,
        "baidu": CloudProvider.BAIDU,
        "china telecom": CloudProvider.CTYUN,
        "china mobile": CloudProvider.ECLOUD,
        "ovhcloud": CloudProvider.OVH,
        "scaleway": CloudProvider.SCALEWAY,
        "deutsche telekom": CloudProvider.TCLOUD,
        "yandex": CloudProvider.YANDEX_CLOUD,
    }

    def __init__(self, database: Database, statistics: StatisticsRepository, logger: Optional[Logger] = None) -> None:
        """Initialize the deriver.

        Args:
            database (Database): The open database.
            statistics (StatisticsRepository): The market statistics.
            logger (Optional[Logger]): The deriver logger.
        """
        self.database = database
        self.statistics = statistics
        self.logger = logger if logger else getLogger(__name__)
        self.products: Table = Base.metadata.tables[ProductRow.__tablename__]
        self.software: Table = Base.metadata.tables[SoftwareRow.__tablename__]
        self.members: Table = Base.metadata.tables[ConceptMemberRow.__tablename__]
        self.logger.debug("Metric deriver ready.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _quarter(self, moment: datetime) -> str:
        """Write the quarter of a moment.

        Args:
            moment (datetime): The moment.

        Returns:
            str: Its quarter, `YYYYQn`.
        """
        return f"{moment.year}Q{(moment.month - 1) // 3 + 1}"

    def _value(self, provider: str, period: str, metric: ProviderMetric, value: float) -> Optional[ProviderMetricValue]:
        """Build a derived measure, for a known provider only.

        Args:
            provider (str): The provider value.
            period (str): The quarter.
            metric (ProviderMetric): The metric.
            value (float): The measure.

        Returns:
            Optional[ProviderMetricValue]: The measure, `None` for an unknown provider.
        """
        if provider not in {known.value for known in CloudProvider}:
            return None
        return ProviderMetricValue(
            provider=CloudProvider(provider), period=period, metric=metric, value=value, source=MetricSource.DERIVED
        )

    def _domains_overlap(self, slugs: Tuple[str, ...]) -> ColumnElement[bool]:
        """Select the products filed under one of some domains.

        Args:
            slugs (Tuple[str, ...]): The domains.

        Returns:
            ColumnElement[bool]: The condition.
        """
        return self.products.c.service_domains.overlap(cast(list(slugs), self.products.c.service_domains.type))

    def _catalogue_statements(self) -> List[Tuple[ProviderMetric, Select[str, float]]]:
        """Build the statements of the catalogue snapshot (one value per provider each).

        Returns:
            List[Tuple[ProviderMetric, Select[str, float]]]: The metric and its statement.
        """
        products = self.products
        listed = products.c.deleted_at.is_(None)
        total = func.count()
        domain = func.unnest(products.c.service_domains).table_valued("slug").render_derived("domain")
        category = func.unnest(products.c.service_categories).table_valued("slug").render_derived("category")
        statements: List[Tuple[ProviderMetric, Select[str, float]]] = [
            (
                ProviderMetric.PRODUCTS,
                select(products.c.provider, cast(total, Integer)).where(listed).group_by(products.c.provider),
            ),
            (
                ProviderMetric.DOMAINS,
                select(products.c.provider, func.count(func.distinct(domain.c.slug)))
                .select_from(products.join(domain, true()))
                .where(listed, domain.c.slug.not_in(self.IGNORED_NODES))
                .group_by(products.c.provider),
            ),
            (
                ProviderMetric.CATEGORIES,
                select(products.c.provider, func.count(func.distinct(category.c.slug)))
                .select_from(products.join(category, true()))
                .where(listed, category.c.slug.not_in(self.IGNORED_NODES))
                .group_by(products.c.provider),
            ),
            (
                ProviderMetric.DEVELOPER_SHARE,
                select(
                    products.c.provider,
                    func.avg(cast(products.c.categories.any_() == SoftwareCategory.DEVELOPER_TOOL.value, Integer)),
                )
                .where(listed)
                .group_by(products.c.provider),
            ),
        ]
        for metric, slugs in self.DOMAIN_SHARES.items():
            statements.append(
                (
                    metric,
                    select(products.c.provider, func.avg(cast(self._domains_overlap(slugs), Integer)))
                    .where(listed)
                    .group_by(products.c.provider),
                )
            )
        return statements

    def _marketplace_statements(self) -> List[Tuple[ProviderMetric, Select[str, float]]]:
        """Build the statements of the marketplace snapshot (one value per provider each).

        Returns:
            List[Tuple[ProviderMetric, Select[str, float]]]: The metric and its statement.
        """
        software = self.software
        listed = software.c.deleted_at.is_(None)
        statements: List[Tuple[ProviderMetric, Select[str, float]]] = [
            (
                ProviderMetric.MARKETPLACE_SIZE,
                select(software.c.provider, func.count()).where(listed).group_by(software.c.provider),
            ),
            (
                ProviderMetric.PUBLISHERS,
                select(software.c.provider, func.count(func.distinct(software.c.publisher)))
                .where(listed)
                .group_by(software.c.provider),
            ),
        ]
        for metric, delivery in self.DELIVERY_SHARES.items():
            statements.append(
                (
                    metric,
                    select(software.c.provider, func.avg(cast(software.c.delivery == delivery.value, Integer)))
                    .where(listed)
                    .group_by(software.c.provider),
                )
            )
        return statements

    def _parity_statement(self) -> Select[str, float]:
        """Build the statement of the parity: the share of the listed products sharing a concept with a leader.

        Returns:
            Select[str, float]: The provider and its parity.
        """
        products, members = self.products, self.members
        own, other = members.alias("own_member"), members.alias("other_member")
        leader = products.alias("leader_product")
        matched = exists(
            select(own.c.product_id)
            .join(other, and_(other.c.concept_id == own.c.concept_id, other.c.product_id != own.c.product_id))
            .join(leader, leader.c.id == other.c.product_id)
            .where(
                own.c.product_id == products.c.id,
                own.c.excluded.is_(False),
                other.c.excluded.is_(False),
                leader.c.deleted_at.is_(None),
                leader.c.provider.in_([provider.value for provider in self.LEADERS]),
                leader.c.provider != products.c.provider,
            )
        )
        return (
            select(products.c.provider, func.avg(cast(matched, Integer)))
            .where(products.c.deleted_at.is_(None))
            .group_by(products.c.provider)
        )

    def _dated_statement(self, table: Table, moment: ColumnElement[datetime]) -> Select[str, int, int, int]:
        """Build the statement counting items per provider and quarter of a date.

        Args:
            table (Table): The items table.
            moment (ColumnElement[datetime]): The date (added or deleted).

        Returns:
            Select[str, int, int, int]: The provider, year, quarter and count.
        """
        year = cast(func.extract("year", moment), Integer).label("year")
        quarter = cast(func.extract("quarter", moment), Integer).label("quarter")
        return (
            select(table.c.provider, year, quarter, func.count())
            .where(moment.is_not(None))
            .group_by(table.c.provider, column("year", Integer), column("quarter", Integer))
        )

    def _synergy(self, statistics: Optional[MarketStatistics]) -> List[ProviderMetricValue]:
        """Read the market shares, the revenues and the mentions of the market statistics.

        Args:
            statistics (Optional[MarketStatistics]): The stored market statistics.

        Returns:
            List[ProviderMetricValue]: The quarterly measures of the providers Synergy names.
        """
        if statistics is None:
            return []
        values: List[ProviderMetricValue] = []
        mentions: Dict[Tuple[CloudProvider, str], int] = {}
        for report in statistics.reports:
            if not ProviderMetricValue.PERIOD.match(report.period):
                continue
            worldwide = report.region is MarketRegion.WORLDWIDE and report.segment is MarketSegment.CLOUD_INFRASTRUCTURE
            for share in report.shares:
                provider = share.player.provider
                if provider is None or not worldwide:
                    continue
                values.append(
                    ProviderMetricValue(
                        provider=provider,
                        period=report.period,
                        metric=ProviderMetric.MARKET_SHARE,
                        value=share.share_pct,
                        source=MetricSource.SYNERGY,
                        source_url=report.source_url,
                    )
                )
                if report.market_size_bn is not None:
                    values.append(
                        ProviderMetricValue(
                            provider=provider,
                            period=report.period,
                            metric=ProviderMetric.REVENUE,
                            value=share.share_pct / 100 * report.market_size_bn,
                            source=MetricSource.SYNERGY,
                            source_url=report.source_url,
                        )
                    )
            for mention in report.mentions:
                named = self.MENTION_PROVIDERS.get(mention.name.casefold())
                if named is not None:
                    mentions[(named, report.period)] = mentions.get((named, report.period), 0) + 1
        values += [
            ProviderMetricValue(
                provider=provider,
                period=period,
                metric=ProviderMetric.MENTIONS,
                value=count,
                source=MetricSource.SYNERGY,
            )
            for (provider, period), count in sorted(mentions.items())
        ]
        return values

    ############################
    # Publicly Exposed Methods #
    ############################

    async def derive(self, now: datetime) -> List[ProviderMetricValue]:
        """Compute every derived measure.

        Args:
            now (datetime): When the snapshot is taken (its quarter receives the snapshot measures).

        Returns:
            List[ProviderMetricValue]: The derived measures (source derived), then the Synergy ones (source synergy).

        Raises:
            StorageReadError: If the crawled data cannot be read.
        """
        period = self._quarter(now)
        snapshot = [*self._catalogue_statements(), *self._marketplace_statements()]
        dated: List[Tuple[ProviderMetric, Select[str, int, int, int]]] = [
            (ProviderMetric.LAUNCHES, self._dated_statement(self.products, self.products.c.added_at)),
            (ProviderMetric.DELETIONS, self._dated_statement(self.products, self.products.c.deleted_at)),
            (ProviderMetric.NEW_LISTINGS, self._dated_statement(self.software, self.software.c.added_at)),
        ]
        values: List[ProviderMetricValue] = []
        try:
            async with self.database.connect() as connection:
                for metric, statement in snapshot:
                    for provider, value in (await connection.execute(statement)).all():
                        if value is not None and (measure := self._value(str(provider), period, metric, float(value))):
                            values.append(measure)
                if await connection.scalar(select(func.count()).select_from(self.members)):
                    for provider, value in (await connection.execute(self._parity_statement())).all():
                        if value is not None and (
                            measure := self._value(str(provider), period, ProviderMetric.PARITY, float(value))
                        ):
                            values.append(measure)
                for metric, history in dated:
                    for provider, year, quarter, count in (await connection.execute(history)).all():
                        if measure := self._value(str(provider), f"{year}Q{quarter}", metric, float(count)):
                            values.append(measure)
        except SQLAlchemyError as e:
            self.logger.error("The provider metrics cannot be derived: %s", e)
            raise StorageReadError("provider metrics", str(e)) from e
        values += self._synergy(await self.statistics.load(self.STATISTICS_SOURCE))
        self.logger.info("%d provider metrics derived for %s.", len(values), period)
        return values
