from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.compounding.data.covariates.category_density import CategoryDensity
from analytics.compounding.data.covariates.foundation_share import FoundationShare
from analytics.compounding.data.entry_panel import EntryPanel
from analytics.compounding.data.risk_set import RiskSet
from models.cloud.enums import CloudProvider
from models.compounding.enums import FitKind, Specification

type FoundationColumns = Dict[int, NDArray[numpy.intp]]


class RiskSetBuilder:
    """Build the provider-category-years at risk of an entry, with the covariates of a model.

    Attributes:
        ENTRY (ClassVar[List[str]]): The covariates of the density model (6.5).
        HAZARD (ClassVar[List[str]]): The covariates of the foundation hazard (6.13).
        CONTROLS (ClassVar[List[str]]): The controls of every model.
        SHARE (ClassVar[str]): The market-share control of specification S2.
        panel (EntryPanel): The entry years and yearly catalogues.
        density (CategoryDensity): The density of the related categories.
        foundations (FoundationShare): The foundations held.
        logger (Logger): The builder logger.

    Notes:
        - A provider is at risk of entering a category from the second year of its window until it enters it (the
          entry year is the last row).
        - The covariates of a year are measured at the end of the year before (`lag` years before for the
          foundations): the catalogue size (log of 1 + products), the market share (S2), the density of related
          categories, the foundation share and the experience (log of 1 + mean years held). The growth of the cloud
          market is the year's own, and the age of the category the years since another kept provider entered it
          (log of 1 + years, 0 before).
        - Rows without the growth of the market, or without the share in S2, are left out.
        - A pooled risk set adds one effect per provider but the first.
    """

    ENTRY: ClassVar[List[str]] = ["density"]
    HAZARD: ClassVar[List[str]] = ["foundations", "experience"]
    CONTROLS: ClassVar[List[str]] = ["size", "market", "age"]
    SHARE: ClassVar[str] = "share"

    def __init__(
        self,
        panel: EntryPanel,
        density: CategoryDensity,
        foundations: FoundationShare,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the builder.

        Args:
            panel (EntryPanel): The entry years and yearly catalogues.
            density (CategoryDensity): The density of the related categories.
            foundations (FoundationShare): The foundations held.
            logger (Optional[Logger]): The builder logger.
        """
        self.panel = panel
        self.density = density
        self.foundations = foundations
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _names(self, kind: FitKind, specification: Specification, providers: Sequence[CloudProvider]) -> List[str]:
        """Name the covariate columns of a model.

        Args:
            kind (FitKind): The model.
            specification (Specification): The controls held constant.
            providers (Sequence[CloudProvider]): The providers fitted.

        Returns:
            List[str]: The column names.
        """
        names = [*(self.ENTRY if kind is FitKind.ENTRY else self.HAZARD), *self.CONTROLS]
        if specification is Specification.SHARE:
            names.append(self.SHARE)
        return names + [f"fe:{provider.value}" for provider in providers[1:]]

    def _row(
        self,
        kind: FitKind,
        provider: CloudProvider,
        column: int,
        year: int,
        lag: int,
        sets: FoundationColumns,
    ) -> List[float]:
        """Compute the model covariates of a provider-category-year.

        Args:
            kind (FitKind): The model.
            provider (CloudProvider): The provider.
            column (int): The category.
            year (int): The year.
            lag (int): The years the foundations must have been held.
            sets (FoundationColumns): The foundation columns of each dependent category.

        Returns:
            List[float]: The model covariates, controls excluded.
        """
        if kind is FitKind.ENTRY:
            return [self.density.density(provider, self.panel.held_at(provider, year - 1), column)]
        foundations = sets[column]
        return [
            self.foundations.share(provider, foundations, year, lag),
            math.log1p(self.foundations.experience(provider, foundations, year)),
        ]

    def _controls(self, provider: CloudProvider, column: int, year: int, share: bool) -> Optional[List[float]]:
        """Compute the controls of a provider-category-year.

        Args:
            provider (CloudProvider): The provider.
            column (int): The category.
            year (int): The year.
            share (bool): Whether the market share is a control.

        Returns:
            Optional[List[float]]: The controls, `None` when one is unknown (the row is left out).
        """
        growth = self.panel.growth(year)
        if growth is None:
            return None
        birth = self.panel.birth(column, provider)
        age = math.log1p(max(0.0, year - birth)) if math.isfinite(birth) else 0.0
        controls = [math.log1p(self.panel.size(provider, year - 1)), growth, age]
        if share:
            value = self.panel.share(provider, year - 1)
            if value is None:
                return None
            controls.append(value)
        return controls

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(
        self,
        kind: FitKind,
        providers: Sequence[CloudProvider],
        specification: Specification,
        lag: int,
        sets: Dict[CloudProvider, FoundationColumns],
    ) -> RiskSet:
        """Build the risk set of a model.

        Args:
            kind (FitKind): The model.
            providers (Sequence[CloudProvider]): The providers fitted (several: a pooled fit with provider effects).
            specification (Specification): The controls held constant.
            lag (int): The years the foundations must have been held (hazard only).
            sets (Dict[CloudProvider, FoundationColumns]): The foundation columns of each provider (hazard only).

        Returns:
            RiskSet: The rows at risk, possibly none.
        """
        fitted = [provider for provider in providers if provider in self.panel.windows]
        names = self._names(kind, specification, fitted)
        share = specification is Specification.SHARE
        x: List[List[float]] = []
        y: List[float] = []
        owners: List[CloudProvider] = []
        columns: List[int] = []
        years: List[int] = []
        for position, provider in enumerate(fitted):
            first, last = self.panel.windows[provider]
            entries = self.panel.entries[provider]
            dependents = range(len(self.panel.categories)) if kind is FitKind.ENTRY else sorted(sets.get(provider, {}))
            effects = [1.0 if position == other else 0.0 for other in range(1, len(fitted))]
            for column in dependents:
                if entries[column] <= first:
                    continue
                end = min(last, int(entries[column])) if math.isfinite(entries[column]) else last
                for year in range(first + 1, end + 1):
                    controls = self._controls(provider, column, year, share)
                    if controls is None:
                        continue
                    x.append(
                        self._row(
                            kind, provider, column, year, 1 if kind is FitKind.ENTRY else lag, sets.get(provider, {})
                        )
                        + controls
                        + effects
                    )
                    y.append(1.0 if entries[column] == year else 0.0)
                    owners.append(provider)
                    columns.append(column)
                    years.append(year)
        risk_set = RiskSet(
            names=names,
            x=numpy.array(x, dtype=float).reshape(len(y), len(names)),
            y=numpy.array(y, dtype=float),
            providers=owners,
            columns=numpy.array(columns, dtype=numpy.intp),
            years=numpy.array(years, dtype=numpy.intp),
        )
        self.logger.debug(
            "%s risk set of %d providers: %d rows, %d entries.",
            kind.value,
            len(fitted),
            risk_set.rows(),
            risk_set.events(),
        )
        return risk_set

    def refill(self, risk_set: RiskSet, sets: Dict[CloudProvider, FoundationColumns], lag: int) -> RiskSet:
        """Recompute the foundation share and the experience of a hazard risk set with other foundation sets.

        Args:
            risk_set (RiskSet): The hazard risk set.
            sets (Dict[CloudProvider, FoundationColumns]): The other foundation columns, for the same dependents.
            lag (int): The years the foundations must have been held.

        Returns:
            RiskSet: The same rows, the two foundation columns recomputed.
        """
        x = risk_set.x.copy()
        rows = zip(risk_set.providers, risk_set.columns, risk_set.years, strict=True)
        for row, (provider, column, year) in enumerate(rows):
            foundations = sets[provider][int(column)]
            x[row, 0] = self.foundations.share(provider, foundations, int(year), lag)
            x[row, 1] = math.log1p(self.foundations.experience(provider, foundations, int(year)))
        return RiskSet(
            names=risk_set.names,
            x=x,
            y=risk_set.y,
            providers=risk_set.providers,
            columns=risk_set.columns,
            years=risk_set.years,
        )
