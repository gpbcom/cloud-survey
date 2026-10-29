from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.compounding.data.entry_panel import EntryPanel
from models.cloud.enums import CloudProvider
from models.compounding.config.compounding_settings import CompoundingSettings


class FoundationShare:
    """The foundations of the categories and how much of them a provider holds (equation 6.13).

    Attributes:
        panel (EntryPanel): The entry years of the providers.
        settings (CompoundingSettings): How the data-driven foundations are found.
        logger (Logger): The covariate logger.

    Notes:
        - A curated foundation set comes from the configuration, the same for every provider.
        - A data-driven foundation of a category is a category most other kept providers entered strictly before it
          (at least the precedence share of those holding both, and at least the fewest providers of the settings).
          The provider explained is left out, so that its own order never explains itself.
        - The foundation share is the share of the foundations held `lag` years before, and the experience the mean
          years each foundation has been held at the end of the year before.
    """

    def __init__(self, panel: EntryPanel, settings: CompoundingSettings, logger: Optional[Logger] = None) -> None:
        """Initialize the covariate.

        Args:
            panel (EntryPanel): The entry years of the providers.
            settings (CompoundingSettings): How the data-driven foundations are found.
            logger (Optional[Logger]): The covariate logger.
        """
        self.panel = panel
        self.settings = settings
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _precedence(self, others: List[CloudProvider], column: int) -> List[Tuple[float, int, int]]:
        """Rank the categories other providers entered before a category.

        Args:
            others (List[CloudProvider]): The providers whose order counts.
            column (int): The category.

        Returns:
            List[Tuple[float, int, int]]: The precedence share, the providers holding both and the column of each
                candidate foundation meeting the thresholds, best first.
        """
        before = numpy.zeros(len(self.panel.categories))
        both = numpy.zeros(len(self.panel.categories))
        for provider in others:
            entries = self.panel.entries[provider]
            if not math.isfinite(entries[column]):
                continue
            held = numpy.isfinite(entries)
            both += held
            before += held & (entries < entries[column])
        both[column] = 0
        candidates: List[Tuple[float, int, int]] = []
        for other in numpy.flatnonzero(both >= self.settings.precedence_providers):
            share = float(before[other] / both[other])
            if share >= self.settings.precedence_share:
                candidates.append((share, int(both[other]), int(other)))
        return sorted(candidates, reverse=True)

    ############################
    # Publicly Exposed Methods #
    ############################

    def curated(self, sets: Dict[str, List[str]]) -> Dict[int, NDArray[numpy.intp]]:
        """Turn the curated foundation sets into columns.

        Args:
            sets (Dict[str, List[str]]): The foundations of each dependent category.

        Returns:
            Dict[int, NDArray[numpy.intp]]: The foundation columns of each dependent column (categories outside the
                kept domains dropped).
        """
        index = self.panel.index
        columns: Dict[int, NDArray[numpy.intp]] = {}
        for category, foundations in sets.items():
            kept = [index[slug] for slug in foundations if slug in index]
            if category in index and kept:
                columns[index[category]] = numpy.array(kept, dtype=numpy.intp)
            else:
                self.logger.warning("The foundation set of %s has no category in the kept domains.", category)
        return columns

    def data_driven(self, without: Optional[CloudProvider]) -> Dict[int, NDArray[numpy.intp]]:
        """Find the foundations of every category from the order the other providers entered them.

        Args:
            without (Optional[CloudProvider]): The provider left out, `None` to use every kept provider.

        Returns:
            Dict[int, NDArray[numpy.intp]]: The foundation columns of each category that has some.
        """
        others = [
            provider
            for provider in self.panel.config.kept()
            if provider is not without and provider in self.panel.entries
        ]
        columns: Dict[int, NDArray[numpy.intp]] = {}
        for column in range(len(self.panel.categories)):
            ranked = self._precedence(others, column)[: self.settings.data_driven_size]
            if ranked:
                columns[column] = numpy.array([other for _, _, other in ranked], dtype=numpy.intp)
        self.logger.debug("%d data-driven foundation sets without %s.", len(columns), without)
        return columns

    def share(self, provider: CloudProvider, foundations: NDArray[numpy.intp], year: int, lag: int) -> float:
        """Get the share of a category's foundations a provider held `lag` years before.

        Args:
            provider (CloudProvider): The provider.
            foundations (NDArray[numpy.intp]): The foundation columns.
            year (int): The year of the possible entry.
            lag (int): The years the foundations must have been held.

        Returns:
            float: The share held, from 0 to 1.
        """
        return float(numpy.mean(self.panel.held_at(provider, year - lag)[foundations]))

    def experience(self, provider: CloudProvider, foundations: NDArray[numpy.intp], year: int) -> float:
        """Get the mean years a provider has held a category's foundations at the end of the year before.

        Args:
            provider (CloudProvider): The provider.
            foundations (NDArray[numpy.intp]): The foundation columns.
            year (int): The year of the possible entry.

        Returns:
            float: The mean years held (a foundation not held counts for 0).
        """
        held_since = self.panel.entries[provider][foundations]
        years = numpy.where(numpy.isfinite(held_since), numpy.clip(year - held_since, 0, None), 0.0)
        return float(numpy.mean(years))
