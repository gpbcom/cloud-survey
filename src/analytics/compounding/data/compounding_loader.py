from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Set, Tuple

# First Party Imports.
from models.cloud.enums import CloudProvider, MarketRegion, MarketSegment
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.data.dated_product import DatedProduct
from models.compounding.data.year_value import YearValue
from models.compounding.enums import ValueOrigin
from models.history.chronology import Chronology
from models.markets.enums import ShareSource
from models.markets.values.market_share_value import MarketShareValue
from models.stats.market_report import MarketReport
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.storage import Storage


class CompoundingLoader:
    """Read from the database what the service-compounding models fit.

    Attributes:
        SEGMENT (ClassVar[str]): The market-share segment of the cloud market.
        AREA (ClassVar[str]): The worldwide area of the market shares.
        STATISTICS (ClassVar[str]): The market statistics source.
        SOURCES (ClassVar[Dict[ShareSource, ValueOrigin]]): The share sources read, with what they are.
        config (CompoundingConfig): The scope of the analysis.
        chronology (Chronology): The companies of the chronology (their cloud providers).
        logger (Logger): The loader logger.

    Notes:
        - The products are the dated catalogue products of the providers analysed and excluded, with their categories
          of the kept domains only. A product without any is left out.
        - A share is the mean of the year's quarterly shares (Synergy, crawled), or the hand-typed yearly point of the
          dossier when Synergy gives none that year.
        - The market size of a year is the sum of its four quarters, a missing quarter interpolated between its
          neighbours, then the curated size of the configuration.
        - It is the only class of the analysis opening the database: the models never do.
    """

    SEGMENT: ClassVar[str] = "cloud"
    AREA: ClassVar[str] = "ww"
    STATISTICS: ClassVar[str] = "synergy"
    SOURCES: ClassVar[Dict[ShareSource, ValueOrigin]] = {
        ShareSource.SYNERGY: ValueOrigin.CRAWLED,
        ShareSource.MANUAL: ValueOrigin.MANUAL,
    }

    def __init__(self, config: CompoundingConfig, chronology: Chronology, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            config (CompoundingConfig): The scope of the analysis.
            chronology (Chronology): The companies of the chronology.
            logger (Optional[Logger]): The loader logger.
        """
        self.config = config
        self.chronology = chronology
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _kept_categories(self, taxonomy: Taxonomy) -> List[str]:
        """Get the categories of the kept domains.

        Args:
            taxonomy (Taxonomy): The stored taxonomy.

        Returns:
            List[str]: The visible categories of the kept domains, in taxonomy order.
        """
        categories: List[str] = []
        for domain in self.config.domains:
            categories.extend(node.slug for node in taxonomy.children(domain) if not node.hidden)
        if not categories:
            self.logger.warning("No category in the kept domains: the taxonomy may not be seeded.")
        return categories

    async def _products(
        self, storage: Storage, kept: Set[str]
    ) -> Tuple[List[DatedProduct], Dict[CloudProvider, List[str]]]:
        """Read the dated products of the providers analysed, and the categories every catalogue offers today.

        Args:
            storage (Storage): The open storage.
            kept (Set[str]): The categories kept.

        Returns:
            Tuple[List[DatedProduct], Dict[CloudProvider, List[str]]]: The dated products, and the categories each
                catalogue offers today.
        """
        analysed = {*self.config.kept(), *(entry.provider for entry in self.config.excluded)}
        held_caveats = set(self.config.settings.held_caveats)
        products: List[DatedProduct] = []
        snapshot: Dict[CloudProvider, List[str]] = {}
        for provider in CloudProvider:
            read = await storage.catalogues.items(provider)
            if read is None:
                continue
            offered: Set[str] = set()
            for item in read[1]:
                categories = [slug for slug in item.service_categories if slug in kept]
                if not categories:
                    continue
                if item.deleted_at is None:
                    offered.update(categories)
                if provider not in analysed or item.added_at is None:
                    continue
                products.append(
                    DatedProduct(
                        provider=provider,
                        year=item.added_at.year,
                        held=item.added_caveat in held_caveats,
                        categories=categories,
                        deleted=item.deleted_at.year if item.deleted_at else None,
                    )
                )
            if offered:
                snapshot[provider] = sorted(offered)
        self.logger.debug("%d dated products read, %d catalogues in the snapshot.", len(products), len(snapshot))
        return products, snapshot

    def _shares(self, values: List[MarketShareValue]) -> List[YearValue]:
        """Turn the stored cloud-market shares into yearly shares of the providers.

        Args:
            values (List[MarketShareValue]): The worldwide cloud shares.

        Returns:
            List[YearValue]: The share of each provider and year, a crawled share preferred to a hand-typed one.
        """
        providers = {company.key: company.provider for company in self.chronology.companies if company.provider}
        points: Dict[Tuple[CloudProvider, int, ValueOrigin], List[float]] = defaultdict(list)
        for value in values:
            origin = self.SOURCES.get(value.source)
            provider = providers.get(value.company or "")
            if origin is None or provider is None:
                continue
            points[(provider, value.period.year, origin)].append(value.value)
        shares: Dict[Tuple[CloudProvider, int], YearValue] = {}
        for origin in (ValueOrigin.CRAWLED, ValueOrigin.MANUAL):
            for (provider, year, found_origin), found in points.items():
                if found_origin is origin and (provider, year) not in shares:
                    shares[(provider, year)] = YearValue(
                        provider=provider, year=year, value=sum(found) / len(found), origin=origin
                    )
        return sorted(shares.values(), key=lambda share: (str(share.provider), share.year))

    def _quarters(self, reports: List[MarketReport]) -> Tuple[Dict[int, float], Set[int]]:
        """Read the quarterly worldwide sizes of the cloud infrastructure services market.

        Args:
            reports (List[MarketReport]): The stored reports.

        Returns:
            Tuple[Dict[int, float], Set[int]]: The size of each quarter known (numbered `4 * year + quarter - 1`)
                and the years with a perimeter break.
        """
        sizes: Dict[int, float] = {}
        breaks: Set[int] = set()
        for report in reports:
            worldwide = report.region is MarketRegion.WORLDWIDE
            if not worldwide or report.segment is not MarketSegment.CLOUD_INFRASTRUCTURE or len(report.period) != 6:
                continue
            year = int(report.period[:4])
            if report.methodology_break:
                breaks.add(year)
            if report.market_size_bn is not None and report.currency == "USD":
                sizes[4 * year + int(report.period[5]) - 1] = report.market_size_bn
        return sizes, breaks

    def _interpolated(self, sizes: Dict[int, float], quarter: int) -> Optional[float]:
        """Interpolate a missing quarter geometrically between the nearest known quarters around it.

        Args:
            sizes (Dict[int, float]): The size of each quarter known.
            quarter (int): The missing quarter.

        Returns:
            Optional[float]: The size, `None` outside the span of the known quarters.
        """
        before = max((known for known in sizes if known < quarter), default=None)
        after = min((known for known in sizes if known > quarter), default=None)
        if before is None or after is None:
            return None
        weight = (quarter - before) / (after - before)
        return float(sizes[before] * (sizes[after] / sizes[before]) ** weight)

    def _market(self, reports: List[MarketReport]) -> List[YearValue]:
        """Turn the stored Synergy reports into yearly sizes of the worldwide cloud market.

        Args:
            reports (List[MarketReport]): The stored reports.

        Returns:
            List[YearValue]: The size of each year known, crawled sizes first, then the curated ones.

        Notes:
            A year is the sum of its four quarters. A missing quarter inside the span of the known ones is
            interpolated geometrically between its neighbours, and the year is then marked interpolated.
        """
        quarters, breaks = self._quarters(reports)
        result: Dict[int, YearValue] = {}
        for year in sorted({quarter // 4 for quarter in quarters}):
            values: List[float] = []
            filled = False
            for quarter in range(4 * year, 4 * year + 4):
                value = quarters.get(quarter)
                if value is None:
                    value = self._interpolated(quarters, quarter)
                    filled = True
                if value is None:
                    break
                values.append(value)
            if len(values) == 4:
                result[year] = YearValue(
                    year=year,
                    value=sum(values),
                    origin=ValueOrigin.INTERPOLATED if filled else ValueOrigin.CRAWLED,
                    perimeter_break=year in breaks,
                )
            else:
                self.logger.debug("The cloud market size of %d is unknown: quarters missing at an end.", year)
        for year, curated in self.config.market_sizes().items():
            if year not in result:
                result[year] = YearValue(year=year, value=curated, origin=ValueOrigin.MANUAL)
        return [result[year] for year in sorted(result)]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, storage: Storage) -> CompoundingData:
        """Read everything the compounding models fit.

        Args:
            storage (Storage): The open storage.

        Returns:
            CompoundingData: The dated products, the shares, the market sizes, today's categories of every catalogue
                and the categories kept.

        Raises:
            StorageReadError: If the database cannot be read.
        """
        taxonomy = await storage.taxonomy.list()
        categories = self._kept_categories(taxonomy)
        products, snapshot = await self._products(storage, set(categories))
        shares = self._shares(await storage.shares.list(self.SEGMENT, self.AREA))
        statistics = await storage.statistics.read(self.STATISTICS)
        if statistics is None:
            self.logger.warning("No %s statistics stored: crawl the cloud market history first.", self.STATISTICS)
        market = self._market(statistics.reports if statistics else [])
        self.logger.info(
            "Compounding data read: %d dated products, %d shares, %d market years, %d categories.",
            len(products),
            len(shares),
            len(market),
            len(categories),
        )
        return CompoundingData(
            products=products, shares=shares, market=market, snapshot=snapshot, categories=categories
        )
