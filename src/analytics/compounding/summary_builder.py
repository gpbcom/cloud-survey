from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Sequence

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import Verdict
from models.compounding.results.fits.growth_fit import GrowthFit
from models.compounding.results.fits.heaps_fit import HeapsFit
from models.compounding.results.fits.regression_fit import RegressionFit
from models.compounding.results.scores.placebo_result import PlaceboResult
from models.compounding.results.scores.summary_row import SummaryRow
from models.compounding.results.scores.transfer_score import TransferScore


class SummaryBuilder:
    """Sum up what every model says about each provider and about the pooled fit.

    Attributes:
        PLACEBO (ClassVar[float]): The placebo p-value below which the foundations beat random sets.
        HINT (ClassVar[float]): The placebo p-value below which the foundations are a hint.
        min_events (int): The fewest entries for a verdict.
        logger (Logger): The builder logger.

    Notes:
        The verdict reads the foundation hazard first:
        - insufficient: fewer entries than the settings ask, or a fit that did not converge.
        - supports: a foundation coefficient whose interval is above zero and that beats the placebo (p < 0.05).
        - mixed: a positive foundation coefficient that is significant or beats the placebo at 10%, or a density
          coefficient whose interval is above zero.
        - against: otherwise.
    """

    PLACEBO: ClassVar[float] = 0.05
    HINT: ClassVar[float] = 0.10

    def __init__(self, min_events: int, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            min_events (int): The fewest entries for a verdict.
            logger (Optional[Logger]): The builder logger.
        """
        self.min_events = min_events
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _verdict(
        self, hazard: Optional[RegressionFit], entry: Optional[RegressionFit], placebo: Optional[PlaceboResult]
    ) -> Verdict:
        """Read the verdict of a provider.

        Args:
            hazard (Optional[RegressionFit]): Its foundation hazard.
            entry (Optional[RegressionFit]): Its density model.
            placebo (Optional[PlaceboResult]): Its placebo test.

        Returns:
            Verdict: What the models say.
        """
        if hazard is None or not hazard.converged or hazard.events < self.min_events:
            return Verdict.INSUFFICIENT
        foundations = hazard.estimate("foundations")
        density = entry.estimate("density") if entry and entry.converged else None
        p_value = placebo.p_value if placebo else None
        positive = foundations is not None and foundations.value > 0
        significant = foundations is not None and foundations.significant() and foundations.value > 0
        if significant and p_value is not None and p_value < self.PLACEBO:
            return Verdict.SUPPORTS
        if positive and (significant or (p_value is not None and p_value < self.HINT)):
            return Verdict.MIXED
        if density is not None and density.significant() and density.value > 0:
            return Verdict.MIXED
        return Verdict.AGAINST

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(
        self,
        providers: Sequence[Optional[CloudProvider]],
        excluded: Sequence[CloudProvider],
        heaps: List[HeapsFit],
        growth: List[GrowthFit],
        entry: List[RegressionFit],
        hazard: List[RegressionFit],
        placebo: List[PlaceboResult],
        transfer: List[TransferScore],
    ) -> List[SummaryRow]:
        """Build one summary row per provider, `None` standing for the pooled fit.

        Args:
            providers (Sequence[Optional[CloudProvider]]): The providers, `None` for the pooled fit.
            excluded (Sequence[CloudProvider]): The providers outside the public-cloud scope.
            heaps (List[HeapsFit]): The Heaps' law fits.
            growth (List[GrowthFit]): The growth fits.
            entry (List[RegressionFit]): The density models.
            hazard (List[RegressionFit]): The foundation hazards.
            placebo (List[PlaceboResult]): The placebo tests.
            transfer (List[TransferScore]): The predictions from AWS.

        Returns:
            List[SummaryRow]: The rows, in the order of the providers.
        """
        rows: List[SummaryRow] = []
        for provider in providers:
            own_heaps = next((fit for fit in heaps if fit.provider is provider), None)
            own_growth = next((fit for fit in growth if fit.provider is provider), None)
            own_entry = next((fit for fit in entry if fit.provider is provider), None)
            own_hazard = next((fit for fit in hazard if fit.provider is provider), None)
            own_placebo = next((test for test in placebo if test.provider is provider), None)
            own_transfer = next((score for score in transfer if score.provider is provider), None)
            converged = own_hazard is not None and own_hazard.converged
            rows.append(
                SummaryRow(
                    provider=provider,
                    excluded=provider in excluded,
                    events=own_hazard.events if own_hazard else 0,
                    heaps=own_heaps.slope if own_heaps else None,
                    growth=own_growth.estimate("size") if own_growth else None,
                    best_curve=own_growth.best if own_growth else None,
                    density=own_entry.estimate("density") if own_entry and own_entry.converged else None,
                    foundations=own_hazard.estimate("foundations") if own_hazard and converged else None,
                    experience=own_hazard.estimate("experience") if own_hazard and converged else None,
                    size=own_hazard.estimate("size") if own_hazard and converged else None,
                    share=own_hazard.estimate("share") if own_hazard and converged else None,
                    market=own_hazard.estimate("market") if own_hazard and converged else None,
                    placebo=own_placebo.p_value if own_placebo else None,
                    transfer=own_transfer.gain() if own_transfer else None,
                    verdict=self._verdict(own_hazard, own_entry, own_placebo),
                )
            )
        self.logger.debug("%d summary rows built.", len(rows))
        return rows
