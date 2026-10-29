from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import Callable, ClassVar, List, Optional, Sequence, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray
from scipy.optimize import curve_fit

# First Party Imports.
from analytics.compounding.data.entry_panel import EntryPanel
from analytics.compounding.estimators.curves.growth_curves import GrowthCurves
from analytics.compounding.estimators.curves.ordinary_least_squares import OrdinaryLeastSquares
from models.cloud.enums import CloudProvider
from models.compounding.enums import CurveKind, Specification
from models.compounding.results.fits.curve_fit import CurveFit
from models.compounding.results.fits.estimate import Estimate
from models.compounding.results.fits.growth_fit import GrowthFit

type Curve = Callable[..., NDArray[numpy.float64]]


class GrowthFitter:
    """Fit how a provider's catalogue grows: the linear launch rate (6.6) and the growth curves (6.7).

    Attributes:
        MIN_YEARS (ClassVar[int]): The fewest years of a curve fit.
        least_squares (OrdinaryLeastSquares): The least-squares estimator.
        logger (Logger): The fitter logger.

    Notes:
        - The linear rate regresses the launches of a year on the catalogue size at the end of the year before, the
          growth of the cloud market that year and, in S2, the market share of the year before.
        - The curves are fitted to the catalogue size with `scipy.optimize.curve_fit` and ranked by AIC
          (`n ln(RSS / n) + 2k`). When the market size is known on at least five years of the window, the four curves
          are fitted on those years only, so that the market rival (the catalogue as a power of the market size)
          competes on the same points. Otherwise the three own curves are fitted on the whole window.
    """

    MIN_YEARS: ClassVar[int] = 5

    def __init__(self, least_squares: OrdinaryLeastSquares, logger: Optional[Logger] = None) -> None:
        """Initialize the fitter.

        Args:
            least_squares (OrdinaryLeastSquares): The least-squares estimator.
            logger (Optional[Logger]): The fitter logger.
        """
        self.least_squares = least_squares
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _aic(self, observed: NDArray[numpy.float64], fitted: NDArray[numpy.float64], parameters: int) -> float:
        """Compute the Akaike information criterion of a fit.

        Args:
            observed (NDArray[numpy.float64]): The sizes observed.
            fitted (NDArray[numpy.float64]): The sizes fitted.
            parameters (int): The parameters fitted.

        Returns:
            float: The criterion.
        """
        rss = max(float(numpy.sum((observed - fitted) ** 2)), 1e-9)
        return observed.size * math.log(rss / observed.size) + 2 * parameters

    def _curve(
        self,
        kind: CurveKind,
        curve: Curve,
        names: Sequence[str],
        guess: Sequence[float],
        bounds: Tuple[Sequence[float], Sequence[float]],
        years: List[int],
        sizes: NDArray[numpy.float64],
    ) -> CurveFit:
        """Fit one curve to the catalogue sizes.

        Args:
            kind (CurveKind): The curve.
            curve (Curve): Its function of the years since the first year.
            names (Sequence[str]): The names of its parameters.
            guess (Sequence[float]): The starting values.
            bounds (Tuple[Sequence[float], Sequence[float]]): The bounds of the parameters.
            years (List[int]): The years fitted.
            sizes (NDArray[numpy.float64]): The sizes observed.

        Returns:
            CurveFit: The fit, without AIC when it fails.
        """
        elapsed = numpy.array(years, dtype=float) - years[0]
        try:
            values, covariance = curve_fit(curve, elapsed, sizes, p0=list(guess), bounds=bounds, maxfev=20000)
        except (RuntimeError, ValueError) as e:
            self.logger.warning("The %s curve did not fit: %s", kind.value, e)
            return CurveFit(kind=kind)
        fitted = curve(elapsed, *values)
        errors = numpy.sqrt(numpy.clip(numpy.diag(covariance), 0, None))
        parameters = [
            Estimate(
                name=name,
                value=float(value),
                low=float(value - 1.96 * error) if numpy.isfinite(error) else None,
                high=float(value + 1.96 * error) if numpy.isfinite(error) else None,
            )
            for name, value, error in zip(names, values, errors, strict=True)
        ]
        return CurveFit(
            kind=kind,
            aic=self._aic(sizes, fitted, len(values)),
            parameters=parameters,
            points=[(year, float(size)) for year, size in zip(years, fitted, strict=True)],
        )

    def _market_curve(self, years: List[int], sizes: NDArray[numpy.float64], market: List[float]) -> CurveFit:
        """Fit the catalogue as a power of the cloud-market size (the rival explanation).

        Args:
            years (List[int]): The years fitted.
            sizes (NDArray[numpy.float64]): The sizes observed.
            market (List[float]): The market size of each year.

        Returns:
            CurveFit: The fit, without AIC when a size is not positive.
        """
        if numpy.any(sizes <= 0):
            return CurveFit(kind=CurveKind.MARKET)
        exponent, constant = numpy.polyfit(numpy.log(market), numpy.log(sizes), 1)
        fitted = numpy.exp(constant + exponent * numpy.log(market))
        return CurveFit(
            kind=CurveKind.MARKET,
            aic=self._aic(sizes, fitted, 2),
            parameters=[
                Estimate(name="elasticity", value=float(exponent)),
                Estimate(name="constant", value=float(constant)),
            ],
            points=[(year, float(size)) for year, size in zip(years, fitted, strict=True)],
        )

    def _curves(self, panel: EntryPanel, provider: CloudProvider) -> List[CurveFit]:
        """Fit the growth curves of a provider's catalogue.

        Args:
            panel (EntryPanel): The yearly catalogues.
            provider (CloudProvider): The provider.

        Returns:
            List[CurveFit]: The curves fitted, none with too few years.
        """
        first, last = panel.windows[provider]
        window = list(range(first, last + 1))
        common = [year for year in window if year in panel.market]
        years = common if len(common) >= self.MIN_YEARS else window
        if len(years) < self.MIN_YEARS:
            self.logger.debug("Too few years to fit the growth curves of %s.", provider.value)
            return []
        sizes = numpy.array([panel.size(provider, year) for year in years], dtype=float)
        top = max(float(numpy.max(sizes)), 1.0)
        curves = GrowthCurves(float(sizes[0]), self.logger)
        span = float(years[-1] - years[0])
        launches = max(float(numpy.mean(numpy.diff(sizes))), 0.1)
        fits = [
            self._curve(
                CurveKind.EXPONENTIAL,
                curves.exponential,
                ("a", "b"),
                (launches, 0.05),
                ((-1e4, -1.0), (1e4, 2.0)),
                years,
                sizes,
            ),
            self._curve(
                CurveKind.LOGISTIC,
                curves.logistic,
                ("ceiling", "rate", "middle"),
                (1.5 * top, 0.3, span / 2),
                ((top, 1e-3, -50.0), (50 * top, 5.0, 100.0)),
                years,
                sizes,
            ),
            self._curve(
                CurveKind.BASS,
                curves.bass,
                ("potential", "steady", "imitation"),
                (max(top - float(sizes[0]), 1.0), 0.03, 0.3),
                ((1e-6, 1e-5, 0.0), (50 * top + 1, 1.0, 5.0)),
                years,
                sizes,
            ),
        ]
        if years == common:
            fits.append(self._market_curve(years, sizes, [panel.market[year][0] for year in years]))
        return fits

    ############################
    # Publicly Exposed Methods #
    ############################

    def fit(self, panel: EntryPanel, provider: CloudProvider, specification: Specification) -> GrowthFit:
        """Fit how a provider's catalogue grows.

        Args:
            panel (EntryPanel): The yearly catalogues.
            provider (CloudProvider): The provider.
            specification (Specification): The controls held constant.

        Returns:
            GrowthFit: The linear rate and the growth curves.
        """
        first, last = panel.windows[provider]
        share = specification is Specification.SHARE
        names = ["size", "share", "market"] if share else ["size", "market"]
        rows: List[List[float]] = []
        launches: List[float] = []
        for year in range(first + 1, last + 1):
            growth = panel.growth(year)
            held_share = panel.share(provider, year - 1)
            if growth is None or (share and held_share is None):
                continue
            rows.append(
                [
                    float(panel.size(provider, year - 1)),
                    *([held_share] if share and held_share is not None else []),
                    growth,
                ]
            )
            launches.append(float(panel.launches[provider][year]))
        fitted = self.least_squares.fit(numpy.array(launches), numpy.array(rows).reshape(len(rows), len(names)), names)
        curves = self._curves(panel, provider)
        ranked = [curve for curve in curves if curve.aic is not None]
        best = min(ranked, key=lambda curve: curve.aic or 0.0).kind if ranked else None
        self.logger.debug("Growth of %s fitted on %d years, best curve %s.", provider.value, len(launches), best)
        return GrowthFit(
            provider=provider,
            years=len(launches),
            linear=fitted[1] if fitted else [],
            r2=fitted[2] if fitted else None,
            curves=curves,
            best=best,
        )
