from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import List, Optional

# Third Party Imports.
import numpy

# First Party Imports.
from analytics.drivers.matrix.driver_matrix import DriverMatrix
from analytics.drivers.panel.fixed_effects_demeaner import FixedEffectsDemeaner
from analytics.drivers.regression.driver_regression import DriverRegression, RegressionOutcome
from models.drivers.enums import DriverWarningKind
from models.drivers.results.driver_warning import DriverWarning


class PanelRegression:
    """Regress the yearly change of the target on the lagged changes of the criteria, with two-way fixed effects.

    Attributes:
        regression (DriverRegression): The fit and the split of the R².
        demeaner (FixedEffectsDemeaner): The provider and quarter effects.
        logger (Logger): The regression logger.

    Notes:
        The provider effect removes what is constant per provider (brand, country, age), the quarter effect the
        market-wide movement. The coefficients then read within-provider: how a provider's change of a criterion goes
        with its later change of the target. The R² is the within R² (after the effects). The lead tests (Granger)
        are run per criterion by the analysis, whether the regression runs or not.
    """

    def __init__(
        self,
        regression: Optional[DriverRegression] = None,
        demeaner: Optional[FixedEffectsDemeaner] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the regression.

        Args:
            regression (Optional[DriverRegression]): The fit and the split of the R².
            demeaner (Optional[FixedEffectsDemeaner]): The provider and quarter effects.
            logger (Optional[Logger]): The regression logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.regression = regression if regression else DriverRegression(logger=self.logger)
        self.demeaner = demeaner if demeaner else FixedEffectsDemeaner(self.logger)

    ############################
    # Publicly Exposed Methods #
    ############################

    def regress(self, matrix: DriverMatrix, bootstrap: int, seed: int) -> RegressionOutcome:
        """Regress the complete panel observations.

        Args:
            matrix (DriverMatrix): The panel observations (the changes over a year).
            bootstrap (int): The bootstrap resamples (0 for no interval).
            seed (int): The seed of the resampling.

        Returns:
            RegressionOutcome: The fit (`None` when skipped), the coefficients and the warnings.
        """
        rows = numpy.flatnonzero(matrix.complete_rows())
        providers = [matrix.providers[row] for row in rows]
        periods = [matrix.periods[row] for row in rows]
        warnings: List[DriverWarning] = []
        if len(set(providers)) < 2 or len(set(periods)) < 2:
            self.logger.warning(
                "The panel holds %d providers over %d quarters.", len(set(providers)), len(set(periods))
            )
            warnings.append(
                DriverWarning(
                    kind=DriverWarningKind.SHORT_PANEL,
                    message=f"The panel holds {len(set(providers))} providers over {len(set(periods))} quarters: "
                    "at least 2 of each are needed.",
                )
            )
            return None, [], warnings
        values = numpy.column_stack([matrix.y[rows], matrix.x[rows]])
        within = self.demeaner.demean(
            values, [self.demeaner.codes([provider.value for provider in providers]), self.demeaner.codes(periods)]
        )
        absorbed = len(set(providers)) + len(set(periods)) - 2
        fit, coefficients, found = self.regression.regress(
            within[:, 0], within[:, 1:], matrix.criteria, providers, bootstrap, seed, absorbed
        )
        self.logger.info(
            "Panel regression of %s: %d observations, %d providers.", matrix.target, len(rows), len(set(providers))
        )
        return fit, coefficients, warnings + found
