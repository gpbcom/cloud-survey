from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import CurveKind, Verdict
from models.compounding.results.fits.estimate import Estimate


class SummaryRow(BaseModel):
    """What every model says about a provider, or about the pooled fit.

    Attributes:
        provider (Optional[CloudProvider]): The provider, `None` for the pooled fit.
        excluded (bool): Whether the provider is outside the public-cloud scope (a flagged robustness row).
        events (int): Its entries fitted by the hazard model.
        heaps (Optional[Estimate]): The Heaps' law slope.
        growth (Optional[Estimate]): The launch rate per product already held (b of 6.6).
        best_curve (Optional[CurveKind]): The growth curve with the lowest AIC.
        density (Optional[Estimate]): The coefficient of the density of related categories (6.5).
        foundations (Optional[Estimate]): The coefficient of the share of foundations held (beta 1 of 6.13).
        experience (Optional[Estimate]): The coefficient of the experience in the foundations (beta 2).
        size (Optional[Estimate]): The coefficient of the catalogue size in the hazard model.
        share (Optional[Estimate]): The coefficient of the market share in the hazard model (S2).
        market (Optional[Estimate]): The coefficient of the growth of the cloud market in the hazard model.
        placebo (Optional[float]): The share of placebo foundation sets doing at least as well.
        transfer (Optional[float]): The gain of area under the ROC curve when the AWS model predicts the provider.
        verdict (Verdict): What the models say.
    """

    model_config = ConfigDict(frozen=True)

    provider: Optional[CloudProvider] = Field(default=None, description="The provider.")
    excluded: bool = Field(default=False, description="Whether it is a flagged robustness row.")
    events: int = Field(default=0, ge=0, description="Its entries fitted.")
    heaps: Optional[Estimate] = Field(default=None, description="The Heaps' law slope.")
    growth: Optional[Estimate] = Field(default=None, description="The launch rate per product held.")
    best_curve: Optional[CurveKind] = Field(default=None, description="The best growth curve.")
    density: Optional[Estimate] = Field(default=None, description="The density coefficient.")
    foundations: Optional[Estimate] = Field(default=None, description="The foundation coefficient.")
    experience: Optional[Estimate] = Field(default=None, description="The experience coefficient.")
    size: Optional[Estimate] = Field(default=None, description="The size coefficient.")
    share: Optional[Estimate] = Field(default=None, description="The share coefficient.")
    market: Optional[Estimate] = Field(default=None, description="The market-growth coefficient.")
    placebo: Optional[float] = Field(default=None, ge=0, le=1, description="The placebo share.")
    transfer: Optional[float] = Field(default=None, description="The transfer gain of AUC.")
    verdict: Verdict = Field(default=Verdict.INSUFFICIENT, description="What the models say.")
