from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from models.cloud.enums import CloudProvider


class CategoryDensity:
    """The proximity of the categories and the density of a provider's related categories (equation 6.4).

    Attributes:
        categories (List[str]): The categories, in column order.
        offers (Dict[CloudProvider, NDArray[numpy.bool_]]): The categories each catalogue offers today.
        cache (Dict[CloudProvider, NDArray[numpy.float64]]): The proximity matrix computed without each provider.
        logger (Logger): The density logger.

    Notes:
        - The proximity of two categories is the smaller of the two conditional probabilities that a catalogue
          offering one offers the other, over every stored catalogue (dated or not).
        - The catalogue of the provider explained is left out of the proximity, so that its own entries never explain
          themselves. The catalogues are today's: a provider entering a category late still counts in the
          proximity of earlier years (a look-ahead the results document states).
    """

    def __init__(
        self,
        categories: List[str],
        snapshot: Dict[CloudProvider, List[str]],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the density.

        Args:
            categories (List[str]): The categories, in column order.
            snapshot (Dict[CloudProvider, List[str]]): The categories each catalogue offers today.
            logger (Optional[Logger]): The density logger.
        """
        self.categories = categories
        self.logger = logger if logger else getLogger(__name__)
        index = {slug: position for position, slug in enumerate(categories)}
        self.offers: Dict[CloudProvider, NDArray[numpy.bool_]] = {}
        for provider, offered in snapshot.items():
            row = numpy.zeros(len(categories), dtype=bool)
            row[[index[slug] for slug in offered if slug in index]] = True
            self.offers[provider] = row
        self.cache: Dict[CloudProvider, NDArray[numpy.float64]] = {}

    ############################
    # Publicly Exposed Methods #
    ############################

    def proximity(self, without: CloudProvider) -> NDArray[numpy.float64]:
        """Get the proximity of every pair of categories, one catalogue left out.

        Args:
            without (CloudProvider): The catalogue left out.

        Returns:
            NDArray[numpy.float64]: The symmetric proximity matrix, zero on its diagonal.
        """
        if without in self.cache:
            return self.cache[without]
        rows = [offered for provider, offered in self.offers.items() if provider is not without]
        size = len(self.categories)
        if not rows:
            self.logger.warning("No other catalogue to compute the proximity of the categories.")
            self.cache[without] = numpy.zeros((size, size))
            return self.cache[without]
        matrix = numpy.array(rows, dtype=float)
        together = matrix.T @ matrix
        counts = numpy.diag(together).copy()
        with numpy.errstate(divide="ignore", invalid="ignore"):
            given = numpy.where(counts[None, :] > 0, together / counts[None, :], 0.0)
        proximity = numpy.minimum(given, given.T)
        numpy.fill_diagonal(proximity, 0.0)
        self.cache[without] = proximity
        self.logger.debug("Proximity computed without %s over %d catalogues.", without.value, len(rows))
        return proximity

    def density(self, provider: CloudProvider, held: NDArray[numpy.bool_], column: int) -> float:
        """Get the density of the related categories a provider holds around a category.

        Args:
            provider (CloudProvider): The provider explained (left out of the proximity).
            held (NDArray[numpy.bool_]): The categories it holds.
            column (int): The category.

        Returns:
            float: The proximity-weighted share of the related categories held, from 0 to 1.
        """
        weights = self.proximity(provider)[column]
        total = float(numpy.sum(weights))
        return float(numpy.sum(weights[held]) / total) if total > 0 else 0.0
