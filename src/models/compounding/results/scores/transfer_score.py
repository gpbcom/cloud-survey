from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider


class TransferScore(BaseModel):
    """How well the hazard model fitted on AWS predicts another provider's entries.

    Attributes:
        provider (CloudProvider): The provider predicted.
        rows (int): Its rows at risk.
        events (int): Its entries.
        auc (Optional[float]): The area under the ROC curve of the AWS model (0.5 is chance).
        baseline_auc (Optional[float]): The same for the AWS model without the foundation terms.
        log_score (Optional[float]): The mean log-likelihood per row of the AWS model (higher is better).
        baseline_log_score (Optional[float]): The same without the foundation terms.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The provider predicted.")
    rows: int = Field(ge=0, description="Its rows at risk.")
    events: int = Field(ge=0, description="Its entries.")
    auc: Optional[float] = Field(default=None, ge=0, le=1, description="The area under the ROC curve.")
    baseline_auc: Optional[float] = Field(default=None, ge=0, le=1, description="The baseline area.")
    log_score: Optional[float] = Field(default=None, description="The mean log-likelihood per row.")
    baseline_log_score: Optional[float] = Field(default=None, description="The baseline mean log-likelihood.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def gain(self) -> Optional[float]:
        """Get what the foundation terms add to the area under the ROC curve.

        Returns:
            Optional[float]: The difference of the areas, `None` when either is unknown.
        """
        if self.auc is None or self.baseline_auc is None:
            return None
        return self.auc - self.baseline_auc
