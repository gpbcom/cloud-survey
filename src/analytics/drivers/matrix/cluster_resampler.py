from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from models.cloud.enums import CloudProvider


class ClusterResampler:
    """Draw the bootstrap resamples of the observations, a provider at a time.

    Attributes:
        logger (Logger): The resampler logger.

    Notes:
        A resample draws as many providers as there are, with replacement, and takes every observation of each one
        drawn. In a cross-section a provider is one observation, so this is the usual bootstrap. In a panel the
        quarters of a provider move together, which keeps their correlation in the intervals.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the resampler.

        Args:
            logger (Optional[Logger]): The resampler logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def samples(self, providers: List[CloudProvider], count: int, seed: int) -> List[NDArray[numpy.intp]]:
        """Draw resamples.

        Args:
            providers (List[CloudProvider]): The provider of each observation.
            count (int): How many resamples.
            seed (int): The seed (the same seed draws the same resamples).

        Returns:
            List[NDArray[numpy.intp]]: The indices of the observations of each resample.
        """
        clusters: Dict[CloudProvider, List[int]] = {}
        for index, provider in enumerate(providers):
            clusters.setdefault(provider, []).append(index)
        groups = [numpy.asarray(rows, dtype=numpy.intp) for rows in clusters.values()]
        if not groups or count <= 0:
            return []
        generator = numpy.random.default_rng(seed)
        samples = [
            numpy.concatenate([groups[drawn] for drawn in generator.integers(0, len(groups), len(groups))])
            for _ in range(count)
        ]
        self.logger.debug("Drew %d resamples of %d providers.", count, len(groups))
        return samples
