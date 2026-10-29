from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.results.fits.growth_fit import GrowthFit
from models.compounding.results.fits.heaps_fit import HeapsFit
from models.compounding.results.fits.regression_fit import RegressionFit
from models.compounding.results.scores.compounding_warning import CompoundingWarning
from models.compounding.results.scores.placebo_result import PlaceboResult
from models.compounding.results.scores.summary_row import SummaryRow
from models.compounding.results.scores.transfer_score import TransferScore
from models.compounding.results.series.market_year import MarketYear
from models.compounding.results.series.provider_coverage import ProviderCoverage
from models.compounding.results.series.provider_year import ProviderYear


class CompoundingReport(BaseModel):
    """Everything a compounding analysis gives, shown card for card in the Analysis tab and in the results document.

    Attributes:
        query (CompoundingQuery): What was fitted.
        coverage (List[ProviderCoverage]): What the database holds for each provider.
        provider_years (List[ProviderYear]): The yearly catalogue of each provider.
        market_years (List[MarketYear]): The yearly cloud-market size.
        heaps (List[HeapsFit]): Heaps' law of each provider (6.8).
        growth (List[GrowthFit]): The growth of each provider's catalogue (6.6, 6.7).
        entry (List[RegressionFit]): The density model of each provider and pooled (6.5).
        hazard (List[RegressionFit]): The foundation hazard of each provider and pooled, at the lag asked (6.13).
        lags (List[RegressionFit]): The pooled and AWS foundation hazards at every lag of the settings.
        placebo (List[PlaceboResult]): The placebo test of each hazard fit.
        transfer (List[TransferScore]): How the AWS hazard model predicts each other provider.
        summary (List[SummaryRow]): What every model says about each provider and the pooled fit.
        foundations (Dict[str, List[str]]): The foundation sets used (curated or data-driven, for all providers).
        warnings (List[CompoundingWarning]): The caveats.
    """

    model_config = ConfigDict(frozen=True)

    query: CompoundingQuery = Field(description="What was fitted.")
    coverage: List[ProviderCoverage] = Field(default_factory=list, description="What the database holds.")
    provider_years: List[ProviderYear] = Field(default_factory=list, description="The yearly catalogues.")
    market_years: List[MarketYear] = Field(default_factory=list, description="The yearly market size.")
    heaps: List[HeapsFit] = Field(default_factory=list, description="Heaps' law of each provider.")
    growth: List[GrowthFit] = Field(default_factory=list, description="The catalogue growth of each provider.")
    entry: List[RegressionFit] = Field(default_factory=list, description="The density models.")
    hazard: List[RegressionFit] = Field(default_factory=list, description="The foundation hazards.")
    lags: List[RegressionFit] = Field(default_factory=list, description="The hazards at every lag.")
    placebo: List[PlaceboResult] = Field(default_factory=list, description="The placebo tests.")
    transfer: List[TransferScore] = Field(default_factory=list, description="The predictions from AWS.")
    summary: List[SummaryRow] = Field(default_factory=list, description="What every model says.")
    foundations: Dict[str, List[str]] = Field(default_factory=dict, description="The foundation sets used.")
    warnings: List[CompoundingWarning] = Field(default_factory=list, description="The caveats.")
