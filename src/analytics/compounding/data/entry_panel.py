from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.data.dated_product import DatedProduct
from models.compounding.enums import ValueOrigin
from models.compounding.results.series.market_year import MarketYear
from models.compounding.results.series.provider_coverage import ProviderCoverage
from models.compounding.results.series.provider_year import ProviderYear


class EntryPanel:
    """The yearly catalogue of each provider and the year it entered each category.

    Attributes:
        data (CompoundingData): What the database holds.
        config (CompoundingConfig): The scope of the analysis.
        categories (List[str]): The categories kept, in taxonomy order (the columns of the entry years).
        index (Dict[str, int]): The column of each category.
        windows (Dict[CloudProvider, Tuple[int, int]]): The first and last year observed of each provider.
        entries (Dict[CloudProvider, NDArray[numpy.float64]]): The year each provider entered each category, infinite
            when it never did.
        sizes (Dict[CloudProvider, Dict[int, int]]): The products offered at the end of each year.
        launches (Dict[CloudProvider, Dict[int, int]]): The products launched in each year.
        held (Dict[CloudProvider, int]): The products counted as held at the start of the window.
        shares (Dict[Tuple[CloudProvider, int], Tuple[float, ValueOrigin]]): The market share of each provider-year.
        market (Dict[int, Tuple[float, ValueOrigin, bool]]): The market size, its origin and its perimeter break.
        logger (Logger): The panel logger.

    Notes:
        - The window of a provider starts at the start year of its public cloud (configuration), else at its first
          dated launch, and ends at the last complete year of the settings.
        - A product dated before the window, or dated only "on or before" (a feed start, a website record), is held at
          the start of the window: the categories it brings are not entries.
        - A category is entered the first year a product of the category is offered. A category entered at the start
          of the window is held from the start, not entered.
    """

    def __init__(self, data: CompoundingData, config: CompoundingConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the panel.

        Args:
            data (CompoundingData): What the database holds.
            config (CompoundingConfig): The scope of the analysis.
            logger (Optional[Logger]): The panel logger.
        """
        self.data = data
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.categories: List[str] = list(data.categories)
        self.index: Dict[str, int] = {slug: position for position, slug in enumerate(self.categories)}
        self.windows: Dict[CloudProvider, Tuple[int, int]] = {}
        self.entries: Dict[CloudProvider, NDArray[numpy.float64]] = {}
        self.sizes: Dict[CloudProvider, Dict[int, int]] = {}
        self.launches: Dict[CloudProvider, Dict[int, int]] = {}
        self.held: Dict[CloudProvider, int] = {}
        self.shares: Dict[Tuple[CloudProvider, int], Tuple[float, ValueOrigin]] = {
            (share.provider, share.year): (share.value, share.origin) for share in data.shares if share.provider
        }
        self.market: Dict[int, Tuple[float, ValueOrigin, bool]] = {
            point.year: (point.value, point.origin, point.perimeter_break) for point in data.market
        }

    ############################
    # Internal Helpers Methods #
    ############################

    def _window(self, provider: CloudProvider, products: List[DatedProduct]) -> Optional[Tuple[int, int]]:
        """Get the years a provider is observed.

        Args:
            provider (CloudProvider): The provider.
            products (List[DatedProduct]): Its dated products.

        Returns:
            Optional[Tuple[int, int]]: The first and last year, `None` when it leaves less than two years.
        """
        launched = [product.year for product in products if not product.held]
        first = self.config.start(provider) or min(launched or [product.year for product in products])
        last = self.config.settings.last_year
        if last - first < 1:
            self.logger.warning("%s is observed over less than two years: it is left out.", provider.value)
            return None
        return first, last

    def _timeline(self, provider: CloudProvider, products: List[DatedProduct], first: int, last: int) -> None:
        """Compute a provider's yearly catalogue and entry years.

        Args:
            provider (CloudProvider): The provider.
            products (List[DatedProduct]): Its dated products.
            first (int): The first year observed.
            last (int): The last year observed.
        """
        entries = numpy.full(len(self.categories), numpy.inf)
        sizes = dict.fromkeys(range(first, last + 1), 0)
        launches = dict.fromkeys(range(first, last + 1), 0)
        held = 0
        for product in products:
            year = first if product.held or product.year < first else product.year
            if year > last:
                continue
            held += year == first and (product.held or product.year < first)
            if not product.held and first <= product.year <= last:
                launches[product.year] += 1
            for offered in range(year, last + 1):
                if product.deleted is None or product.deleted > offered:
                    sizes[offered] += 1
            for slug in product.categories:
                column = self.index.get(slug)
                if column is not None:
                    entries[column] = min(entries[column], year)
        self.windows[provider] = (first, last)
        self.entries[provider] = entries
        self.sizes[provider] = sizes
        self.launches[provider] = launches
        self.held[provider] = held

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(self) -> EntryPanel:
        """Compute every provider's yearly catalogue and entry years.

        Returns:
            EntryPanel: The panel itself, filled.
        """
        by_provider: Dict[CloudProvider, List[DatedProduct]] = {}
        for product in self.data.products:
            by_provider.setdefault(product.provider, []).append(product)
        for provider, products in by_provider.items():
            window = self._window(provider, products)
            if window is not None:
                self._timeline(provider, products, *window)
        self.logger.info("Entry panel built: %d providers, %d categories.", len(self.windows), len(self.categories))
        return self

    def providers(self) -> List[CloudProvider]:
        """Get the providers with a window.

        Returns:
            List[CloudProvider]: The providers, in the order of the configuration then the excluded ones.
        """
        order = [*self.config.kept(), *(entry.provider for entry in self.config.excluded)]
        return [provider for provider in order if provider in self.windows]

    def size(self, provider: CloudProvider, year: int) -> int:
        """Get a provider's catalogue size at the end of a year.

        Args:
            provider (CloudProvider): The provider.
            year (int): The year.

        Returns:
            int: The products offered, 0 outside the window.
        """
        return self.sizes.get(provider, {}).get(year, 0)

    def share(self, provider: CloudProvider, year: int) -> Optional[float]:
        """Get a provider's cloud-market share in a year.

        Args:
            provider (CloudProvider): The provider.
            year (int): The year.

        Returns:
            Optional[float]: The share (%), `None` when unknown.
        """
        found = self.shares.get((provider, year))
        return found[0] if found else None

    def growth(self, year: int) -> Optional[float]:
        """Get the growth of the logarithm of the cloud-market size from the year before.

        Args:
            year (int): The year.

        Returns:
            Optional[float]: The growth, `None` when either size is unknown.
        """
        now, before = self.market.get(year), self.market.get(year - 1)
        if now is None or before is None or now[0] <= 0 or before[0] <= 0:
            return None
        return math.log(now[0]) - math.log(before[0])

    def birth(self, column: int, without: CloudProvider) -> float:
        """Get the first year another kept provider entered a category.

        Args:
            column (int): The category column.
            without (CloudProvider): The provider left out (the one being explained).

        Returns:
            float: The year, infinite when no other kept provider entered it.
        """
        years = [
            float(self.entries[provider][column])
            for provider in self.config.kept()
            if provider is not without and provider in self.entries
        ]
        return min(years, default=math.inf)

    def held_at(self, provider: CloudProvider, year: int) -> NDArray[numpy.bool_]:
        """Get the categories a provider offers at the end of a year.

        Args:
            provider (CloudProvider): The provider.
            year (int): The year (before the window: the categories held at its start).

        Returns:
            NDArray[numpy.bool_]: Whether each category is held.
        """
        first = self.windows[provider][0]
        return self.entries[provider] <= max(year, first)

    def provider_years(self) -> List[ProviderYear]:
        """Get the yearly catalogue of every provider.

        Returns:
            List[ProviderYear]: The catalogue of each provider and year, by provider then year.
        """
        years: List[ProviderYear] = []
        for provider in self.providers():
            first, last = self.windows[provider]
            for year in range(first, last + 1):
                share = self.shares.get((provider, year))
                years.append(
                    ProviderYear(
                        provider=provider,
                        year=year,
                        size=self.sizes[provider][year],
                        launches=self.launches[provider][year],
                        categories=int(numpy.sum(self.held_at(provider, year))),
                        share=share[0] if share else None,
                        share_origin=share[1] if share else ValueOrigin.NONE,
                    )
                )
        return years

    def market_years(self) -> List[MarketYear]:
        """Get the yearly cloud-market size.

        Returns:
            List[MarketYear]: The size of every year known, with its growth.
        """
        return [
            MarketYear(year=year, size_bn=size, origin=origin, growth=self.growth(year), perimeter_break=broken)
            for year, (size, origin, broken) in sorted(self.market.items())
        ]

    def coverage(self) -> List[ProviderCoverage]:
        """Get what the database holds for every provider.

        Returns:
            List[ProviderCoverage]: The coverage of each provider with a window.
        """
        excluded = {entry.provider for entry in self.config.excluded}
        rows: List[ProviderCoverage] = []
        for provider in self.providers():
            first, last = self.windows[provider]
            entries = self.entries[provider]
            rows.append(
                ProviderCoverage(
                    provider=provider,
                    excluded=provider in excluded,
                    products=sum(1 for product in self.data.products if product.provider is provider),
                    held=self.held[provider],
                    first=first,
                    last=last,
                    categories=int(numpy.sum(numpy.isfinite(entries))),
                    events=int(numpy.sum((entries > first) & (entries <= last))),
                    share_years=sum(1 for year in range(first, last + 1) if (provider, year) in self.shares),
                )
            )
        return rows
